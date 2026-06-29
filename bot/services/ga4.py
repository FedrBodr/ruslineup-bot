"""GA4 Measurement Protocol (этап 7): серверные события бота. Best-effort, ENV-gated."""
import logging

import aiohttp

from bot.config import settings

logger = logging.getLogger("ga4")
_COLLECT = "https://www.google-analytics.com/mp/collect"


async def _post(url: str, payload: dict) -> None:
    async with aiohttp.ClientSession() as session:
        async with session.post(url, json=payload) as resp:
            await resp.read()


async def send_event(client_id: str, name: str, params: dict | None = None) -> None:
    if not (settings.ga4_measurement_id and settings.ga4_api_secret and client_id):
        return
    url = (f"{_COLLECT}?measurement_id={settings.ga4_measurement_id}"
           f"&api_secret={settings.ga4_api_secret}")
    payload = {"client_id": client_id, "events": [{"name": name, "params": params or {}}]}
    try:
        await _post(url, payload)
    except Exception:
        logger.warning("GA4 send_event failed (best-effort)", exc_info=True)
