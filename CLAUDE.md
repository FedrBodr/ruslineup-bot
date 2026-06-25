# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`ruslineup-bot` — Telegram bot for the «Русский Лайнап» brand: intake of leads, FAQ buttons,
partner promo codes, an AI fallback (FAQ + LLM), and end-to-end analytics. Built live as
episode #1 of the «от 0 до прода» show. Full spec lives in Linear (project «Русский Лайнап —
Telegram-бот», team FedrBodrCore, doc «ТЗ — Telegram-бот «Русский Лайнап» v1»).

## Commands

```bash
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env            # fill BOT_TOKEN, DATABASE_URL, etc.
python -m bot                   # run the bot (long-polling)

PYTHONPATH=. pytest -q          # all tests
PYTHONPATH=. pytest tests/test_promocode.py::test_format -v   # single test
```

## Architecture

- **Stack:** Python 3.11 · aiogram 3 (async, long-polling) · PostgreSQL · deployed on Amvera from git.
- **Entry point:** `bot/__main__.py` builds the `Dispatcher` and registers one router per feature.
  Each stage (FAQ, leads, promo, AI) adds its own router under `bot/handlers/` — keep them isolated.
- **Config:** `bot/config.py` — a frozen `Settings` dataclass reads everything from ENV via `python-dotenv`.
  Never read secrets or sensitive values anywhere else.
- **Metrics:** every user action funnels through `bot/services/metrics.log_event(...)` — the single
  logging chokepoint. It writes to the `events` table. `utm_source` arrives only at `/start`; it is
  persisted per-user (a `users` table) so later events can be attributed.
- **Storage:** PostgreSQL (async, `asyncpg`) is the source of truth. Tables map to the ТЗ's sheets:
  `events`, `leads`, `promo`, `tokens`, plus `users` for utm. **Note:** the Linear ТЗ still says Google
  Sheets — that was superseded by a Postgres decision; treat Postgres as authoritative.
- **Promo codes:** `bot/services/promocode.generate_code(user_id)` is deterministic (`sha1(user_id)`),
  so one user always gets the same code — idempotent without a storage lookup.

## Hard rules

- **Repo is PUBLIC.** No secrets or sensitive data in code, tests, or `knowledge.md`: BOT_TOKEN, DB
  credentials, the service-account key, prices, pre-order terms, partner discount, contacts — ENV only
  (`DATABASE_URL`, `BOT_TOKEN`, `ADMIN_CHAT_ID`, `PARTNER_NICK`, `BOARD_PRICE`, `PREORDER_TERMS`,
  `TESTDAY_PRICE`, `PARTNER_DISCOUNT`, `LLM_API_KEY`, `LLM_MODEL`). FAQ/knowledge text stays generic;
  concrete numbers are interpolated from ENV at runtime.
- **Plan before code; tests per stage (TDD).** Work is staged in Linear issues FED-239…FED-246.
- Commits and work happen in Russian («Этап N»), matching the team's convention.

## Git / push

This repo pushes to the **FedrBodr** GitHub account via a dedicated SSH alias —
`git@github-fedrbodr:FedrBodr/ruslineup-bot.git`, not the default `github.com` (that resolves to a
different account, `fedrbodrai`, which lacks write access). Verify with `ssh -T git@github-fedrbodr`
(expect "Hi FedrBodr!").
