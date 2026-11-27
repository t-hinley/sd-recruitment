"""Send a copy of each employer enquiry and candidate registration to Airtable.

The website database is always the main record: a submission is saved there first and the visitor
always sees "Thank you". The copy in Airtable is created straight afterwards. If Airtable cannot be
reached, the record is marked "Failed" and sent again later (admin action "Send to Airtable again" or
`manage.py sync_airtable`).

Each website form goes to the table set for its Airtable form. Today both Airtable forms share one
table; see SHARED_TABLE below for how columns are matched.

Settings (in .env): AIRTABLE_TOKEN, AIRTABLE_BASE_ID, AIRTABLE_EMPLOYER_TABLE (Employer Enquiry Form)
and AIRTABLE_TALENT_TABLE (Talent Registration Form). With the token empty, the integration is off.
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

# The table both Airtable forms save into today. While a form's table (AIRTABLE_EMPLOYER_TABLE /
# AIRTABLE_TALENT_TABLE) is this one, columns are addressed by their field ID, exactly as the Airtable
# forms map them, so renaming a column doesn't break anything. If a form is moved to its own table,
# columns are addressed by NAME instead: the column names below, which are the Airtable form labels.
SHARED_TABLE = "tblZaBP5px3dqWuaD"

# (website value, field ID in the shared table, column name in a table of its own)
EMPLOYER_FIELDS = [
    ("company", "flde6QS0zw4mK3vcV", "Company Name"),          # Organisation / Company Name
    ("industry", "fldZzLlrg8bgGdkpY", "Industry / Sector"),
    ("contact_name", "fldg9tVfNK7REj52P", "Contact Person"),   # shared table: "Position / Job Title"
    ("phone", "fldDXTuMrsq5riVPU", "Mobile Number"),           # shared table: "Phone Number"
    ("email", "fldjEWSC9V0b31LEf", "Email Address"),
    ("position", "fldRtIJEPWV15RmSv", "Position Recruiting For"),
    ("employment_types", "fldlKUehNaiNjxa90", "Employment Type"),
    ("positions_count", "fldg2R4etvUrg9WBQ", "Number of Vacancies"),  # shared table: "Number of Staff Required"
    ("location", "fldaFBs37NRkuw38W", "Work Location"),        # shared table: "Country / Location"
    ("details", "fld93WIxFp36uXcwo", "Additional Requirements or Comments"),  # shared: "Additional Information"
    ("consent", "fldt1MwrPLURa3fJo", "Consent to Contact"),
]
TALENT_FIELDS = [
    ("full_name", "fldNazuVVEevqlwIf", "Full Name"),           # shared table: "Enquiry / Registration Name"
    ("phone", "fldDXTuMrsq5riVPU", "Phone Number"),
    ("email", "fldjEWSC9V0b31LEf", "Email Address"),
    ("location", "fldaFBs37NRkuw38W", "Country / Location"),
    ("visa_type", "fldlOQ61PTPvjfZkt", "Visa Type"),
    ("preferred_location", "fldj8QcpglaHe7K1e", "Preferred Job Location"),
    ("industry", "fld8DCHC9mxzlYQyN", "Industry / Job Category"),
    ("position_sought", "fld0UHh3D9L21yqPx", "Position(s) Interested In"),
    ("employment_types", "fldlKUehNaiNjxa90", "Employment Type"),
    ("experience", "fld2MpuDbls6jFRt0", "Relevant Work Experience"),
]
# Only in the shared table (the Talent Registration Form has no such question):
SHARED_ONLY = {
    "employer_name": "fldNazuVVEevqlwIf",   # Enquiry / Registration Name: filled with the company name
    "talent_consent": "fldt1MwrPLURa3fJo",  # Consent to Contact
}


def enabled():
    return bool(settings.AIRTABLE_TOKEN and settings.AIRTABLE_BASE_ID)


def table_for(obj):
    from .models import VacancyEnquiry
    return settings.AIRTABLE_EMPLOYER_TABLE if isinstance(obj, VacancyEnquiry) else settings.AIRTABLE_TALENT_TABLE


def _clean(fields):
    """Leave out empty values, as the Airtable form does for fields left blank."""
    return {k: v for k, v in fields.items() if v not in ("", None, [])}


def _value(obj, attr):
    value = getattr(obj, attr)
    if attr == "employment_types":
        return list(value or [])
    if attr == "consent":
        return bool(value)
    return value


def fields_for(obj):
    """Website record -> Airtable fields, mirroring what each Airtable form writes."""
    from .models import CandidateRegistration, VacancyEnquiry
    if isinstance(obj, VacancyEnquiry):
        mapping = EMPLOYER_FIELDS
    elif isinstance(obj, CandidateRegistration):
        mapping = TALENT_FIELDS
    else:
        raise TypeError(f"{type(obj).__name__} is not sent to Airtable")
    shared = table_for(obj) == SHARED_TABLE
    fields = {(fid if shared else name): _value(obj, attr) for attr, fid, name in mapping}
    if shared:
        if isinstance(obj, VacancyEnquiry):
            fields[SHARED_ONLY["employer_name"]] = obj.company  # the Airtable form leaves this empty
        else:
            fields[SHARED_ONLY["talent_consent"]] = bool(obj.consent)
    return _clean(fields)


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
                    f"{settings.AIRTABLE_BASE_ID}, and the AIRTABLE_EMPLOYER_TABLE / AIRTABLE_TALENT_TABLE settings)")
        elif e.code == 422 and "UNKNOWN_FIELD_NAME" in str(err):
            hint = " (a column name in Airtable doesn't match the form label the website uses; see core/airtable.py)"
        raise AirtableError(f"HTTP {e.code} {err}{hint}"[:500]) from e
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        raise AirtableError(f"Could not reach Airtable: {getattr(e, 'reason', e)}"[:500]) from e


def _table_url(obj):
    return f"{API}/{settings.AIRTABLE_BASE_ID}/{urllib.parse.quote(table_for(obj), safe='')}"


DEMO_EMAIL_DOMAIN = "@demo.example.com"


def is_demo(obj):
    """Sample records made by `manage.py demo_enquiries` (their email ends in @demo.example.com)."""
    return (getattr(obj, "email", "") or "").lower().endswith(DEMO_EMAIL_DOMAIN)


def push(obj):
    """Create the Airtable copy of one record (once). Never raises; records the result on the object.
    Returns True when Airtable has it."""
    from .models import AIRTABLE_FAILED, AIRTABLE_OFF, AIRTABLE_SENT
    model = type(obj)
    if obj.airtable_id:
        return True
    if is_demo(obj) or not enabled():  # sample records (manage.py demo_enquiries) never go to Airtable
        model.objects.filter(pk=obj.pk, airtable_id="").update(airtable_status=AIRTABLE_OFF)
        obj.airtable_status = AIRTABLE_OFF
        return False
    try:
        # "typecast" lets Airtable add a dropdown option it doesn't have yet (needed for
        # "Position Recruiting For", which has no options in Airtable).
        created = _request("POST", _table_url(obj), {"records": [{"fields": fields_for(obj)}], "typecast": True})
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
