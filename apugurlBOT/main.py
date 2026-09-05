from __future__ import annotations

import asyncio
import logging
import re

from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from dotenv import load_dotenv

from burn import poll_burns
from config import Settings
from db import Database
from handlers import install_handlers
from hotwallet import HotWallet
from i18n import DEFAULT_LANGUAGE, t
from tonapi import TonApi
from wallet import WalletManager
from web_server import ConnectWebServer

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
                    lang = database.get_language(tg_id) or DEFAULT_LANGUAGE
                    if credited_amount > 0:
                        await bot.send_message(tg_id, t(lang, "deposit_credited", amount=credited_amount))
                    else:
                        await bot.send_message(tg_id, t(lang, "deposit_below_minimum"))
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
    bot = Bot(
        settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML, link_preview_is_disabled=True),
    )
    await backfill_full_names(bot, database)
    bot_username = (await bot.get_me()).username or ""
    web_server = ConnectWebServer(wallets, settings.tonconnect_manifest_url, settings.web_host, settings.web_port)
    await web_server.start()
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
            settings.required_channel_username,
            settings.required_group_username,
            web_server,
            settings.tonconnect_public_url,
            settings.pollinations_api_key,
            bot_username,
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
    burn_poll_task = asyncio.create_task(
        poll_burns(
            bot,
            database,
            tonapi,
            f"@{settings.burn_chat_username}",
            settings.jetton_master_address,
            settings.jetton_decimals,
            settings.burn_poll_interval_seconds,
            settings.burn_media_path,
        )
    )
    try:
        await dispatcher.start_polling(bot)
    finally:
        deposit_poll_task.cancel()
        burn_poll_task.cancel()
        await web_server.stop()
        await bot.session.close()
        database.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        pass
