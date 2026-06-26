"""Веб-дашборд (этап 8): Basic-auth, одна страница с воронкой и заявками."""
import base64
import secrets
from html import escape

from aiohttp import web

from bot.config import settings
from bot.services.stats import Stats, get_stats


def _authorized(header: str) -> bool:
    if not header.startswith("Basic "):
        return False
    try:
        user, _, pwd = base64.b64decode(header[6:]).decode().partition(":")
    except Exception:
        return False
    return (
        secrets.compare_digest(user, settings.dashboard_user)
        and secrets.compare_digest(pwd, settings.dashboard_password)
    )


@web.middleware
async def _auth_mw(request, handler):
    if not _authorized(request.headers.get("Authorization", "")):
        return web.Response(
            status=401,
            text="401",
            headers={"WWW-Authenticate": 'Basic realm="dashboard"'},
        )
    return await handler(request)


def render_html(s: Stats) -> str:
    rows = "".join(
        f"<tr><td>{escape(l.ts)}</td><td>{escape(l.name)}</td><td>{escape(l.city)}</td>"
        f"<td>{escape(l.type)}</td><td>{escape(l.contact)}</td><td>{escape(l.utm_source)}</td></tr>"
        for l in s.recent_leads
    )
    src = "".join(f"<li>{escape(n or 'direct')}: {c}</li>" for n, c in s.starts_by_source)
    return (
        "<!doctype html><meta charset='utf-8'><title>ruslineup dashboard</title>"
        "<style>body{font-family:sans-serif;margin:2rem;max-width:900px}"
        "table{border-collapse:collapse;width:100%}td,th{border:1px solid #ccc;padding:4px 8px}"
        "h1{font-size:1.3rem}</style>"
        "<h1>📊 Русский Лайнап — дашборд</h1>"
        f"<p>Старты: <b>{s.starts_total}</b> (сегодня {s.starts_today}, 7 дней {s.starts_7d})</p>"
        f"<p>Заявки: <b>{s.leads_total}</b> · конверсия start→lead {s.lead_conv()}</p>"
        f"<p>Промокоды: <b>{s.promo_total}</b> · конверсия start→promo {s.promo_conv()}</p>"
        f"<p>Источники стартов:</p><ul>{src}</ul>"
        "<h2>Последние заявки</h2>"
        "<table><tr><th>Когда</th><th>Имя</th><th>Город</th><th>Тип</th>"
        f"<th>Контакт</th><th>Источник</th></tr>{rows}</table>"
    )


async def _index(request):
    return web.Response(text=render_html(await get_stats()), content_type="text/html")


def build_app() -> web.Application:
    app = web.Application(middlewares=[_auth_mw])
    app.router.add_get("/", _index)
    return app
