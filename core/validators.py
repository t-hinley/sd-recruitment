"""Contact number and email checks for the website forms (candidate, employer and contact). They run on the
server (the browser repeats the format checks as people type, static/js/main.js, but can't be relied on).

Phone: an Australian number typed the usual way (0412 345 678, 08 9200 1234, 1300 123 456, or +61 ...), or an
overseas number starting with + and the country code (common countries checked against their mobile format).
Saved in a tidy, consistent form.

Email: a strict format check, common typos caught ("Did you mean ...@gmail.com?"), throwaway inboxes refused,
and the domain must be able to receive email (a quick DNS lookup; if the lookup itself fails we accept the
address rather than lose a real enquiry).
"""

import re

from django.conf import settings
from django.core.exceptions import ValidationError

# ---- Phone ---------------------------------------------------------------------------------------------------
AU_RULES = [  # (pattern on the 10 digits after converting +61 to 0, formatter)
    (re.compile(r"^04\d{8}$"), lambda d: f"{d[:4]} {d[4:7]} {d[7:]}"),            # mobile 0412 345 678
    (re.compile(r"^0[2378]\d{8}$"), lambda d: f"{d[:2]} {d[2:6]} {d[6:]}"),        # landline 08 9200 1234
    (re.compile(r"^1[38]00\d{6}$"), lambda d: f"{d[:4]} {d[4:7]} {d[7:]}"),        # 1300 / 1800 123 456
]
# Overseas mobiles: country code -> (country, rule for the digits after the code, example)
OVERSEAS = {
    "975": ("Bhutan", r"(?:17|77)\d{6}", "+975 17 123 456"),
    "977": ("Nepal", r"9[678]\d{8}", "+977 98 1234 5678"),
    "91": ("India", r"[6-9]\d{9}", "+91 98765 43210"),
    "880": ("Bangladesh", r"1[3-9]\d{8}", "+880 1712 345678"),
    "94": ("Sri Lanka", r"7\d{8}", "+94 71 234 5678"),
    "92": ("Pakistan", r"3\d{9}", "+92 301 2345678"),
    "63": ("the Philippines", r"9\d{9}", "+63 917 123 4567"),
    "64": ("New Zealand", r"2\d{7,9}", "+64 21 123 4567"),
    "44": ("the UK", r"7\d{9}", "+44 7123 456789"),
    "1": ("the USA or Canada", r"[2-9]\d{2}[2-9]\d{6}", "+1 415 555 2671"),
}
TRUNK_ZERO = {"977", "91", "880", "94", "92", "63", "64", "44"}  # a 0 typed after the code is dropped
PHONE_HELP = ("Enter an Australian number such as 0412 345 678 or 08 9200 1234, "
              "or an overseas number starting with + and the country code.")


def clean_phone(value):
    """Return the number in a tidy form ('0412 345 678', '+97517123456') or raise ValidationError."""
    raw = (value or "").strip()
    if not raw:
        return ""
    if not re.fullmatch(r"[+()\d\s.-]+", raw):
        raise ValidationError("Use numbers only. " + PHONE_HELP)
    digits = re.sub(r"\D", "", raw)
    international = raw.startswith("+") or raw.startswith("00")
    if raw.startswith("00"):
        digits = digits[2:]
    if international and digits.startswith("61"):          # +61 ... is Australian: write it the local way
        digits, international = "0" + digits[2:].removeprefix("0"), False
    if not international:
        for rule, fmt in AU_RULES:
            if rule.match(digits):
                if len(set(digits[2:])) == 1:
                    raise ValidationError("That number doesn't look real. " + PHONE_HELP)
                return fmt(digits)
        if digits.startswith("04"):
            raise ValidationError("Australian mobile numbers have 10 digits, for example 0412 345 678.")
        raise ValidationError(PHONE_HELP)
    code = next((c for c in sorted(OVERSEAS, key=len, reverse=True) if digits.startswith(c)), None)
    if code:
        country, rule, example = OVERSEAS[code]
        rest = digits[len(code):]
        if code in TRUNK_ZERO:
            rest = rest.removeprefix("0")
        if re.fullmatch(rule, rest):
            return f"+{code}{rest}"
        raise ValidationError(f"That doesn't look like a mobile number in {country}. Example: {example}.")
    if re.fullmatch(r"[1-9]\d{7,14}", digits):
        return "+" + digits
    raise ValidationError(PHONE_HELP)


# ---- Email ---------------------------------------------------------------------------------------------------
EMAIL_RE = re.compile(
    r"^(?!.*\.\.)[a-z0-9](?:[a-z0-9._%+-]{0,62}[a-z0-9])?"
    r"@(?:[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?\.)+[a-z]{2,24}$"
)
TYPOS = {  # common slips -> the domain they meant
    "gmial.com": "gmail.com", "gmai.com": "gmail.com", "gmal.com": "gmail.com", "gamil.com": "gmail.com",
    "gmail.co": "gmail.com", "gmail.con": "gmail.com", "gmail.cm": "gmail.com", "gnail.com": "gmail.com",
    "gmail.om": "gmail.com", "gmaill.com": "gmail.com", "hotmial.com": "hotmail.com", "hotmal.com": "hotmail.com",
    "hotmail.con": "hotmail.com", "hotmail.co": "hotmail.com", "outlok.com": "outlook.com",
    "outlook.con": "outlook.com", "yaho.com": "yahoo.com", "yahooo.com": "yahoo.com", "yahoo.con": "yahoo.com",
    "icloud.con": "icloud.com", "iclod.com": "icloud.com", "bigpond.con": "bigpond.com",
    "bigpond.com.a": "bigpond.com.au", "outlook.com.a": "outlook.com.au",
}
DISPOSABLE = {
    "mailinator.com", "guerrillamail.com", "guerrillamail.net", "sharklasers.com", "10minutemail.com",
    "tempmail.com", "temp-mail.org", "yopmail.com", "trashmail.com", "getnada.com", "maildrop.cc",
    "dispostable.com", "throwawaymail.com", "fakeinbox.com", "mintemail.com", "emailondeck.com",
}
EMAIL_HELP = "Enter a valid email address, for example name@gmail.com."


CONTROL_DOMAIN = "gmail.com"  # always receives email: used to tell "no such domain" from "DNS isn't working"


def _lookup(domain):
    """'yes' (mail servers or an address record), 'no' (domain doesn't exist / has neither) or 'unknown'."""
    try:
        import dns.exception
        import dns.resolver
    except ImportError:
        return "unknown"
    resolver = dns.resolver.Resolver()
    resolver.lifetime = resolver.timeout = 3
    try:
        resolver.resolve(domain, "MX")
        return "yes"
    except dns.resolver.NXDOMAIN:
        return "no"
    except dns.resolver.NoAnswer:
        try:
            resolver.resolve(domain, "A")
            return "yes"
        except (dns.resolver.NXDOMAIN, dns.resolver.NoAnswer):
            return "no"
        except dns.exception.DNSException:
            return "unknown"
    except dns.exception.DNSException:  # timeout, no DNS server reachable ...
        return "unknown"


def _dns_works():
    """True when this server's DNS gives real answers (checked against CONTROL_DOMAIN, remembered 10 minutes).
    Some networks answer 'doesn't exist' for everything; then we must not refuse anyone."""
    from django.core.cache import cache
    ok = cache.get("email_dns_works")
    if ok is None:
        ok = _lookup(CONTROL_DOMAIN) == "yes"
        cache.set("email_dns_works", ok, 600)
    return ok


def domain_receives_email(domain):
    """False only when we're sure the domain can't receive email. Unknown (lookup failed, DNS not working,
    or the check switched off) counts as True, so a DNS problem never blocks real people."""
    if not getattr(settings, "EMAIL_DOMAIN_CHECK", True):
        return True
    if _lookup(domain) != "no":
        return True
    return not _dns_works()


def clean_email(value):
    """Return the address in lower case, or raise ValidationError with a helpful message."""
    email = (value or "").strip().lower()
    if not email:
        return ""
    if len(email) > 254 or not EMAIL_RE.match(email):
        raise ValidationError(EMAIL_HELP)
    local, _, domain = email.rpartition("@")
    if domain in TYPOS:
        raise ValidationError(f"Did you mean {local}@{TYPOS[domain]}? Please check the email address.")
    if domain in DISPOSABLE:
        raise ValidationError("Please use your own email address (temporary inboxes can't be used).")
    if not domain_receives_email(domain):
        raise ValidationError(f"Emails can't be delivered to “{domain}”. Please check the email address for a typo.")
    return email


def browser_rules():
    """The same format rules for the browser (static/js/main.js), so mistakes show as people type."""
    return {"typos": TYPOS, "disposable": sorted(DISPOSABLE),
            "overseas": {code: [country, rule, example] for code, (country, rule, example) in OVERSEAS.items()},
            "trunkZero": sorted(TRUNK_ZERO)}
