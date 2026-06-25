import importlib


def test_database_url_from_env(monkeypatch):
    monkeypatch.setenv("DATABASE_URL", "postgresql://u:p@h:5432/db")
    import bot.config as cfg
    importlib.reload(cfg)
    assert cfg.settings.database_url == "postgresql://u:p@h:5432/db"
    # restore default state for other tests
    monkeypatch.delenv("DATABASE_URL", raising=False)
    importlib.reload(cfg)
