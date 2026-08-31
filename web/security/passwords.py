"""Хеширование паролей веб-пользователей.

Формат хранения: pbkdf2_sha256$<iterations>$<salt>$<hash>
PBKDF2-HMAC-SHA256, 100 000 итераций — стандартная библиотека, без внешних
зависимостей (bcrypt/argon2 требуют нативных сборок; PBKDF2 рекомендован NIST).
"""

import base64
import hashlib
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 100_000


def hash_password(password: str) -> str:
    """Хешировать пароль в самодостаточную строку для хранения в БД."""
    salt = base64.b64encode(secrets.token_bytes(16)).decode()
    digest = hashlib.pbkdf2_hmac(
        "sha256", password.encode("utf-8"), salt.encode("utf-8"), ITERATIONS
    )
    return f"{ALGORITHM}${ITERATIONS}${salt}${base64.b64encode(digest).decode()}"


def verify_password(password: str, stored: str | None) -> bool:
    """Проверить пароль против сохранённого хеша (timing-safe)."""
    if not stored:
        return False
    try:
        algorithm, iterations, salt, expected = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        )
        return secrets.compare_digest(
            base64.b64encode(digest).decode("ascii"), expected
        )
    except (ValueError, TypeError):
        return False
