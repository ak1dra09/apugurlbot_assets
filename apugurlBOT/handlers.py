from __future__ import annotations

import asyncio
import html
import logging
import re
from decimal import Decimal, InvalidOperation

from aiogram import Router
from aiogram.enums import ChatType
from aiogram.filters import Command, CommandObject
from aiogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup, Message
from ton_core import Address

from db import Database
from hotwallet import HotWallet, HotWalletError
from wallet import WalletManager

logger = logging.getLogger(__name__)

TELEGRAM_SERVICE_ACCOUNT_ID = 777000
PROMO_CODE_PATTERN = re.compile(r"[A-Za-z0-9_]{3,32}")


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


def duel_keyboard(duel_id: int) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(inline_keyboard=[[
        InlineKeyboardButton(text="Accept", callback_data=f"duel_accept:{duel_id}"),
        InlineKeyboardButton(text="Decline", callback_data=f"duel_decline:{duel_id}"),
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


def dice_choice_keyboard(initiator_id: int, amount: int) -> InlineKeyboardMarkup:
    def button(label: str, choice: str) -> InlineKeyboardButton:
        return InlineKeyboardButton(text=label, callback_data=f"dice_choice:{initiator_id}:{amount}:{choice}")

    return InlineKeyboardMarkup(inline_keyboard=[
        [button("Even ×1.8", "even"), button("Odd ×1.8", "odd")],
        [button(f"{n} ×5.0", str(n)) for n in (1, 2, 3)],
        [button(f"{n} ×5.0", str(n)) for n in (4, 5, 6)],
    ])


def dice_payout(amount: int, choice: str) -> int:
    if choice in ("even", "odd"):
        return amount * DICE_PARITY_PAYOUT_NUM // DICE_PARITY_PAYOUT_DEN
    return amount * DICE_NUMBER_MULTIPLIER


def install_handlers(
    database: Database,
    wallets: WalletManager,
    rain_duration_seconds: int = 30,
    duel_result_delay_seconds: int = 3,
    duel_accept_timeout_seconds: int = 60,
    deposit_wallet_address: str = "",
    hot_wallet: HotWallet | None = None,
) -> Router:
    router = Router()

    async def expire_duel(bot, chat_id: int, message_id: int, duel_id: int) -> None:
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
            await bot.send_message(chat_id, "Duel expired: no response in time.")
        except Exception:
            pass

    @router.message(Command("start"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def start(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        user = database.get_user(message.from_user.id)
        await message.answer(f"Welcome! Your balance: {user.balance if user else 0} $APUGURL.")

    @router.message(Command("balance"))
    async def balance(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        user = database.get_user(message.from_user.id)
        await message.answer(f"Your balance: {user.balance if user else 0} $APUGURL.")

    @router.message(Command("deposit"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def deposit(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        user = database.get_user(message.from_user.id)
        comment = f"DEP{message.from_user.id}"
        await message.answer(
            f"Your balance: {user.balance if user else 0} $APUGURL.\n\n"
            f"Deposit wallet (TON):\n{deposit_wallet_address}\n\n"
            f"⚠️ You must include this comment with your transfer:\n{comment}\n\n"
            "Without this comment, the bot won't be able to determine who to credit.\n\n"
            "Crediting is automatic and takes a few minutes after the transfer is confirmed on the blockchain."
        )

    @router.message(Command("withdraw"), lambda message: message.chat.type == ChatType.PRIVATE)
    async def withdraw(message: Message, command: CommandObject) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        parts = (command.args or "").split()
        if len(parts) != 2:
            await message.answer("Usage: /withdraw ADDRESS amount")
            return
        address_text, amount_text = parts
        address = parse_ton_address(address_text)
        if address is None:
            await message.answer("Invalid TON address.")
            return
        try:
            amount = parse_amount(amount_text)
            withdrawal_id = database.create_withdrawal(message.from_user.id, amount, address.to_str())
        except ValueError as error:
            errors = {
                "invalid_amount": "Amount must be a positive whole number.",
                "insufficient_balance": "Insufficient balance.",
            }
            await message.answer(errors.get(str(error), "Could not create the withdrawal request."))
            return
        await message.answer(
            f"Withdrawal request #{withdrawal_id} for {amount} $APUGURL to {address.to_str()} "
            "has been submitted for review. You'll be notified once it's processed."
        )
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
                    f"Your withdrawal request #{withdrawal_id} was rejected. Your balance was refunded.",
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
                    f"Your withdrawal request #{withdrawal_id} failed and your balance was refunded. Please try again later.",
                )
            except Exception:
                logger.info("Could not notify user %s about failed withdrawal #%s", withdrawal["tg_id"], withdrawal_id)
            return
        database.resolve_withdrawal(withdrawal_id, "sent", tx_hash)
        await query.message.answer(f"Withdrawal #{withdrawal_id} sent. Tx: {tx_hash}")
        try:
            await query.bot.send_message(
                withdrawal["tg_id"],
                f"Your withdrawal of {withdrawal['amount']} $APUGURL has been sent. Tx: {tx_hash}",
            )
        except Exception:
            logger.info("Could not notify user %s about sent withdrawal #%s", withdrawal["tg_id"], withdrawal_id)

    @router.message(Command("top"))
    async def leaderboard(message: Message) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        users = database.get_leaderboard(10)
        if not users:
            await message.answer("The leaderboard is empty.")
            return
        lines = ["Leaderboard:"]
        for position, user in enumerate(users, start=1):
            label = mention(user.tg_id, user.username, user.full_name)
            lines.append(f"{position}. {label} - {user.balance} $APUGURL")
        await message.answer("\n".join(lines))

    @router.message(Command("info"))
    async def info(message: Message) -> None:
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP) and message.from_user:
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        await message.answer(
            "Available commands:\n"
            "/start - register and see your balance\n"
            "/balance - show your balance\n"
            "/deposit - show the deposit wallet and instructions (DM only)\n"
            "/withdraw ADDRESS amount - request a withdrawal to a TON wallet (DM only)\n"
            "/top - show the top 10 users by balance\n"
            "+send @username amount - send $APUGURL to a user\n"
            "Reply to a message with +amount - send $APUGURL to its author\n"
            "+duel @username amount - challenge a user\n"
            "Reply with +duel amount - challenge the message author\n"
            "+fire amount - randomly distribute the amount to chat users\n"
            "/create_promo NAME uses amount - create a promo code (DM only)\n"
            "+promo NAME - redeem a promo code (DM only)\n"
            "/my_promo - list your active promo codes (DM only)\n"
            "/dice amount - bet on even/odd or an exact number\n"
            "/info - show this help"
        )

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

    @router.message(Command("create_promo"))
    async def create_promo(message: Message, command: CommandObject) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE:
            return
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        parts = (command.args or "").split()
        if len(parts) != 3:
            await message.answer("Usage: /create_promo NAME uses amount")
            return
        code, uses_raw, amount_raw = parts
        if not PROMO_CODE_PATTERN.fullmatch(code):
            await message.answer("Promo name must be 3-32 letters, digits, or underscores.")
            return
        try:
            uses = parse_amount(uses_raw)
            amount_per_use = parse_amount(amount_raw)
            database.create_promo(message.from_user.id, code, uses, amount_per_use)
        except ValueError as error:
            errors = {
                "invalid_amount": "Uses and amount must be positive whole numbers.",
                "promo_exists": "This promo name is already taken.",
                "insufficient_balance": "Insufficient balance to fund this promo.",
            }
            await message.answer(errors.get(str(error), "Could not create the promo code."))
            return
        total = uses * amount_per_use
        await message.answer(f"Promo code {code} created: {uses} uses of {amount_per_use} $APUGURL each ({total} $APUGURL reserved).")

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+promo\s+\S+", message.text.strip(), re.IGNORECASE)))
    async def redeem_promo(message: Message) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE:
            return
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        code = message.text.strip().split()[1]
        try:
            amount, creator_id, uses_remaining = database.redeem_promo(code, message.from_user.id)
        except ValueError as error:
            errors = {
                "promo_not_found": "Promo code not found.",
                "promo_exhausted": "This promo code has no uses left.",
                "already_redeemed": "You already redeemed this promo code.",
                "self_redeem": "You cannot redeem your own promo code.",
            }
            await message.answer(errors.get(str(error), "Could not redeem the promo code."))
            return
        await message.answer(f"You received {amount} $APUGURL from promo code {code}.")
        redeemer_label = mention(message.from_user.id, user_name(message), user_full_name(message))
        try:
            await message.bot.send_message(
                creator_id,
                f"{redeemer_label} activated your promo code {code}. Uses left: {uses_remaining}.",
            )
        except Exception:
            logger.info("Could not notify promo creator %s about redemption of %s", creator_id, code)

    @router.message(Command("my_promo"))
    async def my_promo(message: Message) -> None:
        assert message.from_user
        if message.chat.type != ChatType.PRIVATE:
            return
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        promos = database.get_active_promos(message.from_user.id)
        if not promos:
            await message.answer("You have no active promo codes.")
            return
        lines = ["Your active promo codes:"]
        for promo in promos:
            lines.append(
                f"{promo['code']}: {promo['amount_per_use']} $APUGURL per use, "
                f"{promo['uses_remaining']} uses left, {promo['redeemed_count']} activated, "
                f"created {promo['created_at']}"
            )
        await message.answer("\n".join(lines))

    @router.message(Command("dice"))
    async def dice(message: Message, command: CommandObject) -> None:
        assert message.from_user
        database.upsert_telegram_user(message.from_user.id, user_name(message), user_full_name(message))
        if message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP):
            database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        args = (command.args or "").strip()
        if not args:
            await message.answer(
                "Usage: /dice amount\nFor example: /dice 100 — or press a preset amount:",
                reply_markup=dice_amount_keyboard(message.from_user.id),
            )
            return
        try:
            amount = parse_amount(args)
        except ValueError:
            await message.answer("Bet must be a positive whole number.")
            return
        user = database.get_user(message.from_user.id)
        if not user or user.balance < amount:
            await message.answer("Insufficient balance.")
            return
        await message.answer(
            f"🎲 Bet: {amount} $APUGURL.\nWhat are you betting on?",
            reply_markup=dice_choice_keyboard(message.from_user.id, amount),
        )

    @router.callback_query(lambda query: query.data and query.data.startswith("dice_amount:"))
    async def dice_amount_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        _, initiator_id_raw, amount_raw = query.data.split(":")
        initiator_id, amount = int(initiator_id_raw), int(amount_raw)
        if query.from_user.id != initiator_id:
            await query.answer("This is not your bet.", show_alert=True)
            return
        user = database.get_user(query.from_user.id)
        if not user or user.balance < amount:
            await query.answer("Insufficient balance.", show_alert=True)
            return
        await query.answer()
        await query.message.edit_text(
            f"🎲 Bet: {amount} $APUGURL.\nWhat are you betting on?",
            reply_markup=dice_choice_keyboard(initiator_id, amount),
        )

    @router.callback_query(lambda query: query.data and query.data.startswith("dice_choice:"))
    async def dice_choice_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        _, initiator_id_raw, amount_raw, choice = query.data.split(":")
        initiator_id, amount = int(initiator_id_raw), int(amount_raw)
        if query.from_user.id != initiator_id:
            await query.answer("This is not your bet.", show_alert=True)
            return
        try:
            database.place_bet(query.from_user.id, amount)
        except ValueError as error:
            errors = {"insufficient_balance": "Insufficient balance.", "invalid_amount": "Invalid bet amount."}
            await query.answer(errors.get(str(error), "Could not place the bet."), show_alert=True)
            return
        await query.answer()
        await query.message.edit_reply_markup(reply_markup=None)
        roll_message = await query.message.bot.send_dice(query.message.chat.id, emoji="🎲")
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
            await query.message.answer(f"🎲 Rolled {roll}. You won {payout} $APUGURL!")
        else:
            await query.message.answer(f"🎲 Rolled {roll}. You lost your bet of {amount} $APUGURL.")

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+fire\s+\d+", message.text.strip(), re.IGNORECASE)))
    async def fire(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        assert message.from_user
        database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        try:
            total = parse_amount(message.text.strip().split()[1])
            drop_id, _ = database.create_drop(message.chat.id, message.from_user.id, total, 10)
            payouts, count = database.finish_drop_random(drop_id, message.chat.id)
        except ValueError as error:
            errors = {
                "invalid_amount": "Amount must be a positive whole number.",
                "invalid_drop": "Amount must be at least 10 $APUGURL.",
                "insufficient_balance": "Insufficient balance.",
            }
            await message.answer(errors.get(str(error), "Could not create the fire."))
            return
        if count == 0:
            await message.answer("Fire cancelled: no other users are known in this chat. $APUGURL was returned.")
            return
        creator_label = mention(message.from_user.id, user_name(message), user_full_name(message))
        names = ", ".join(mention(tg_id, username, full_name) for tg_id, username, full_name, _ in payouts)
        amounts = {amount for _, _, _, amount in payouts}
        if len(amounts) == 1:
            header = f"🎁 {creator_label} gave away {amounts.pop()} $APUGURL each to {count} active participants:"
        else:
            header = f"🎁 {creator_label} distributed {total} $APUGURL among {count} active participants:"
        await message.answer(f"{header}\n{names}")

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+duel(?:\s+@\w+)?\s+\d+", message.text.strip(), re.IGNORECASE)))
    async def duel(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        assert message.from_user
        database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        parts = message.text.strip().split()[1:]
        opponent = None
        if message.reply_to_message and message.reply_to_message.from_user and len(parts) == 1:
            opponent_user = message.reply_to_message.from_user
            if not is_trackable_user(opponent_user):
                await message.answer("You cannot interact with bots.")
                return
            database.touch_chat_member(message.chat.id, opponent_user.id, opponent_user.username, opponent_user.full_name, opponent_user.is_bot)
            opponent = database.get_user(opponent_user.id)
        elif len(parts) == 2 and parts[0].startswith("@"):
            if is_bot_username(parts[0]):
                await message.answer("You cannot interact with bots.")
                return
            opponent = await ensure_username_user(database, message, parts[0])
        else:
            await message.answer("Usage: reply to a message with +duel amount, or use +duel @username amount.")
            return
        try:
            amount = parse_amount(parts[-1])
            if not opponent:
                raise ValueError("opponent_not_registered")
            duel_id = database.create_duel(message.chat.id, message.from_user.id, opponent.tg_id, amount)
        except ValueError as error:
            errors = {
                "invalid_amount": "Amount must be a positive whole number.",
                "opponent_not_registered": "The opponent could not be found.",
                "user_not_found": "Both players must be known to the bot.",
                "insufficient_balance": "Both players must have enough $APUGURL for the duel.",
                "self_duel": "You cannot challenge yourself.",
            }
            await message.answer(errors.get(str(error), "Could not create the duel."))
            return
        opponent_label = mention(opponent.tg_id, opponent.username, opponent.full_name)
        sent = await message.answer(
            f"You challenged {opponent_label} to a duel for {amount} $APUGURL! "
            f"({duel_accept_timeout_seconds}s to respond)",
            reply_markup=duel_keyboard(duel_id),
        )
        asyncio.create_task(expire_duel(message.bot, message.chat.id, sent.message_id, duel_id))

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
        if sender.id == recipient.id:
            await message.answer("You cannot send $APUGURL to yourself.")
            return
        database.touch_chat_member(message.chat.id, sender.id, sender.username, sender.full_name, sender.is_bot)
        database.touch_chat_member(message.chat.id, recipient.id, recipient.username, recipient.full_name, recipient.is_bot)
        amount = parse_amount(message.text.strip()[1:])
        try:
            database.transfer(sender.id, recipient.id, amount)
        except ValueError as error:
            errors = {"insufficient_balance": "Insufficient balance.", "recipient_not_registered": "The recipient is not registered."}
            await message.answer(errors.get(str(error), "The transfer failed."))
            return
        label = mention(recipient.id, recipient.username, recipient.full_name)
        await message.answer(f"Sent {amount} $APUGURL to {label}.")

    @router.message(lambda message: bool(message.text and re.fullmatch(r"\+send\s+@\w+\s+\d+", message.text.strip(), re.IGNORECASE)))
    async def send(message: Message) -> None:
        if message.chat.type not in (ChatType.GROUP, ChatType.SUPERGROUP):
            return
        assert message.from_user
        database.touch_chat_member(message.chat.id, message.from_user.id, user_name(message), user_full_name(message), message.from_user.is_bot)
        parts = message.text.strip().split()[1:]
        if len(parts) != 2 or not parts[0].startswith("@"):
            await message.answer("Usage: +send @username amount")
            return
        if is_bot_username(parts[0]):
            await message.answer("You cannot interact with bots.")
            return
        try:
            amount = parse_amount(parts[1])
            recipient = await ensure_username_user(database, message, parts[0])
            if not recipient:
                raise ValueError("recipient_not_registered")
            database.touch_chat_member(message.chat.id, recipient.tg_id, recipient.username, recipient.full_name)
            database.transfer(message.from_user.id, recipient.tg_id, amount)
        except ValueError as error:
            errors = {"recipient_not_registered": "The recipient is not registered.", "insufficient_balance": "Insufficient balance."}
            await message.answer(errors.get(str(error), "The transfer failed."))
            return
        await message.answer(f"Sent {amount} $APUGURL to {mention(recipient.tg_id, recipient.username, recipient.full_name)}.")

    @router.message()
    async def remember_group_member(message: Message) -> None:
        if (
            message.chat.type in (ChatType.GROUP, ChatType.SUPERGROUP)
            and message.from_user
            and is_trackable_user(message.from_user)
        ):
            database.touch_chat_member(message.chat.id, message.from_user.id, message.from_user.username, message.from_user.full_name, message.from_user.is_bot)

    @router.callback_query(lambda query: query.data and query.data.startswith("duel_"))
    async def duel_action(query: CallbackQuery) -> None:
        assert query.from_user and query.data and query.message
        try:
            action, raw_id = query.data.split(":", 1)
            duel_id = int(raw_id)
            duel = database.get_duel(duel_id)
            if not duel:
                raise ValueError("duel_not_found")
            if duel["opponent_id"] != query.from_user.id:
                await query.answer("Only the challenged player can respond.", show_alert=True)
                return
            if action == "duel_decline":
                database.cancel_duel(duel_id)
                await query.message.edit_reply_markup(reply_markup=None)
                await query.message.answer("Duel declined.")
                await query.answer()
                return
            await query.answer("Duel accepted!")
            await query.message.edit_reply_markup(reply_markup=None)
            first = await query.message.bot.send_dice(query.message.chat.id, emoji="🎲")
            second = await query.message.bot.send_dice(query.message.chat.id, emoji="🎲")
            await asyncio.sleep(duel_result_delay_seconds)
            challenger_id, opponent_id, amount, winner_id, result = database.resolve_duel(duel_id, first.dice.value, second.dice.value)
            challenger = database.get_user(challenger_id)
            opponent = database.get_user(opponent_id)
            challenger_label = mention(challenger_id, challenger.username if challenger else None, challenger.full_name if challenger else None)
            opponent_label = mention(opponent_id, opponent.username if opponent else None, opponent.full_name if opponent else None)
            if result == "draw":
                outcome = "Draw. Both players keep their $APUGURL."
            else:
                winner = challenger_label if winner_id == challenger_id else opponent_label
                outcome = f"Winner: {winner}. They receive the loser's {amount} $APUGURL."
            await query.message.answer(f"{challenger_label}: {first.dice.value}\n{opponent_label}: {second.dice.value}\n{outcome}")
        except ValueError as error:
            errors = {"duel_not_found": "Duel not found.", "duel_finished": "This duel has already finished.", "insufficient_balance": "One player no longer has enough $APUGURL."}
            await query.answer(errors.get(str(error), "Could not finish the duel."), show_alert=True)

    return router
