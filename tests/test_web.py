import base64
import types

import pytest
from unittest.mock import AsyncMock
from aiohttp.test_utils import TestClient, TestServer

import bot.web as web
from bot.services.stats import Lead, Stats


def _auth(u, p):
    return "Basic " + base64.b64encode(f"{u}:{p}".encode()).decode()


def _sample():
    return Stats(
        starts_total=100, starts_today=5, starts_7d=40,
        starts_by_source=[("youtube", 60)], faq_by_topic=[("boards", 30)],
        leads_total=25, leads_by_type=[("testday", 20)], promo_total=10,
        recent_leads=[Lead("2026-06-26 03:38", "Дмитрий", "Москва",
                           "preorder", "+7926***3341", "direct")],
    )


@pytest.mark.asyncio
async def test_requires_auth(monkeypatch):
    monkeypatch.setattr(web, "settings",
                        types.SimpleNamespace(dashboard_user="a", dashboard_password="b"))
    monkeypatch.setattr(web, "get_stats", AsyncMock(return_value=_sample()))
    async with TestClient(TestServer(web.build_app())) as cli:
        assert (await cli.get("/")).status == 401
        assert (await cli.get("/", headers={"Authorization": _auth("a", "wrong")})).status == 401


@pytest.mark.asyncio
async def test_health_no_auth(monkeypatch):
    monkeypatch.setattr(web, "settings",
                        types.SimpleNamespace(dashboard_user="a", dashboard_password="b"))
    monkeypatch.setattr(web, "get_stats", AsyncMock(return_value=_sample()))
    async with TestClient(TestServer(web.build_app())) as cli:
        resp = await cli.get("/health")  # без авторизации
        assert resp.status == 200
        assert (await resp.text()) == "ok"


@pytest.mark.asyncio
async def test_ok_with_auth_and_masked(monkeypatch):
    monkeypatch.setattr(web, "settings",
                        types.SimpleNamespace(dashboard_user="a", dashboard_password="b"))
    monkeypatch.setattr(web, "get_stats", AsyncMock(return_value=_sample()))
    async with TestClient(TestServer(web.build_app())) as cli:
        resp = await cli.get("/", headers={"Authorization": _auth("a", "b")})
        assert resp.status == 200
        html = await resp.text()
        assert "100" in html and "25" in html
        assert "+7926***3341" in html
        assert "5803341" not in html  # полный телефон НЕ светится
