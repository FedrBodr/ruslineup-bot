import importlib


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.database_url == "postgresql://u:p@h:5432/db"
    # restore default state for other tests
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(cfg)


# dsn — чистая логика на полях dataclass: тестируем прямым инстанцированием,
# без env/reload (иначе load_dotenv подхватывает реальный .env разработчика).
from bot.config import Settings  # noqa: E402


def test_dsn_uses_full_url():
    s = Settings(database_url="postgresql://u:p@h:5432/db")
    assert s.dsn == "postgresql://u:p@h:5432/db"


def test_dsn_strips_jdbc_and_injects_creds():
    # ровно кейс Amvera: jdbc-URL без логина + отдельные user/password
    s = Settings(
        database_url="jdbc:postgresql://host.amvera.tech:5432/ruslineup",
        database_user="ruslineup",
        database_password="p@ss/word",
    )
    assert s.dsn == "postgresql://ruslineup:p%40ss%2Fword@host.amvera.tech:5432/ruslineup"


def test_dsn_from_components():
    s = Settings(
        database_url="",
        database_host="db.internal",
        database_port="5432",
        database_user="ruslineup",
        database_password="secret",
        database_name="ruslineup",
    )
    assert s.dsn == "postgresql://ruslineup:secret@db.internal:5432/ruslineup"


def test_dsn_empty():
    assert Settings(database_url="", database_host="", database_user="").dsn == ""


def test_dashboard_and_port_fields():
    s = Settings(dashboard_user="admin", dashboard_password="pw", web_port=9000)
    assert s.dashboard_user == "admin"
    assert s.dashboard_password == "pw"
    assert s.web_port == 9000


def test_ai_daily_limit_field():
    from bot.config import Settings
    assert Settings().ai_daily_limit == 20
    assert Settings(ai_daily_limit=5).ai_daily_limit == 5
