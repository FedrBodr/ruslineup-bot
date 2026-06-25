import importlib


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.database_url == "postgresql://u:p@h:5432/db"
    # restore default state for other tests
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(cfg)


_DB_ENV = ("DATABASE_URL", "DATABASE_HOST", "DATABASE_PORT", "DATABASE_USER",
           "DATABASE_PASSWORD", "DATABASE_NAME")


def _reload_clean(monkeypatch):
    for k in _DB_ENV:
        monkeypatch.delenv(k, raising=False)
    import bot.config as cfg
    importlib.reload(cfg)
    return cfg


def test_dsn_prefers_database_url(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.dsn == "postgresql://u:p@h:5432/db"
    _reload_clean(monkeypatch)


def test_dsn_from_components_encodes_password(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    monkeypatch.setenv("DATABASE_HOST", "db.internal")
    monkeypatch.setenv("DATABASE_USER", "ruslineup")
    monkeypatch.setenv("DATABASE_PASSWORD", "p@ss/word")
    monkeypatch.setenv("DATABASE_NAME", "ruslineup")
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.dsn == "postgresql://ruslineup:p%40ss%2Fword@db.internal:5432/ruslineup"
    _reload_clean(monkeypatch)


def test_dsn_empty_without_config(monkeypatch):
    cfg = _reload_clean(monkeypatch)
    assert cfg.settings.dsn == ""
