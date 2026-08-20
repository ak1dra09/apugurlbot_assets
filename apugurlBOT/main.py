from __future__ import annotations

import asyncio
import logging
import re

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from config import Settings
from db import Database
from handlers import install_handlers
from hotwallet import HotWallet
from tonapi import TonApi
from wallet import WalletManager

DEPOSIT_COMMENT_PATTERN = re.compile(r"DEP(\d+)", re.IGNORECASE)


async def backfill_full_names(bot: Bot, database: Database) -> None:
    logger = logging.getLogger(__name__)
    for tg_id, username in database.get_users_missing_full_name():
        try:
            chat = await bot.get_chat(tg_id)
        except Exception as error:
            logger.info("Could not backfill full name for %s (@%s): %s", tg_id, username, error)
            continue
        if chat.full_name:
            database.upsert_telegram_user(tg_id, chat.username, chat.full_name)


async def poll_deposits(
    bot: Bot,
    database: Database,
    tonapi: TonApi,
    deposit_wallet_address: str,
    decimals: int,
    poll_interval: int,
) -> None:
    logger = logging.getLogger(__name__)
    while True:
        try:
            cursor = database.get_deposit_cursor()
            transfers = await tonapi.get_incoming_jetton_transfers(deposit_wallet_address, cursor)
            max_lt = cursor
            for transfer in transfers:
                lt = transfer.get("lt") or 0
                if lt > max_lt:
                    max_lt = lt
                match = DEPOSIT_COMMENT_PATTERN.search(transfer.get("comment") or "")
                if not match:
                    logger.info("Deposit event %s has no DEP<id> comment, skipping", transfer["event_id"])
                    continue
                tg_id = int(match.group(1))
                if not database.get_user(tg_id):
                    logger.info("Deposit event %s references unknown user %s, skipping", transfer["event_id"], tg_id)
                    continue
                raw_amount = transfer["raw_amount"]
                credited_amount = raw_amount // (10 ** decimals)
                if not database.credit_deposit(
                    transfer["event_id"], tg_id, raw_amount, credited_amount, transfer.get("sender_address")
                ):
                    continue
                try:
                    if credited_amount > 0:
                        await bot.send_message(
                            tg_id, f"Deposit received: {credited_amount} $APUGURL credited to your balance."
                        )
                    else:
                        await bot.send_message(
                            tg_id,
                            "A deposit was received but was below the minimum of 1 $APUGURL, so no balance was credited.",
                        )
                except Exception:
                    logger.info("Could not notify user %s about deposit", tg_id)
            if max_lt != cursor:
                database.set_deposit_cursor(max_lt)
        except Exception:
            logger.exception("Deposit polling iteration failed")
        await asyncio.sleep(poll_interval)


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    database = Database(settings.database_path)
    database.init_schema()
    tonapi = TonApi(settings.jetton_master_address, settings.tonapi_key)
    wallets = WalletManager(
        settings.tonconnect_manifest_url,
        database,
        tonapi,
        settings.internal_divisor,
        settings.tonconnect_public_url,
        settings.admin_ids,
    )
    hot_wallet = HotWallet(
        settings.hot_wallet_mnemonic,
        settings.jetton_master_address,
        settings.jetton_decimals,
        settings.tonapi_key,
    )
    bot = Bot(settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    await backfill_full_names(bot, database)
    dispatcher = Dispatcher()
    dispatcher.include_router(
        install_handlers(
            database,
            wallets,
            settings.rain_duration_seconds,
            settings.duel_result_delay_seconds,
            settings.duel_accept_timeout_seconds,
            settings.deposit_wallet_address,
            hot_wallet,
        )
    )
    deposit_poll_task = asyncio.create_task(
        poll_deposits(
            bot,
            database,
            tonapi,
            settings.deposit_wallet_address,
            settings.jetton_decimals,
            settings.deposit_poll_interval_seconds,
        )
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        deposit_poll_task.cancel()
        await bot.session.close()
        database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
