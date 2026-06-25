"""Генерация промокода. Детерминированно: один пользователь = один код."""
import hashlib


def generate_code(user_id: int, prefix: str = "RL") -> str:
    """RL-XXXX, где XXXX — стабильный хэш от user_id (повторный запрос → тот же код)."""
    digest = hashlib.sha1(str(user_id).encode()).hexdigest()[:4].upper()
    return f"{prefix}-{digest}"
