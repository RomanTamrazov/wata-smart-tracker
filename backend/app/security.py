from __future__ import annotations

import hashlib
import secrets


def generate_salt() -> str:
    return secrets.token_hex(16)


def hash_password(password: str, salt: str) -> str:
    raw = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 210_000)
    return raw.hex()


def verify_password(password: str, salt: str, expected_hash: str) -> bool:
    actual = hash_password(password, salt)
    return secrets.compare_digest(actual, expected_hash)


def issue_token() -> str:
    return secrets.token_urlsafe(32)
