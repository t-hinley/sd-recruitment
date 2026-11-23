"""Send a copy of each employer enquiry and candidate registration to Airtable.

The website database is always the main record: a submission is saved there first and the visitor
always sees "Thank you". The copy in Airtable is created straight afterwards. If Airtable cannot be
reached, the record is marked "Failed" and sent again later (admin action "Send to Airtable again" or
`manage.py sync_airtable`).

Both Airtable forms (Employer Enquiry Form and Talent Registration Form) save into the same table, so
both website forms do too. Fields are addressed by their Airtable field ID, exactly as the Airtable
forms map them, so renaming a column in Airtable does not break the website.

Settings (in .env): AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_TABLE. With the token empty, the
integration is switched off.
"""

import json
import logging
import ssl
import urllib.error
import urllib.parse
import urllib.request

from django.conf import settings
from django.utils import timezone

logger = logging.getLogger(__name__)
API = "https://api.airtable.com/v0"

# Airtable field IDs (table "tblZaBP5px3dqWuaD"), read from the two Airtable forms.
F = {
    "name": "fldNazuVVEevqlwIf",            # Enquiry / Registration Name (primary field)
    "phone": "fldDXTuMrsq5riVPU",           # Phone Number
    "email": "fldjEWSC9V0b31LEf",           # Email Address
    "location": "fldaFBs37NRkuw38W",        # Country / Location (employer form: "Work Location")
    "company": "flde6QS0zw4mK3vcV",         # Organisation / Company Name
    "job_title": "fldg9tVfNK7REj52P",       # Position / Job Title (employer form: "Contact Person")
    "employer_industry": "fldZzLlrg8bgGdkpY",  # Industry / Sector
    "staff_required": "fldg2R4etvUrg9WBQ",  # Number of Staff Required ("Number of Vacancies")
    "additional": "fld93WIxFp36uXcwo",      # Additional Information ("Additional Requirements or Comments")
    "consent": "fldt1MwrPLURa3fJo",         # Consent to Contact
    "employment_type": "fldlKUehNaiNjxa90",  # Employment Type (multiple select)
    "position_recruiting": "fldRtIJEPWV15RmSv",  # Position Recruiting For (single select)
    "preferred_location": "fldj8QcpglaHe7K1e",   # Preferred Job Location
    "candidate_industry": "fld8DCHC9mxzlYQyN",   # Industry / Job Category
    "positions_interested": "fld0UHh3D9L21yqPx",  # Position(s) Interested In
    "experience": "fld2MpuDbls6jFRt0",      # Relevant Work Experience
    "visa": "fldlOQ61PTPvjfZkt",            # Visa Type
}


def enabled():
    return bool(settings.AIRTABLE_TOKEN and settings.AIRTABLE_BASE_ID and settings.AIRTABLE_TABLE)


def _clean(fields):
    """Leave out empty values, as the Airtable form does for fields left blank."""
    return {k: v for k, v in fields.items() if v not in ("", None, [])}


def fields_for(obj):
    """Website record -> Airtable fields, mirroring what each Airtable form writes."""
    from .models import CandidateRegistration, VacancyEnquiry
    if isinstance(obj, VacancyEnquiry):
        return _clean({
            F["name"]: obj.company,             # the Airtable form leaves this empty; the company names the row
            F["company"]: obj.company,
            F["employer_industry"]: obj.industry,
            F["job_title"]: obj.contact_name,   # the Airtable form maps "Contact Person" here
            F["phone"]: obj.phone,
            F["email"]: obj.email,
            F["position_recruiting"]: obj.position,
            F["employment_type"]: list(obj.employment_types or []),
            F["staff_required"]: obj.positions_count,
            F["location"]: obj.location,
            F["additional"]: obj.details,
            F["consent"]: bool(obj.consent),
        })
    if isinstance(obj, CandidateRegistration):
        return _clean({
            F["name"]: obj.full_name,
            F["phone"]: obj.phone,
            F["email"]: obj.email,
            F["location"]: obj.location,
            F["visa"]: obj.visa_type,
            F["preferred_location"]: obj.preferred_location,
            F["candidate_industry"]: obj.industry,
            F["positions_interested"]: obj.position_sought,
            F["employment_type"]: list(obj.employment_types or []),
            F["experience"]: obj.experience,
            F["consent"]: bool(obj.consent),
        })
    raise TypeError(f"{type(obj).__name__} is not sent to Airtable")


def _ssl_context():
    """Trusted certificates from the certifi package, so https works even where Python has no
    certificate list of its own."""
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:  # pragma: no cover
        return ssl.create_default_context()


class AirtableError(Exception):
    pass


def _request(method, url, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": f"Bearer {settings.AIRTABLE_TOKEN}",
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=settings.AIRTABLE_TIMEOUT, context=_ssl_context()) as resp:
            return json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        body = e.read().decode(errors="replace")
        try:
            err = json.loads(body).get("error", body)
            if isinstance(err, dict):
                err = f"{err.get('type', '')}: {err.get('message', '')}".strip(": ")
        except ValueError:
            err = body
        hint = ""
        if e.code in (401, 403, 404):
            hint = (" (check AIRTABLE_TOKEN, that the token has data.records:write access to base "
                    f"{settings.AIRTABLE_BASE_ID}, and AIRTABLE_TABLE={settings.AIRTABLE_TABLE!r})")
        raise AirtableError(f"HTTP {e.code} {err}{hint}"[:500]) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AirtableError(f"Could not reach Airtable: {getattr(e, 'reason', e)}"[:500]) from e


def _table_url():
    return f"{API}/{settings.AIRTABLE_BASE_ID}/{urllib.parse.quote(settings.AIRTABLE_TABLE, safe='')}"


def push(obj):
    """Create the Airtable copy of one record (once). Never raises; records the result on the object.
    Returns True when Airtable has it."""
    from .models import AIRTABLE_FAILED, AIRTABLE_OFF, AIRTABLE_SENT
    model = type(obj)
    if obj.airtable_id:
        return True
    if not enabled():
        model.objects.filter(pk=obj.pk, airtable_id="").update(airtable_status=AIRTABLE_OFF)
        obj.airtable_status = AIRTABLE_OFF
        return False
    try:
        # "typecast" lets Airtable add a dropdown option it doesn't have yet (needed for
        # "Position Recruiting For", which has no options in Airtable).
        created = _request("POST", _table_url(), {"records": [{"fields": fields_for(obj)}], "typecast": True})
        record_id = created["records"][0]["id"]
    except (AirtableError, KeyError, IndexError, ValueError) as e:
        logger.warning("Airtable send failed for %s #%s: %s", model.__name__, obj.pk, e)
        model.objects.filter(pk=obj.pk).update(airtable_status=AIRTABLE_FAILED, airtable_error=str(e)[:500])
        obj.airtable_status, obj.airtable_error = AIRTABLE_FAILED, str(e)[:500]
        return False
    now = timezone.now()
    # .update() so this bookkeeping does not change "Last updated".
    model.objects.filter(pk=obj.pk).update(airtable_id=record_id, airtable_status=AIRTABLE_SENT,
                                           airtable_error="", airtable_synced_at=now)
    obj.airtable_id, obj.airtable_status, obj.airtable_error, obj.airtable_synced_at = record_id, AIRTABLE_SENT, "", now
    return True
