from __future__ import annotations

import asyncio
import html
import logging
import random
import re
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.enums import ChatMemberStatus, ChatType
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.types import BufferedInputFile, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from ton_core import Address

from db import Database
from hotwallet import HotWallet, HotWalletError
from i18n import DEFAULT_LANGUAGE, LANGUAGE_NAMES, SUPPORTED_LANGUAGES, t
from imagegen import ImageGenError, transform_to_apu
from wallet import WalletManager
from web_server import ConnectWebServer

logger = logging.getLogger(__name__)

TELEGRAM_SERVICE_ACCOUNT_ID = 777000
PROMO_CODE_PATTERN = re.compile(r"[A-Za-z0-9_]{3,32}")


class MenuStates(StatesGroup):
    waiting_withdraw = State()
    waiting_create_promo = State()
    waiting_redeem_promo = State()


def is_trackable_user(user) -> bool:
    return not user.is_bot and user.id != TELEGRAM_SERVICE_ACCOUNT_ID


def is_bot_username(username: str) -> bool:
    # Telegram requires every bot username to end in "bot" (case-insensitive).
    return username.lstrip("@").lower().endswith("bot")


def parse_amount(value: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid_amount") from error
    if amount != amount.to_integral_value() or amount <= 0:
        raise ValueError("invalid_amount")
    return int(amount)


def parse_nonnegative_amount(value: str) -> int:
    try:
        amount = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("invalid_amount") from error
    if amount != amount.to_integral_value() or amount < 0:
        raise ValueError("invalid_amount")
    return int(amount)


def user_name(message: Message) -> str | None:
    return message.from_user.username if message.from_user else None


def user_full_name(message: Message) -> str | None:
    return message.from_user.full_name if message.from_user else None


def mention(tg_id: int, username: str | None, full_name: str | None = None) -> str:
    label = full_name or (f"@{username}" if username else str(tg_id))
    # t.me links work everywhere; tg://user?id= only resolves in chats where the
    # client already knows the target (e.g. a shared group), so it's a fallback.
    href = f"https://t.me/{username}" if username else f"tg://user?id={tg_id}"
    return f'<a href="{href}">{html.escape(label)}</a>'


async def ensure_username_user(database: Database, message: Message, username: str):
    if is_bot_username(username):
        return None
    user = database.find_by_username(username)
    if user:
        return user
    try:
        chat = await message.bot.get_chat(username)
    except Exception:
        return None
    if chat.type != ChatType.PRIVATE:
        return None
    database.upsert_telegram_user(chat.id, chat.username, chat.full_name)
    return database.get_user(chat.id)


def duel_keyboard(duel_id: int, lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text=t(lang, "duel_accept_button"), callback_data=f"duel_accept:{duel_id}"),
        InlineKeyboardButton(text=t(lang, "duel_decline_button"), callback_data=f"duel_decline:{duel_id}"),
    ]])


def withdraw_keyboard(withdrawal_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Approve", callback_data=f"withdraw_approve:{withdrawal_id}"),
        InlineKeyboardButton(text="Reject", callback_data=f"withdraw_reject:{withdrawal_id}"),
    ]])


def parse_ton_address(value: str) -> Address | None:
    try:
        return Address(value)
    except Exception:
        return None


DICE_BET_PRESETS = (50, 100, 500, 1000)
DICE_PARITY_PAYOUT_NUM = 9
DICE_PARITY_PAYOUT_DEN = 5
DICE_NUMBER_MULTIPLIER = 5


def dice_amount_keyboard(initiator_id: int) -> InlineKeyboardMarkup:
    buttons = [
        InlineKeyboardButton(text=f"🎲 {amount}", callback_data=f"dice_amount:{initiator_id}:{amount}")
        for amount in DICE_BET_PRESETS
    ]
    return InlineKeyboardMarkup(inline_keyboard=[buttons])


def dice_choice_keyboard(initiator_id: int, amount: int, lang: str) -> InlineKeyboardMarkup:
    def button(label: str, choice: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=label, callback_data=f"dice_choice:{initiator_id}:{amount}:{choice}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [button(t(lang, "dice_even"), "even"), button(t(lang, "dice_odd"), "odd")],
        [button(f"{n} ×5.0", str(n)) for n in (1, 2, 3)],
        [button(f"{n} ×5.0", str(n)) for n in (4, 5, 6)],
    ])


def dice_payout(amount: int, choice: str) -> int:
    if choice in ("even", "odd"):
        return amount * DICE_PARITY_PAYOUT_NUM // DICE_PARITY_PAYOUT_DEN
    return amount * DICE_NUMBER_MULTIPLIER


def dice_choice_label(lang: str, choice: str) -> str:
    if choice == "even":
        return t(lang, "dice_even")
    if choice == "odd":
        return t(lang, "dice_odd")
    return f"{choice} ×{DICE_NUMBER_MULTIPLIER}.0"


MEMBERSHIP_OK_STATUSES = {
    ChatMemberStatus.CREATOR,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
    ChatMemberStatus.RESTRICTED,
}


# Users must also be a member of the required group, not just the channel.
# Set back to False to only require the channel.
REQUIRE_GROUP_MEMBERSHIP = True


async def is_chat_member(bot, chat_username: str, user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(f"@{chat_username}", user_id)
    except Exception:
        return False
    return member.status in MEMBERSHIP_OK_STATUSES


async def passes_membership_requirements(bot, user_id: int, channel_username: str, group_username: str) -> bool:
    if not await is_chat_member(bot, channel_username, user_id):
        return False
    if REQUIRE_GROUP_MEMBERSHIP and not await is_chat_member(bot, group_username, user_id):
        return False
    return True


MEMBERSHIP_CACHE_HOURS = 24


def is_membership_verification_fresh(verified_at: str | None) -> bool:
    if not verified_at:
        return False
    try:
        verified_time = datetime.strptime(verified_at, "%Y-%m-%d %H:%M:%S")
    except ValueError:
        return False
    return datetime.utcnow() - verified_time < timedelta(hours=MEMBERSHIP_CACHE_HOURS)


def membership_keyboard(channel_username: str, group_username: str, lang: str) -> InlineKeyboardMarkup:
    buttons = [[InlineKeyboardButton(text="📢 Channel", url=f"https://t.me/{channel_username}")]]
    if REQUIRE_GROUP_MEMBERSHIP:
        buttons.append([InlineKeyboardButton(text="👥 Group", url=f"https://t.me/{group_username}")])
    buttons.append([InlineKeyboardButton(text="✅ Check", callback_data="check_membership")])
    buttons.append([InlineKeyboardButton(text=t(lang, "language_button"), callback_data="show_language")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)


def main_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "menu_balance"), callback_data="menu:balance"),
         InlineKeyboardButton(text=t(lang, "menu_top"), callback_data="menu:top")],
        [InlineKeyboardButton(text=t(lang, "menu_deposit"), callback_data="menu:deposit"),
         InlineKeyboardButton(text=t(lang, "menu_withdraw"), callback_data="menu:withdraw")],
        [InlineKeyboardButton(text=t(lang, "menu_promo"), callback_data="menu:promo"),
         InlineKeyboardButton(text=t(lang, "menu_dice"), callback_data="menu:dice")],
        [InlineKeyboardButton(text=t(lang, "language_button"), callback_data="show_language"),
         InlineKeyboardButton(text=t(lang, "menu_info"), callback_data="menu:info")],
    ])


def promo_menu_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "promo_menu_create"), callback_data="promo_menu:create")],
        [InlineKeyboardButton(text=t(lang, "promo_menu_redeem"), callback_data="promo_menu:redeem")],
        [InlineKeyboardButton(text=t(lang, "promo_menu_mine"), callback_data="promo_menu:mine")],
        [InlineKeyboardButton(text=t(lang, "menu_back"), callback_data="menu:main")],
    ])


def cancel_keyboard(lang: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=t(lang, "menu_cancel"), callback_data="menu:cancel")],
    ])


def language_keyboard() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text=LANGUAGE_NAMES[code], callback_data=f"lang:{code}") for code in SUPPORTED_LANGUAGES],
    ])


def install_handlers(
    database: Database,
    wallets: WalletManager,
    rain_duration_seconds: int = 30,
    duel_result_delay_seconds: int = 3,
    duel_accept_timeout_seconds: int = 60,
    deposit_wallet_address: str = "",
    hot_wallet: HotWallet | None = None,
    required_channel_username: str = "ApuGurlOnTon",
    required_group_username: str = "ApugurlCHAT",
    web_server: ConnectWebServer | None = None,
    public_base_url: str = "",
    pollinations_api_key: str = "",
    bot_username: str = "",
) -> Router:
    router = Router()

    def get_lang(user_id: int) -> str:
        return database.get_language(user_id) or DEFAULT_LANGUAGE

    async def user_passes_requirements(bot, user_id: int) -> bool:
        if is_membership_verification_fresh(database.get_membership_verified_at(user_id)):
            return True
        passed = await passes_membership_requirements(bot, user_id, required_channel_username, required_group_username)
        if passed:
            database.mark_membership_verified(user_id)
        return passed

    def gate_prompt_keyboard(lang: str) -> InlineKeyboardMarkup:
        return membership_keyboard(required_channel_username, required_group_username, lang)

    def gate_prompt_text(lang: str) -> str:
        key = "gate_prompt_channel_and_group" if REQUIRE_GROUP_MEMBERSHIP else "gate_prompt_channel_only"
        return t(lang, key)

    @router.message.middleware()
    async def membership_gate_message(handler, event: Message, data: dict):
        user = event.from_user
        if not user or user.is_bot:
            return await handler(event, data)
        text = (event.text or "").strip()
        if not text or not (text.startswith("/") or text.startswith("+")):
            return await handler(event, data)
        command_name = text.split()[0].split("@")[0].lower()
        if command_name in ("/start", "/language"):
            return await handler(event, data)
        if await user_passes_requirements(event.bot, user.id):
            return await handler(event, data)
        lang = get_lang(user.id)
        try:
            await event.bot.send_message(user.id, gate_prompt_text(lang), reply_markup=gate_prompt_keyboard(lang))
        except Exception:
            logger.info("Could not DM membership gate prompt to %s", user.id)
        return None

    @router.callback_query.middleware()
    async def membership_gate_callback(handler, event: CallbackQuery, data: dict):
        user = event.from_user
        if not user or user.is_bot:
            return await handler(event, data)
        if event.data == "check_membership" or event.data == "show_language" or (event.data or "").startswith("lang:"):
            return await handler(event, data)
        if await user_passes_requirements(event.bot, user.id):
            return await handler(event, data)
        lang = get_lang(user.id)
        await event.answer(t(lang, "gate_check_dm"), show_alert=True)
        try:
            await event.bot.send_message(user.id, gate_prompt_text(lang), reply_markup=gate_prompt_keyboard(lang))
        except Exception:
            logger.info("Could not DM membership gate prompt to %s", user.id)
        return None

    @router.message(Command("language"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def language_command(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        lang = get_lang(message.from_user.id)
        await message.answer(t(lang, "language_prompt"), reply_markup=language_keyboard())

    @router.callback_query(lambda query: query.data == "show_language")
    async def show_language_action(query: CallbackQuery) -> None:
        assert query.from_user
        if not query.message or query.message.chat.type != ChatType.PRIVATE:
            await query.answer()
            return
        lang = get_lang(query.from_user.id)
        await query.answer()
        await query.message.answer(t(lang, "language_prompt"), reply_markup=language_keyboard())

    @router.callback_query(lambda query: query.data and query.data.startswith("lang:"))
    async def set_language_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        if query.message.chat.type != ChatType.PRIVATE:
            await query.answer()
            return
        code = query.data.split(":", 1)[1]
        if code not in SUPPORTED_LANGUAGES:
            await query.answer()
            return
        database.set_language(query.from_user.id, code)
        await query.answer(t(code, "language_set"))
        user = database.get_user(query.from_user.id)
        try:
            await query.message.edit_text(
                t(code, "welcome_balance", balance=user.balance if user else 0),
                reply_markup=main_menu_keyboard(code),
            )
        except Exception:
            pass

    @router.callback_query(lambda query: query.data and query.data.startswith("menu:"))
    async def menu_action(query: CallbackQuery, state: FSMContext) -> None:
        assert query.from_user and query.data and query.message
        action = query.data.split(":", 1)[1]
        lang = get_lang(query.from_user.id)

        if action in ("main", "cancel"):
            if action == "cancel":
                await state.clear()
            await query.answer(t(lang, "cancelled") if action == "cancel" else None)
            user = database.get_user(query.from_user.id)
            await query.message.edit_text(
                t(lang, "welcome_balance", balance=user.balance if user else 0),
                reply_markup=main_menu_keyboard(lang),
            )
            return

        if action == "balance":
            await query.answer()
            user = database.get_user(query.from_user.id)
            await query.message.answer(t(lang, "balance_text", balance=user.balance if user else 0))
            return

        if action == "top":
            await query.answer()
            users = database.get_leaderboard(10)
            if not users:
                await query.message.answer(t(lang, "leaderboard_empty"))
                return
            lines = [t(lang, "leaderboard_header")]
            for position, top_user in enumerate(users, start=1):
                label = mention(top_user.tg_id, top_user.username, top_user.full_name)
                lines.append(f"{position}. {label} - {top_user.balance} $APUGURL")
            await query.message.answer("\n".join(lines))
            return

        if action == "deposit":
            await query.answer()
            user = database.get_user(query.from_user.id)
            comment = f"DEP{query.from_user.id}"
            await query.message.answer(
                t(lang, "deposit_info", balance=user.balance if user else 0, wallet=deposit_wallet_address, comment=comment)
            )
            return

        if action == "withdraw":
            await query.answer()
            await state.set_state(MenuStates.waiting_withdraw)
            await query.message.answer(t(lang, "withdraw_prompt"), reply_markup=cancel_keyboard(lang))
            return

        if action == "promo":
            await query.answer()
            await query.message.edit_text(t(lang, "promo_menu_title"), reply_markup=promo_menu_keyboard(lang))
            return

        if action == "dice":
            await query.answer()
            await query.message.answer(t(lang, "dice_usage"), reply_markup=dice_amount_keyboard(query.from_user.id))
            return

        if action == "info":
            await query.answer()
            await query.message.answer(t(lang, "info_help"))
            return

        await query.answer()

    @router.callback_query(lambda query: query.data and query.data.startswith("promo_menu:"))
    async def promo_menu_action(query: CallbackQuery, state: FSMContext) -> None:
        assert query.from_user and query.data and query.message
        action = query.data.split(":", 1)[1]
        lang = get_lang(query.from_user.id)

        if action == "create":
            await query.answer()
            await state.set_state(MenuStates.waiting_create_promo)
            await query.message.answer(t(lang, "promo_create_prompt"), reply_markup=cancel_keyboard(lang))
            return

        if action == "redeem":
            await query.answer()
            await state.set_state(MenuStates.waiting_redeem_promo)
            await query.message.answer(t(lang, "promo_redeem_prompt"), reply_markup=cancel_keyboard(lang))
            return

        if action == "mine":
            await query.answer()
            database.upsert_telegram_user(query.from_user.id, query.from_user.username, query.from_user.full_name)
            await perform_my_promo(query.message, query.from_user.id)
            return

        await query.answer()

    @router.message(MenuStates.waiting_withdraw, lambda message: bool(message.text) and not message.text.startswith(("/", "+")))
    async def handle_withdraw_input(message: Message, state: FSMContext) -> None:
        await state.clear()
        await perform_withdraw(message, message.text.strip().split())

    @router.message(MenuStates.waiting_create_promo, lambda message: bool(message.text) and not message.text.startswith(("/", "+")))
    async def handle_create_promo_input(message: Message, state: FSMContext) -> None:
        await state.clear()
        await perform_create_promo(message, message.text.strip().split())

    @router.message(MenuStates.waiting_redeem_promo, lambda message: bool(message.text) and not message.text.startswith(("/", "+")))
    async def handle_redeem_promo_input(message: Message, state: FSMContext) -> None:
        await state.clear()
        await perform_redeem_promo(message, message.text.strip().split()[0])

    async def expire_duel(bot, chat_id: int, message_id: int, duel_id: int, message_thread_id: int | None) -> None:
        await asyncio.sleep(duel_accept_timeout_seconds)
        duel = database.get_duel(duel_id)
        if not duel or duel["status"] != "pending":
            return
        try:
            database.cancel_duel(duel_id)
        except ValueError:
            return
        try:
            await bot.edit_message_reply_markup(chat_id=chat_id, message_id=message_id, reply_markup=None)
            await bot.send_message(chat_id, t(DEFAULT_LANGUAGE, "duel_expired"), message_thread_id=message_thread_id)
        except Exception:
            pass

    @router.message(Command("start"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def start(message: Message, state: FSMContext) -> None:
        assert message.from_user
        await state.clear()
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        lang = get_lang(message.from_user.id)
        if not await user_passes_requirements(message.bot, message.from_user.id):
            await message.answer(gate_prompt_text(lang), reply_markup=gate_prompt_keyboard(lang))
            return
        user = database.get_user(message.from_user.id)
        await message.answer(
            t(lang, "welcome_balance", balance=user.balance if user else 0),
            reply_markup=main_menu_keyboard(lang),
        )

    @router.callback_query(lambda query: query.data == "check_membership")
    async def check_membership_action(query: CallbackQuery) -> None:
        assert query.from_user and query.message
        lang = get_lang(query.from_user.id)
        if not await user_passes_requirements(query.bot, query.from_user.id):
            unmet_key = "gate_unmet_channel_and_group" if REQUIRE_GROUP_MEMBERSHIP else "gate_unmet_channel_only"
            await query.answer(t(lang, unmet_key), show_alert=True)
            return
        await query.answer(t(lang, "access_granted"))
        user = database.get_user(query.from_user.id)
        await query.message.edit_text(
            t(lang, "welcome_balance", balance=user.balance if user else 0),
            reply_markup=main_menu_keyboard(lang),
        )

    @router.message(Command("balance"))
    async def balance(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        user = database.get_user(message.from_user.id)
        await message.answer(t(get_lang(message.from_user.id), "balance_text", balance=user.balance if user else 0))

    @router.message(Command("deposit"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def deposit(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        user = database.get_user(message.from_user.id)
        comment = f"DEP{message.from_user.id}"
        await message.answer(
            t(
                get_lang(message.from_user.id),
                "deposit_info",
                balance=user.balance if user else 0,
                wallet=deposit_wallet_address,
                comment=comment,
            )
        )

    async def perform_withdraw(message: Message, parts: list[str]) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        lang = get_lang(message.from_user.id)
        if len(parts) != 2:
            await message.answer(t(lang, "withdraw_usage"))
            return
        address_text, amount_text = parts
        address = parse_ton_address(address_text)
        if address is None:
            await message.answer(t(lang, "withdraw_invalid_address"))
            return
        try:
            amount = parse_amount(amount_text)
            withdrawal_id = database.create_withdrawal(message.from_user.id, amount, address.to_str())
        except ValueError as error:
            errors = {
                "invalid_amount": t(lang, "error_invalid_amount"),
                "insufficient_balance": t(lang, "error_insufficient_balance"),
            }
            await message.answer(errors.get(str(error), t(lang, "withdraw_create_failed")))
            return
        await message.answer(t(lang, "withdraw_submitted", id=withdrawal_id, amount=amount, address=address.to_str()))
        requester_label = mention(message.from_user.id, user_name(message), user_full_name(message))
        for admin_id in wallets.admin_ids:
            try:
                await message.bot.send_message(
                    admin_id,
                    f"Withdrawal request #{withdrawal_id}\n"
                    f"From: {requester_label}\n"
                    f"Amount: {amount} $APUGURL\n"
                    f"Destination: {address.to_str()}",
                    reply_markup=withdraw_keyboard(withdrawal_id),
                )
            except Exception:
                logger.info("Could not notify admin %s about withdrawal #%s", admin_id, withdrawal_id)

    @router.message(Command("withdraw"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def withdraw(message: Message, command: CommandObject) -> None:
        await perform_withdraw(message, (command.args or "").split())

    @router.callback_query(lambda query: query.data and query.data.startswith("withdraw_"))
    async def withdraw_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        if query.from_user.id not in wallets.admin_ids:
            await query.answer("Only admins can do this.", show_alert=True)
            return
        action, raw_id = query.data.split(":", 1)
        withdrawal_id = int(raw_id)
        withdrawal = database.get_withdrawal(withdrawal_id)
        if not withdrawal:
            await query.answer("Withdrawal not found.", show_alert=True)
            return
        if withdrawal["status"] != "pending":
            await query.answer("This withdrawal was already processed.", show_alert=True)
            return

        if action == "withdraw_reject":
            database.resolve_withdrawal(withdrawal_id, "rejected")
            await query.message.edit_reply_markup(reply_markup=None)
            await query.answer("Rejected.")
            try:
                await query.bot.send_message(
                    withdrawal["tg_id"],
                    t(get_lang(withdrawal["tg_id"]), "withdraw_rejected_user", id=withdrawal_id),
                )
            except Exception:
                logger.info("Could not notify user %s about rejected withdrawal #%s", withdrawal["tg_id"], withdrawal_id)
            return

        await query.answer("Sending...")
        await query.message.edit_reply_markup(reply_markup=None)
        if hot_wallet is None:
            database.resolve_withdrawal(withdrawal_id, "failed")
            await query.message.answer("Hot wallet is not configured. Withdrawal failed, balance refunded.")
            return
        try:
            tx_hash = await hot_wallet.send_jetton(withdrawal["destination_address"], withdrawal["amount"])
        except HotWalletError as error:
            database.resolve_withdrawal(withdrawal_id, "failed")
            await query.message.answer(f"Withdrawal #{withdrawal_id} failed: {error}. Balance refunded.")
            try:
                await query.bot.send_message(
                    withdrawal["tg_id"],
                    t(get_lang(withdrawal["tg_id"]), "withdraw_failed_user", id=withdrawal_id),
                )
            except Exception:
                logger.info("Could not notify user %s about failed withdrawal #%s", withdrawal["tg_id"], withdrawal_id)
            return
        database.resolve_withdrawal(withdrawal_id, "sent", tx_hash)
        await query.message.answer(f"Withdrawal #{withdrawal_id} sent. Tx: {tx_hash}")
        try:
            await query.bot.send_message(
                withdrawal["tg_id"],
                t(get_lang(withdrawal["tg_id"]), "withdraw_sent_user", amount=withdrawal["amount"], tx=tx_hash),
            )
        except Exception:
            logger.info("Could not notify user %s about sent withdrawal #%s", withdrawal["tg_id"], withdrawal_id)

    @router.message(Command("top"))
    async def leaderboard(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        users = database.get_leaderboard(10)
        if not users:
            await message.answer(t(lang, "leaderboard_empty"))
            return
        lines = [t(lang, "leaderboard_header")]
        for position, user in enumerate(users, start=1):
            label = mention(user.tg_id, user.username, user.full_name)
            lines.append(f"{position}. {label} - {user.balance} $APUGURL")
        await message.answer("\n".join(lines))

    @router.message(Command("top_gamble"))
    async def top_gamble(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        rows = database.get_top_gamblers(10)
        if not rows:
            await message.answer(t(lang, "top_gamblers_empty"))
            return
        lines = [t(lang, "top_gamblers_header")]
        for position, row in enumerate(rows, start=1):
            label = mention(row["tg_id"], row["username"], row["full_name"])
            lines.append(t(lang, "top_list_line", position=position, label=label, total=row["total"]))
        await message.answer("\n".join(lines))

    @router.message(Command("top_patrons"))
    async def top_patrons(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        rows = database.get_top_patrons(10)
        if not rows:
            await message.answer(t(lang, "top_patrons_empty"))
            return
        lines = [t(lang, "top_patrons_header")]
        for position, row in enumerate(rows, start=1):
            label = mention(row["tg_id"], row["username"], row["full_name"])
            lines.append(t(lang, "top_list_line", position=position, label=label, total=row["total"]))
        await message.answer("\n".join(lines))

    @router.message(Command("top_talk"))
    async def top_talk(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        rows = database.get_top_talkers(10)
        if not rows:
            await message.answer(t(lang, "top_talkers_empty"))
            return
        lines = [t(lang, "top_talkers_header")]
        for position, row in enumerate(rows, start=1):
            label = mention(row["tg_id"], row["username"], row["full_name"])
            lines.append(t(lang, "top_talkers_line", position=position, label=label, total=row["total"]))
        await message.answer("\n".join(lines))

    @router.message(Command("info"))
    async def info(message: Message) -> None:
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and message.from_user:
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id) if message.from_user else DEFAULT_LANGUAGE
        await message.answer(t(lang, "info_help"))

    @router.message(Command("admin_add"))
    async def admin_add(message: Message, command: CommandObject) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE or message.from_user.id not in wallets.admin_ids:
            return
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        parts = (command.args or "").split()
        if len(parts) != 1:
            await message.answer("Usage: /admin_add amount")
            return
        try:
            amount = parse_amount(parts[0])
            database.add_balance(message.from_user.id, amount)
        except ValueError as error:
            if str(error) == "invalid_amount":
                await message.answer("Amount must be a positive whole number.")
                return
            await message.answer("Could not add $APUGURL to the admin balance.")
            return
        user = database.get_user(message.from_user.id)
        await message.answer(f"Added {amount} $APUGURL. Your balance: {user.balance if user else 0} $APUGURL.")

    @router.message(Command("set"))
    async def set_balance_command(message: Message, command: CommandObject) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE or message.from_user.id not in wallets.admin_ids:
            return
        lang = get_lang(message.from_user.id)
        parts = (command.args or "").split()
        if len(parts) != 2 or not parts[0].startswith("@"):
            await message.answer(t(lang, "set_usage"))
            return
        try:
            amount = parse_nonnegative_amount(parts[1])
        except ValueError:
            await message.answer(t(lang, "error_invalid_amount"))
            return
        target = await ensure_username_user(database, message, parts[0])
        if not target:
            await message.answer(t(lang, "set_user_not_found"))
            return
        database.set_balance(target.tg_id, amount)
        label = mention(target.tg_id, target.username, target.full_name)
        await message.answer(t(lang, "set_success", user=label, amount=amount))

    @router.message(Command("list"))
    async def list_users(message: Message) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE or message.from_user.id not in wallets.admin_ids:
            return
        users = database.get_all_users()
        if not users:
            await message.answer("No users registered yet.")
            return
        lines = [f"{index}. {mention(user.tg_id, user.username, user.full_name)} - {user.balance} $APUGURL" for index, user in enumerate(users, start=1)]
        chunk = f"Users ({len(users)}):"
        for line in lines:
            if len(chunk) + 1 + len(line) > 3500:
                await message.answer(chunk)
                chunk = line
            else:
                chunk += "\n" + line
        await message.answer(chunk)

    @router.message(Command("statistic"))
    async def statistic(message: Message) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE or message.from_user.id not in wallets.admin_ids:
            return
        stats = database.get_statistics()
        await message.answer(
            f"Total deposits: {stats['total_deposits']} $APUGURL\n"
            f"Total withdrawals: {stats['total_withdrawals']} $APUGURL\n"
            f"Total user balances: {stats['total_balance']} $APUGURL"
        )

    async def perform_create_promo(message: Message, parts: list[str]) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        lang = get_lang(message.from_user.id)
        if len(parts) != 3:
            await message.answer(t(lang, "promo_usage"))
            return
        code, uses_raw, amount_raw = parts
        if not PROMO_CODE_PATTERN.fullmatch(code):
            await message.answer(t(lang, "promo_name_invalid"))
            return
        try:
            uses = parse_amount(uses_raw)
            amount_per_use = parse_amount(amount_raw)
            database.create_promo(message.from_user.id, code, uses, amount_per_use)
        except ValueError as error:
            errors = {
                "invalid_amount": t(lang, "promo_error_amount"),
                "promo_exists": t(lang, "promo_error_exists"),
                "insufficient_balance": t(lang, "promo_error_funds"),
            }
            await message.answer(errors.get(str(error), t(lang, "promo_create_failed")))
            return
        total = uses * amount_per_use
        await message.answer(t(lang, "promo_created", code=code, uses=uses, amount=amount_per_use, total=total))

    @router.message(Command("create_promo"))
    async def create_promo(message: Message, command: CommandObject) -> None:
        if message.chat.type != ChatType.PRIVATE:
            return
        await perform_create_promo(message, (command.args or "").split())

    async def perform_redeem_promo(message: Message, code: str) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        lang = get_lang(message.from_user.id)
        try:
            amount, creator_id, uses_remaining = database.redeem_promo(code, message.from_user.id)
        except ValueError as error:
            errors = {
                "promo_not_found": t(lang, "promo_not_found"),
                "promo_exhausted": t(lang, "promo_exhausted"),
                "already_redeemed": t(lang, "promo_already_redeemed"),
                "self_redeem": t(lang, "promo_self_redeem"),
            }
            await message.answer(errors.get(str(error), t(lang, "promo_redeem_failed")))
            return
        await message.answer(t(lang, "promo_redeemed", amount=amount, code=code))
        redeemer_label = mention(message.from_user.id, user_name(message), user_full_name(message))
        try:
            await message.bot.send_message(
                creator_id,
                t(get_lang(creator_id), "promo_redeemed_notify", redeemer=redeemer_label, code=code, left=uses_remaining),
            )
        except Exception:
            logger.info("Could not notify promo creator %s about redemption of %s", creator_id, code)

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+promo\s+\S+", message.text.strip(), re.IGNORECASE)))
    async def redeem_promo(message: Message) -> None:
        if message.chat.type != ChatType.PRIVATE:
            return
        await perform_redeem_promo(message, message.text.strip().split()[1])

    async def perform_my_promo(reply_target: Message, user_id: int) -> None:
        lang = get_lang(user_id)
        promos = database.get_active_promos(user_id)
        if not promos:
            await reply_target.answer(t(lang, "my_promo_empty"))
            return
        lines = [t(lang, "my_promo_header")]
        for promo in promos:
            lines.append(
                t(
                    lang,
                    "my_promo_line",
                    code=promo["code"],
                    amount=promo["amount_per_use"],
                    left=promo["uses_remaining"],
                    used=promo["redeemed_count"],
                    created=promo["created_at"],
                )
            )
        await reply_target.answer("\n".join(lines))

    @router.message(Command("my_promo"))
    async def my_promo(message: Message) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE:
            return
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        await perform_my_promo(message, message.from_user.id)

    @router.message(Command("dice"))
    async def dice(message: Message, command: CommandObject) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        args = (command.args or "").strip()
        if not args:
            await message.answer(
                t(lang, "dice_usage"),
                reply_markup=dice_amount_keyboard(message.from_user.id),
            )
            return
        try:
            amount = parse_amount(args)
        except ValueError:
            await message.answer(t(lang, "dice_bet_invalid"))
            return
        user = database.get_user(message.from_user.id)
        if not user or user.balance < amount:
            await message.answer(t(lang, "error_insufficient_balance"))
            return
        await message.answer(
            t(lang, "dice_prompt", amount=amount),
            reply_markup=dice_choice_keyboard(message.from_user.id, amount, lang),
        )

    @router.callback_query(lambda query: query.data and query.data.startswith("dice_amount:"))
    async def dice_amount_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        lang = get_lang(query.from_user.id)
        _, initiator_id_raw, amount_raw = query.data.split(":")
        initiator_id, amount = int(initiator_id_raw), int(amount_raw)
        if query.from_user.id != initiator_id:
            await query.answer(t(lang, "dice_not_your_bet"), show_alert=True)
            return
        user = database.get_user(query.from_user.id)
        if not user or user.balance < amount:
            await query.answer(t(lang, "error_insufficient_balance"), show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            t(lang, "dice_prompt", amount=amount),
            reply_markup=dice_choice_keyboard(initiator_id, amount, lang),
        )

    @router.callback_query(lambda query: query.data and query.data.startswith("dice_choice:"))
    async def dice_choice_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        lang = get_lang(query.from_user.id)
        _, initiator_id_raw, amount_raw, choice = query.data.split(":")
        initiator_id, amount = int(initiator_id_raw), int(amount_raw)
        if query.from_user.id != initiator_id:
            await query.answer(t(lang, "dice_not_your_bet"), show_alert=True)
            return
        try:
            database.place_bet(query.from_user.id, amount)
        except ValueError as error:
            errors = {"insufficient_balance": t(lang, "error_insufficient_balance"), "invalid_amount": t(lang, "error_invalid_amount")}
            await query.answer(errors.get(str(error), t(lang, "dice_bet_failed")), show_alert=True)
            return
        database.record_dice_bet(query.from_user.id, amount)
        await query.answer()
        await query.message.edit_text(
            t(lang, "dice_choice_confirmed", amount=amount, choice=dice_choice_label(lang, choice))
        )
        roll_message = await query.message.bot.send_dice(
            query.message.chat.id, emoji="🎲", message_thread_id=query.message.message_thread_id
        )
        await asyncio.sleep(duel_result_delay_seconds)
        roll = roll_message.dice.value
        if choice == "even":
            won = roll % 2 == 0
        elif choice == "odd":
            won = roll % 2 == 1
        else:
            won = roll == int(choice)
        if won:
            payout = dice_payout(amount, choice)
            database.add_balance(query.from_user.id, payout)
            await query.message.answer(t(lang, "dice_won", roll=roll, payout=payout))
        else:
            await query.message.answer(t(lang, "dice_lost", roll=roll, amount=amount))

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+fire\s+\d+", message.text.strip(), re.IGNORECASE)))
    async def fire(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        assert message.from_user
        database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        try:
            total = parse_amount(message.text.strip().split()[1])
            drop_id, _ = database.create_drop(message.chat.id, message.from_user.id, total, 10)
        except ValueError as error:
            errors = {
                "invalid_amount": t(lang, "error_invalid_amount"),
                "invalid_drop": t(lang, "fire_invalid_drop"),
                "insufficient_balance": t(lang, "error_insufficient_balance"),
            }
            await message.answer(errors.get(str(error), t(lang, "fire_create_failed")))
            return
        candidates = database.get_chat_member_ids(message.chat.id, message.from_user.id)
        random.shuffle(candidates)
        winners: list[int] = []
        for tg_id in candidates:
            if len(winners) >= 10:
                break
            if await user_passes_requirements(message.bot, tg_id):
                winners.append(tg_id)
        payouts, count = database.finish_drop_with_winners(drop_id, winners)
        if count == 0:
            key = "fire_cancelled_channel_and_group" if REQUIRE_GROUP_MEMBERSHIP else "fire_cancelled_channel_only"
            await message.answer(t(lang, key))
            return
        creator_label = mention(message.from_user.id, user_name(message), user_full_name(message))
        names = ", ".join(mention(tg_id, username, full_name) for tg_id, username, full_name, _ in payouts)
        amounts = {amount for _, _, _, amount in payouts}
        if len(amounts) == 1:
            header = t(lang, "fire_gave_away", creator=creator_label, amount=amounts.pop(), count=count)
        else:
            header = t(lang, "fire_distributed", creator=creator_label, total=total, count=count)
        await message.answer(f"{header}\n{names}")

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+duel(?:\s+@\w+)?\s+\d+", message.text.strip(), re.IGNORECASE)))
    async def duel(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        assert message.from_user
        database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        parts = message.text.strip().split()[1:]
        opponent = None
        if message.reply_to_message and message.reply_to_message.from_user and len(parts) == 1:
            opponent_user = message.reply_to_message.from_user
            if not is_trackable_user(opponent_user):
                await message.answer(t(lang, "no_bots"))
                return
            database.touch_chat_member(message.chat.id, opponent_user.id, opponent_user.username, opponent_user.full_name, opponent_user.is_bot)
            opponent = database.get_user(opponent_user.id)
        elif len(parts) == 2 and parts[0].startswith("@"):
            if is_bot_username(parts[0]):
                await message.answer(t(lang, "no_bots"))
                return
            opponent = await ensure_username_user(database, message, parts[0])
        else:
            await message.answer(t(lang, "duel_usage"))
            return
        try:
            amount = parse_amount(parts[-1])
            if not opponent:
                raise ValueError("opponent_not_registered")
            duel_id = database.create_duel(message.chat.id, message.from_user.id, opponent.tg_id, amount)
        except ValueError as error:
            errors = {
                "invalid_amount": t(lang, "error_invalid_amount"),
                "opponent_not_registered": t(lang, "duel_opponent_not_found"),
                "user_not_found": t(lang, "duel_user_not_found"),
                "insufficient_balance": t(lang, "duel_insufficient_balance"),
                "self_duel": t(lang, "duel_self"),
            }
            await message.answer(errors.get(str(error), t(lang, "duel_create_failed")))
            return
        opponent_label = mention(opponent.tg_id, opponent.username, opponent.full_name)
        sent = await message.answer(
            t(lang, "duel_challenge", opponent=opponent_label, amount=amount, seconds=duel_accept_timeout_seconds),
            reply_markup=duel_keyboard(duel_id, lang),
        )
        asyncio.create_task(expire_duel(message.bot, message.chat.id, sent.message_id, duel_id, sent.message_thread_id))

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+\d+", message.text.strip())))
    async def reply_transfer(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        if not message.reply_to_message or not message.reply_to_message.from_user or not message.from_user:
            return
        sender = message.from_user
        recipient = message.reply_to_message.from_user
        if not is_trackable_user(recipient):
            return
        lang = get_lang(sender.id)
        if sender.id == recipient.id:
            await message.answer(t(lang, "self_transfer"))
            return
        database.touch_chat_member(message.chat.id, sender.id, sender.username, sender.full_name, sender.is_bot)
        database.touch_chat_member(message.chat.id, recipient.id, recipient.username, recipient.full_name, recipient.is_bot)
        amount = parse_amount(message.text.strip()[1:])
        try:
            database.transfer(sender.id, recipient.id, amount)
        except ValueError as error:
            errors = {"insufficient_balance": t(lang, "error_insufficient_balance"), "recipient_not_registered": t(lang, "transfer_recipient_not_registered")}
            await message.answer(errors.get(str(error), t(lang, "transfer_failed")))
            return
        sender_label = mention(sender.id, sender.username, sender.full_name)
        recipient_label = mention(recipient.id, recipient.username, recipient.full_name)
        await message.answer(t(lang, "transfer_sent", sender=sender_label, amount=amount, recipient=recipient_label))

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+send\s+@\w+\s+\d+", message.text.strip(), re.IGNORECASE)))
    async def send(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        assert message.from_user
        database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        lang = get_lang(message.from_user.id)
        parts = message.text.strip().split()[1:]
        if len(parts) != 2 or not parts[0].startswith("@"):
            await message.answer(t(lang, "send_usage"))
            return
        if is_bot_username(parts[0]):
            await message.answer(t(lang, "no_bots"))
            return
        try:
            amount = parse_amount(parts[1])
            recipient = await ensure_username_user(database, message, parts[0])
            if not recipient:
                raise ValueError("recipient_not_registered")
            database.touch_chat_member(message.chat.id, recipient.tg_id, recipient.username, recipient.full_name)
            database.transfer(message.from_user.id, recipient.tg_id, amount)
        except ValueError as error:
            errors = {"recipient_not_registered": t(lang, "transfer_recipient_not_registered"), "insufficient_balance": t(lang, "error_insufficient_balance")}
            await message.answer(errors.get(str(error), t(lang, "transfer_failed")))
            return
        sender_label = mention(message.from_user.id, user_name(message), user_full_name(message))
        recipient_label = mention(recipient.tg_id, recipient.username, recipient.full_name)
        await message.answer(t(lang, "transfer_sent", sender=sender_label, amount=amount, recipient=recipient_label))

    def mentions_bot(message: Message) -> bool:
        if not bot_username or not message.caption:
            return False
        return f"@{bot_username.lower()}" in message.caption.lower()

    @router.message(lambda message: bool(message.photo) and mentions_bot(message))
    async def apu_transform(message: Message) -> None:
        assert message.from_user
        lang = get_lang(message.from_user.id)
        if not pollinations_api_key or not public_base_url or web_server is None:
            await message.answer(t(lang, "apu_not_configured"))
            return
        status = await message.answer(t(lang, "apu_processing"))
        try:
            photo = message.photo[-1]
            buffer = await message.bot.download(photo.file_id)
            image_bytes = buffer.read()
            image_id = web_server.store_temp_image(image_bytes, "image/jpeg")
            image_url = f"{public_base_url}/images/{image_id}"
            result_bytes = await transform_to_apu(image_url, pollinations_api_key)
        except ImageGenError as error:
            logger.warning("Apu transform failed: %s", error)
            await status.edit_text(t(lang, "apu_failed"))
            return
        except Exception:
            logger.exception("Unexpected error during apu transform")
            await status.edit_text(t(lang, "apu_failed"))
            return
        await status.delete()
        await message.answer_photo(BufferedInputFile(result_bytes, filename="apugurl.png"))

    @router.message()
    async def remember_group_member(message: Message) -> None:
        if (
            message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
            and message.from_user
            and is_trackable_user(message.from_user)
        ):
            database.touch_chat_member(message.chat.id, message.from_user.id, message.from_user.username, message.from_user.full_name, message.from_user.is_bot)
            if not (message.text or "").startswith(("/", "+")):
                database.increment_message_count(message.from_user.id)

    @router.callback_query(lambda query: query.data and query.data.startswith("duel_"))
    async def duel_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        try:
            action, raw_id = query.data.split(":", 1)
            duel_id = int(raw_id)
            duel = database.get_duel(duel_id)
            if not duel:
                raise ValueError("duel_not_found")
            lang = get_lang(duel["challenger_id"])
            if duel["opponent_id"] != query.from_user.id:
                await query.answer(t(lang, "duel_not_challenged_player"), show_alert=True)
                return
            if action == "duel_decline":
                database.cancel_duel(duel_id)
                await query.message.edit_reply_markup(reply_markup=None)
                await query.message.answer(t(lang, "duel_declined"))
                await query.answer()
                return
            await query.answer(t(lang, "duel_accepted"))
            await query.message.edit_reply_markup(reply_markup=None)
            first = await query.message.bot.send_dice(
                query.message.chat.id, emoji="🎲", message_thread_id=query.message.message_thread_id
            )
            second = await query.message.bot.send_dice(
                query.message.chat.id, emoji="🎲", message_thread_id=query.message.message_thread_id
            )
            await asyncio.sleep(duel_result_delay_seconds)
            challenger_id, opponent_id, amount, winner_id, result = database.resolve_duel(duel_id, first.dice.value, second.dice.value)
            challenger = database.get_user(challenger_id)
            opponent = database.get_user(opponent_id)
            challenger_label = mention(challenger_id, challenger.username if challenger else None, challenger.full_name if challenger else None)
            opponent_label = mention(opponent_id, opponent.username if opponent else None, opponent.full_name if opponent else None)
            if result == "draw":
                outcome = t(lang, "duel_draw")
            else:
                winner = challenger_label if winner_id == challenger_id else opponent_label
                outcome = t(lang, "duel_winner", winner=winner, amount=amount)
            await query.message.answer(f"{challenger_label}: {first.dice.value}\n{opponent_label}: {second.dice.value}\n{outcome}")
        except ValueError as error:
            lang = get_lang(query.from_user.id)
            errors = {"duel_not_found": t(lang, "duel_not_found"), "duel_finished": t(lang, "duel_already_finished"), "insufficient_balance": t(lang, "duel_one_side_insufficient")}
            await query.answer(errors.get(str(error), t(lang, "duel_finish_failed")), show_alert=True)

    return router
