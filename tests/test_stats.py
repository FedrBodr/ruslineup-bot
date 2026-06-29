import pytest
from unittest.mock import AsyncMock

import bot.services.db as db
import bot.services.stats as stats
from bot.services.stats import Stats, mask_contact


def test_mask_phone():
    assert mask_contact("+79265803341") == "+7926***3341"


def test_mask_short_and_empty():
    assert mask_contact("@neo") == "***"
    assert mask_contact("") == ""


def test_conversion_and_empty():
    s = Stats.empty()
    assert s.starts_total == 0
    assert s.lead_conv() == "—"  # деления на ноль нет
    s2 = Stats(starts_total=100, starts_today=0, starts_7d=0, starts_by_source=[],
               faq_by_topic=[], leads_total=25, leads_by_type=[], promo_total=10,
               recent_leads=[])
    assert s2.lead_conv() == "25%"
    assert s2.promo_conv() == "10%"


class FakeConn:
    def __init__(self, vals, rows):
        self.fetchval = AsyncMock(side_effect=vals)
        self.fetch = AsyncMock(side_effect=rows)


class FakePool:
    def __init__(self, conn):
        self._conn = conn

    def acquire(self):
        conn = self._conn

        class _Acq:
            async def __aenter__(s):
                return conn

            async def __aexit__(s, *a):
                return False

        return _Acq()


@pytest.mark.asyncio
async def test_get_stats_maps_and_masks():
    vals = [100, 10, 40, 25, 15, 4, 1]  # +conv_total, conv_uploaded
    rows = [
        [{"utm_source": "youtube", "c": 60}],
        [{"detail": "boards", "c": 30}],
        [{"type": "testday", "c": 20}],
        [{"ts": "2026-06-26 03:38", "name": "Дмитрий", "city": "Москва",
          "type": "preorder", "contact": "+79265803341", "utm_source": "direct"}],
        [{"target": "lead", "c": 3}, {"target": "promo", "c": 1}],  # conv_by_target
    ]
    db.set_pool(FakePool(FakeConn(vals, rows)))
    try:
        s = await stats.get_stats()
    finally:
        db.set_pool(None)
    assert s.starts_total == 100
    assert s.leads_total == 25
    assert s.promo_total == 15
    assert s.lead_conv() == "25%"
    assert s.starts_by_source == [("youtube", 60)]
    assert s.recent_leads[0].contact == "+7926***3341"  # замаскирован
    assert s.recent_leads[0].name == "Дмитрий"
    assert s.conv_total == 4 and s.conv_uploaded == 1
    assert s.conv_pending == 3
    assert s.conv_by_target == [("lead", 3), ("promo", 1)]


@pytest.mark.asyncio
async def test_get_stats_no_pool_is_empty():
    db.set_pool(None)
    s = await stats.get_stats()
    assert s.starts_total == 0
    assert s.recent_leads == []
