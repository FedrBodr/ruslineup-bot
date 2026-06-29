"""Слой агрегатов для дашборда (этап 8): воронка + последние заявки.

Read-only поверх пула asyncpg (тот же `db._pool`). Без пула — пустая сводка.
Контакт маскируется здесь же, чтобы PII не покидал слой данных в открытом виде.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import bot.services.db as db


def mask_contact(contact: str) -> str:
    c = (contact or "").strip()
    if len(c) >= 9:
        return f"{c[:5]}***{c[-4:]}"
    return "***" if c else ""


@dataclass
class Lead:
    ts: str
    name: str
    city: str
    type: str
    contact: str
    utm_source: str


@dataclass
class Stats:
    starts_total: int
    starts_today: int
    starts_7d: int
    starts_by_source: list
    faq_by_topic: list
    leads_total: int
    leads_by_type: list
    promo_total: int
    recent_leads: list
    conv_total: int = 0
    conv_uploaded: int = 0
    conv_by_target: list = field(default_factory=list)

    @classmethod
    def empty(cls) -> "Stats":
        return cls(0, 0, 0, [], [], 0, [], 0, [])

    @property
    def conv_pending(self) -> int:
        return max(0, self.conv_total - self.conv_uploaded)

    def _pct(self, n: int) -> str:
        if not self.starts_total:
            return "—"
        return f"{round(n * 100 / self.starts_total)}%"

    def lead_conv(self) -> str:
        return self._pct(self.leads_total)

    def promo_conv(self) -> str:
        return self._pct(self.promo_total)


async def get_stats() -> Stats:
    pool = db._pool
    if pool is None:
        return Stats.empty()
    async with pool.acquire() as conn:
        starts_total = await conn.fetchval(
            "SELECT count(*) FROM events WHERE event = 'start'") or 0
        starts_today = await conn.fetchval(
            "SELECT count(*) FROM events WHERE event='start' AND ts::date = now()::date") or 0
        starts_7d = await conn.fetchval(
            "SELECT count(*) FROM events WHERE event='start' AND ts >= now() - interval '7 days'") or 0
        leads_total = await conn.fetchval("SELECT count(*) FROM leads") or 0
        promo_total = await conn.fetchval("SELECT count(*) FROM promo") or 0

        src = await conn.fetch(
            "SELECT coalesce(utm_source,'') AS utm_source, count(*) AS c "
            "FROM events WHERE event='start' GROUP BY 1 ORDER BY c DESC LIMIT 10")
        faq = await conn.fetch(
            "SELECT coalesce(detail,'') AS detail, count(*) AS c "
            "FROM events WHERE event='faq_click' GROUP BY 1 ORDER BY c DESC LIMIT 10")
        by_type = await conn.fetch(
            "SELECT coalesce(type,'') AS type, count(*) AS c FROM leads GROUP BY 1 ORDER BY c DESC")
        recent = await conn.fetch(
            "SELECT to_char(ts,'YYYY-MM-DD HH24:MI') AS ts, coalesce(name,'') AS name, "
            "coalesce(city,'') AS city, coalesce(type,'') AS type, coalesce(contact,'') AS contact, "
            "coalesce(utm_source,'') AS utm_source FROM leads ORDER BY ts DESC LIMIT 20")

        conv_total = await conn.fetchval("SELECT count(*) FROM conversions") or 0
        conv_uploaded = await conn.fetchval(
            "SELECT count(*) FROM conversions WHERE uploaded = true") or 0
        conv_by_target = await conn.fetch(
            "SELECT coalesce(target,'') AS target, count(*) AS c "
            "FROM conversions GROUP BY 1 ORDER BY c DESC")

    return Stats(
        starts_total=starts_total,
        starts_today=starts_today,
        starts_7d=starts_7d,
        starts_by_source=[(r["utm_source"], r["c"]) for r in src],
        faq_by_topic=[(r["detail"], r["c"]) for r in faq],
        leads_total=leads_total,
        leads_by_type=[(r["type"], r["c"]) for r in by_type],
        promo_total=promo_total,
        recent_leads=[
            Lead(ts=r["ts"], name=r["name"], city=r["city"], type=r["type"],
                 contact=mask_contact(r["contact"]), utm_source=r["utm_source"])
            for r in recent
        ],
        conv_total=conv_total,
        conv_uploaded=conv_uploaded,
        conv_by_target=[(r["target"], r["c"]) for r in conv_by_target],
    )
