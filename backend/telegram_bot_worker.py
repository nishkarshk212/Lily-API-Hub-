"""Standalone long-polling CLI worker reusing Beta API Hub's telegram_service engine.

Usage:
  python telegram_bot_worker.py                 # Poll all active polling bots from DB
  python telegram_bot_worker.py --all-bots      # Force-poll all active bots in DB
"""

import argparse
import asyncio
import sys

from sqlalchemy import select

from app.core.database import SessionLocal, ensure_db_ready
from app.models.telegram import TelegramBot
from app.services.telegram_service import TelegramApiError, poll_bot_updates_once


async def run_worker(poll_all: bool = False) -> None:
    ok, err = ensure_db_ready()
    if not ok:
        print(f"Database init failed: {err}", file=sys.stderr)
        sys.exit(1)

    print("Beta API Hub Telegram Bot Worker started. Press Ctrl+C to stop.")
    while True:
        try:
            with SessionLocal() as db:
                query = select(TelegramBot).where(TelegramBot.is_active.is_(True))
                if not poll_all:
                    query = query.where(TelegramBot.connection_mode == "polling")
                bots = db.scalars(query).all()
                for bot in bots:
                    try:
                        count = await poll_bot_updates_once(db, bot, timeout_sec=5)
                        if count:
                            print(f"[@{bot.bot_username}] processed {count} update(s)")
                    except TelegramApiError as exc:
                        bot.last_error = str(exc)[:500]
                        db.commit()
                        print(f"[@{bot.bot_username}] Telegram API warning: {exc}", file=sys.stderr)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            print(f"[worker_error] {type(exc).__name__}: {exc}", file=sys.stderr)
        await asyncio.sleep(2.0)


def main() -> None:
    parser = argparse.ArgumentParser(description="Beta API Hub Telegram Bot Worker")
    parser.add_argument("--all-bots", action="store_true", help="Poll all active bots regardless of mode")
    args = parser.parse_args()
    try:
        asyncio.run(run_worker(poll_all=args.all_bots))
    except KeyboardInterrupt:
        print("\nTelegram worker stopped cleanly.")


if __name__ == "__main__":
    main()
