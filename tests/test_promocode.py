from bot.services.promocode import generate_code


def test_format():
    code = generate_code(12345678)
    assert code.startswith("RL-")
    assert len(code) == 7  # "RL-" + 4 символа


def test_stable_per_user():
    assert generate_code(42) == generate_code(42)


def test_different_users_differ():
    assert generate_code(1) != generate_code(2)
