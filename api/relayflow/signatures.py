import hashlib
import hmac


def sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


def signatures_match(secret: str, body: bytes, header: str | None) -> bool:
    if not header:
        return False
    expected = sign(secret, body)
    if len(header) != len(expected):
        return False
    return hmac.compare_digest(expected, header)
