import hashlib
import hmac
import secrets


def generate_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def generate_code() -> str:
    return f"{secrets.randbelow(10**6):06d}"


def same_hash(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)
