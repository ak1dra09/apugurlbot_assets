from __future__ import annotations

import asyncio
import logging
import os

from aiogram import Bot
from aiogram.types import FSInputFile

from db import Database
from tonapi import TonApi

logger = logging.getLogger(__name__)

# TON's well-known unspendable zero address (workchain 0, 32 zero-byte hash).
ZERO_ADDRESS = "0:0000000000000000000000000000000000000000000000000000000000000000"

VIDEO_EXTENSIONS = (".mp4", ".mov", ".avi", ".webm", ".mkv")


def _format_amount(raw_amount: int, decimals: int) -> str:
    value = raw_amount // (10 ** decimals)
    return f"{value:,}".replace(",", " ")


def _build_message(
    burned_now_raw: int,
    burned_total_raw: int,
    total_supply_raw: int,
    decimals: int,
    jetton_master_address: str,
) -> str:
    burned_now = _format_amount(burned_now_raw, decimals)
    burned_total = _format_amount(burned_total_raw, decimals)
    percent = (burned_total_raw / total_supply_raw * 100) if total_supply_raw else 0.0
    return (
        "Let it burn! $APUGURL 🎀\n"
        f"Burned now: {burned_now} APUGURL\n"
        f"Burned total: {burned_total} APUGURL \n"
        f"{percent:.2f} % of supply burned "
        f"(https://tonviewer.com/{jetton_master_address}?section=holders) 🔥"
    )


async def _send_burn_message(bot: Bot, chat_id: str, text: str, media_path: str) -> None:
    if media_path and os.path.isfile(media_path):
        file = FSInputFile(media_path)
        if media_path.lower().endswith(VIDEO_EXTENSIONS):
            await bot.send_video(chat_id, file, caption=text)
        else:
            await bot.send_photo(chat_id, file, caption=text)
    else:
        await bot.send_message(chat_id, text)


async def poll_burns(
    bot: Bot,
    database: Database,
    tonapi: TonApi,
    chat_id: str,
    jetton_master_address: str,
    decimals: int,
    poll_interval: int,
    media_path: str,
) -> None:
    while True:
        try:
            cursor = database.get_burn_cursor()
            transfers = await tonapi.get_incoming_jetton_transfers(ZERO_ADDRESS, cursor)
            max_lt = cursor
            for transfer in transfers:
                lt = transfer.get("lt") or 0
                if lt > max_lt:
                    max_lt = lt
                raw_amount = transfer["raw_amount"]
                if raw_amount <= 0:
                    continue
                if not database.record_burn_event(transfer["event_id"], raw_amount, transfer.get("sender_address")):
                    continue
                try:
                    total_supply_raw = await tonapi.get_jetton_total_supply()
                except Exception:
                    logger.exception("Failed to fetch jetton total supply for burn message")
                    total_supply_raw = 0
                total_burned_raw = database.get_total_burned_raw()
                text = _build_message(raw_amount, total_burned_raw, total_supply_raw, decimals, jetton_master_address)
                try:
                    await _send_burn_message(bot, chat_id, text, media_path)
                except Exception:
                    logger.exception("Could not send burn notification")
            if max_lt != cursor:
                database.set_burn_cursor(max_lt)
        except Exception:
            logger.exception("Burn polling iteration failed")
        await asyncio.sleep(poll_interval)
