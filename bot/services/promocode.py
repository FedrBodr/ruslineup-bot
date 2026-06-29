"""Генерация промокода. Детерминированно: один пользователь = один код."""
import hashlib


def generate_code(user_id: int) -> str:
    """Код вида RL_NNNNNN (6 цифр), стабильный для пользователя: повтор → тот же код."""
    digest = hashlib.sha1(str(user_id).encode()).hexdigest()
    return f"RL_{int(digest, 16) % 1_000_000:06d}"
