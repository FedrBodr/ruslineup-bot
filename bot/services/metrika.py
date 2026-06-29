"""Яндекс.Метрика оффлайн-конверсии (этап 7): батч-выгрузка по ClientID. ENV-gated."""
import csv
import io
import logging

import aiohttp

import bot.services.db as db
from bot.config import settings

logger = logging.getLogger("metrika")


def _build_csv(rows) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["ClientId", "Target", "DateTime", "Price", "Currency"])
    for r in rows:
        ts = r.get("ts")
        dt = int(ts.timestamp()) if ts is not None else 0
        writer.writerow([r["ym_cid"], r["target"], dt, r.get("price") or "", "RUB"])
    return buf.getvalue()


async def _upload(csv_text: str) -> bool:
    url = (f"https://api-metrika.yandex.net/management/v1/counter/{settings.ym_counter_id}"
           f"/offline_conversions/upload?client_id_type=CLIENT_ID")
    headers = {"Authorization": f"OAuth {settings.ym_oauth_token}"}
    data = aiohttp.FormData()
    data.add_field("file", csv_text, filename="conversions.csv", content_type="text/csv")
    try:
        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data, headers=headers) as resp:
                return resp.status < 300
    except Exception:
        logger.warning("Metrika upload failed (best-effort)", exc_info=True)
        return False


async def upload_pending() -> int:
    if not (settings.ym_oauth_token and settings.ym_counter_id):
        return 0
    rows = await db.fetch_pending_conversions()
    if not rows:
        return 0
    if await _upload(_build_csv(rows)):
        await db.mark_conversions_uploaded([r["id"] for r in rows])
        return len(rows)
    return 0
