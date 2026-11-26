"""Six-digit codes from authenticator apps (TOTP, RFC 6238: SHA-1, 30-second steps), using only the standard
library, plus the QR code people scan to add the account to their app."""

import base64
import hashlib
import hmac
import re
import secrets
import struct
import time
from urllib.parse import quote

STEP_SECONDS = 30
DIGITS = 6


def new_secret():
    return base64.b32encode(secrets.token_bytes(20)).decode().rstrip("=")


def code_at(secret, step):
    key = base64.b32decode(secret + "=" * (-len(secret) % 8), casefold=True)
    digest = hmac.new(key, struct.pack(">Q", step), hashlib.sha1).digest()
    offset = digest[-1] & 0x0F
    number = (struct.unpack(">I", digest[offset:offset + 4])[0] & 0x7FFFFFFF) % 10 ** DIGITS
    return f"{number:0{DIGITS}d}"


def match(secret, code, last_used_step=-1, now=None, window=1):
    """The time step the code belongs to, or None. Accepts one step either side (clock drift) and never a
    step already used, so a code can't be replayed."""
    code = re.sub(r"\s", "", code or "")
    if not re.fullmatch(rf"\d{{{DIGITS}}}", code):
        return None
    current = int((time.time() if now is None else now) // STEP_SECONDS)
    for step in range(current - window, current + window + 1):
        if step > last_used_step and hmac.compare_digest(code_at(secret, step), code):
            return step
    return None


def provisioning_uri(secret, account, issuer):
    label = quote(f"{issuer}:{account}")
    return (f"otpauth://totp/{label}?secret={secret}&issuer={quote(issuer)}"
            f"&algorithm=SHA1&digits={DIGITS}&period={STEP_SECONDS}")


def qr_svg(uri):
    import segno
    return segno.make(uri, error="m").svg_inline(omitsize=True, border=2, dark="#1B2A5C", light="#FFFFFF")


def grouped(secret):
    return " ".join(secret[i:i + 4] for i in range(0, len(secret), 4))
