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
    # /health — без авторизации, чтобы health-проба Amvera не упёрлась в 401.
    if request.path == "/health":
        return await handler(request)
    if not _authorized(request.headers.get("Authorization", "")):
        return web.Response(
            status=401,
            text="401",
            headers={"WWW-Authenticate": 'Basic realm="dashboard"'},
        )
    return await handler(request)


async def _health(request):
    return web.Response(text="ok")


_STYLE = """
<style>
  :root{--bg:#0e1726;--card:#152236;--line:#26344d;--text:#e6edf6;--muted:#8aa0bd;--accent:#21c4b8;--accent2:#3b82f6}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--text)}
  .wrap{max-width:980px;margin:0 auto;padding:28px 20px 60px}
  header{display:flex;align-items:baseline;gap:12px;margin-bottom:22px}
  header h1{font-size:22px;margin:0}
  header .sub{color:var(--muted);font-size:14px}
  .cards{display:grid;grid-template-columns:repeat(3,1fr);gap:14px}
  @media(max-width:680px){.cards{grid-template-columns:1fr}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
  .card .label{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}
  .card .num{font-size:34px;font-weight:700;margin:6px 0 2px;background:linear-gradient(90deg,var(--accent),var(--accent2));-webkit-background-clip:text;background-clip:text;color:transparent}
  .card .meta{color:var(--muted);font-size:13px}
  .card .conv{display:inline-block;margin-top:8px;padding:2px 10px;border-radius:999px;background:rgba(33,196,184,.14);color:var(--accent);font-size:13px;font-weight:600}
  .section{margin-top:26px}
  .section h2{font-size:13px;color:var(--muted);text-transform:uppercase;letter-spacing:.04em;margin:0 0 10px}
  .chips{display:flex;flex-wrap:wrap;gap:8px}
  .chip{background:var(--card);border:1px solid var(--line);border-radius:999px;padding:5px 12px;font-size:14px;display:flex;gap:8px;align-items:center}
  .chip b{color:var(--accent)}
  table{width:100%;border-collapse:separate;border-spacing:0;background:var(--card);border:1px solid var(--line);border-radius:14px;overflow:hidden;font-size:14px}
  th{text-align:left;color:var(--muted);font-weight:600;font-size:12px;text-transform:uppercase;letter-spacing:.03em;padding:12px 14px;background:rgba(255,255,255,.02)}
  td{padding:11px 14px;border-top:1px solid var(--line)}
  tr:hover td{background:rgba(255,255,255,.03)}
  .tag{background:rgba(59,130,246,.16);color:#9cc2ff;padding:2px 9px;border-radius:6px;font-size:12px}
  .nowrap{white-space:nowrap}
  .muted{color:var(--muted)}
</style>
"""


def _chips(items) -> str:
    if not items:
        return "<span class='muted'>—</span>"
    return "".join(
        f"<span class='chip'>{escape(str(n) or 'direct')}<b>{c}</b></span>" for n, c in items
    )


def render_html(s: Stats) -> str:
    rows = "".join(
        f"<tr><td class='nowrap'>{escape(l.ts)}</td><td>{escape(l.name)}</td>"
        f"<td>{escape(l.city)}</td><td><span class='tag'>{escape(l.type)}</span></td>"
        f"<td class='nowrap'>{escape(l.contact)}</td><td>{escape(l.utm_source)}</td></tr>"
        for l in s.recent_leads
    ) or "<tr><td colspan='6' class='muted'>пока нет заявок</td></tr>"
    return (
        "<!doctype html><html lang='ru'><head><meta charset='utf-8'>"
        "<meta name='viewport' content='width=device-width, initial-scale=1'>"
        "<meta http-equiv='refresh' content='60'>"
        "<title>Русский Лайнап — дашборд</title>"
        + _STYLE
        + "</head><body><div class='wrap'>"
        "<header><h1>🏄 Русский Лайнап</h1><span class='sub'>дашборд бота</span></header>"
        "<div class='cards'>"
        f"<div class='card'><div class='label'>Старты</div><div class='num'>{s.starts_total}</div>"
        f"<div class='meta'>сегодня {s.starts_today} · 7 дней {s.starts_7d}</div></div>"
        f"<div class='card'><div class='label'>Заявки</div><div class='num'>{s.leads_total}</div>"
        f"<div class='conv'>start→lead {s.lead_conv()}</div></div>"
        f"<div class='card'><div class='label'>Промокоды</div><div class='num'>{s.promo_total}</div>"
        f"<div class='conv'>start→promo {s.promo_conv()}</div></div>"
        "</div>"
        f"<div class='section'><h2>Источники стартов</h2><div class='chips'>{_chips(s.starts_by_source)}</div></div>"
        f"<div class='section'><h2>Темы FAQ</h2><div class='chips'>{_chips(s.faq_by_topic)}</div></div>"
        "<div class='section'><h2>Последние заявки</h2>"
        "<table><thead><tr><th>Когда</th><th>Имя</th><th>Город</th><th>Тип</th>"
        f"<th>Контакт</th><th>Источник</th></tr></thead><tbody>{rows}</tbody></table></div>"
        "</div></body></html>"
    )


async def _index(request):
    return web.Response(text=render_html(await get_stats()), content_type="text/html")


def build_app() -> web.Application:
    app = web.Application(middlewares=[_auth_mw])
    app.router.add_get("/", _index)
    app.router.add_get("/health", _health)
    return app
