from __future__ import annotations

DEFAULT_LANGUAGE = "en"
SUPPORTED_LANGUAGES = ("en", "ru")

LANGUAGE_NAMES = {
    "en": "🇬🇧 English",
    "ru": "🇷🇺 Русский",
}

MESSAGES: dict[str, dict[str, str]] = {
    "menu_balance": {
        "en": "💰 Balance",
        "ru": "💰 Баланс",
    },
    "menu_top": {
        "en": "🏆 Top",
        "ru": "🏆 Топ",
    },
    "menu_deposit": {
        "en": "📥 Deposit",
        "ru": "📥 Пополнить",
    },
    "menu_withdraw": {
        "en": "📤 Withdraw",
        "ru": "📤 Вывод",
    },
    "menu_promo": {
        "en": "🎟 Promo",
        "ru": "🎟 Промокод",
    },
    "menu_dice": {
        "en": "🎲 Dice",
        "ru": "🎲 Дайс",
    },
    "menu_info": {
        "en": "ℹ️ Info",
        "ru": "ℹ️ Помощь",
    },
    "menu_back": {
        "en": "⬅️ Back",
        "ru": "⬅️ Назад",
    },
    "menu_cancel": {
        "en": "❌ Cancel",
        "ru": "❌ Отмена",
    },
    "cancelled": {
        "en": "Cancelled.",
        "ru": "Отменено.",
    },
    "promo_menu_title": {
        "en": "🎟 Promo codes:",
        "ru": "🎟 Промокоды:",
    },
    "promo_menu_create": {
        "en": "➕ Create promo code",
        "ru": "➕ Создать промокод",
    },
    "promo_menu_redeem": {
        "en": "🎁 Use promo code",
        "ru": "🎁 Активировать промокод",
    },
    "promo_menu_mine": {
        "en": "📋 My promo codes",
        "ru": "📋 Мои промокоды",
    },
    "withdraw_prompt": {
        "en": "Send the destination TON address and amount, separated by a space.\nExample: UQAbc...123 100",
        "ru": "Отправьте TON-адрес получателя и сумму через пробел.\nПример: UQAbc...123 100",
    },
    "promo_create_prompt": {
        "en": "Send the promo name, number of uses, and amount per use, separated by spaces.\nExample: WELCOME 10 5",
        "ru": "Отправьте название промокода, количество активаций и сумму за активацию через пробел.\nПример: WELCOME 10 5",
    },
    "promo_redeem_prompt": {
        "en": "Send the promo code.",
        "ru": "Отправьте промокод.",
    },
    "language_button": {
        "en": "🌐 Language",
        "ru": "🌐 Язык",
    },
    "language_prompt": {
        "en": "Choose your language:",
        "ru": "Выберите язык:",
    },
    "language_set": {
        "en": "Language set to English.",
        "ru": "Язык изменён на русский.",
    },
    "info_help": {
        "en": (
            "Available commands:\n"
            "/start - register and see your balance\n"
            "/balance - show your balance\n"
            "/deposit - show the deposit wallet and instructions (DM only)\n"
            "/withdraw ADDRESS amount - request a withdrawal to a TON wallet (DM only)\n"
            "/top - show the top 10 users by balance\n"
            "/top_gamble - top 10 users by dice + duel volume\n"
            "/top_patrons - top 10 users by +fire volume given away\n"
            "/top_talk - top 10 most talkative users\n"
            "+send @username amount - send $APUGURL to a user\n"
            "Reply to a message with +amount - send $APUGURL to its author\n"
            "+duel @username amount - challenge a user\n"
            "Reply with +duel amount - challenge the message author\n"
            "+fire amount - randomly distribute the amount to chat users\n"
            "/create_promo NAME uses amount - create a promo code (DM only)\n"
            "+promo NAME - redeem a promo code (DM only)\n"
            "/my_promo - list your active promo codes (DM only)\n"
            "/dice amount - bet on even/odd or an exact number\n"
            "Send a photo with the bot mentioned in the caption - turn it into the Apu meme character\n"
            "/language - change the bot's language\n"
            "/info - show this help"
        ),
        "ru": (
            "Доступные команды:\n"
            "/start - регистрация и просмотр баланса\n"
            "/balance - показать баланс\n"
            "/deposit - кошелёк для пополнения и инструкции (только в ЛС)\n"
            "/withdraw АДРЕС сумма - заявка на вывод на TON-кошелёк (только в ЛС)\n"
            "/top - топ 10 пользователей по балансу\n"
            "/top_gamble - топ 10 по объёму в дайсе и дуэлях\n"
            "/top_patrons - топ 10 по объёму раздач через +fire\n"
            "/top_talk - топ 10 самых общительных\n"
            "+send @username сумма - отправить $APUGURL пользователю\n"
            "Ответ на сообщение +сумма - отправить $APUGURL автору сообщения\n"
            "+duel @username сумма - вызвать пользователя на дуэль\n"
            "Ответ на сообщение +duel сумма - вызвать автора сообщения\n"
            "+fire сумма - случайно раздать сумму участникам чата\n"
            "/create_promo НАЗВАНИЕ количество сумма - создать промокод (только в ЛС)\n"
            "+promo НАЗВАНИЕ - активировать промокод (только в ЛС)\n"
            "/my_promo - список ваших активных промокодов (только в ЛС)\n"
            "/dice сумма - ставка на чёт/нечет или точное число\n"
            "Отправьте фото с упоминанием бота в подписи - превратить его в мем-персонажа Апу\n"
            "/language - сменить язык бота\n"
            "/info - показать эту справку"
        ),
    },
    "gate_prompt_channel_only": {
        "en": "To use this bot you must subscribe to our channel, then press Check:",
        "ru": "Чтобы пользоваться ботом, подпишитесь на наш канал, затем нажмите «Проверить»:",
    },
    "gate_prompt_channel_and_group": {
        "en": "To use this bot you must subscribe to our channel and join our group, then press Check:",
        "ru": "Чтобы пользоваться ботом, подпишитесь на наш канал и вступите в группу, затем нажмите «Проверить»:",
    },
    "gate_unmet_channel_only": {
        "en": "You still need to subscribe to the channel.",
        "ru": "Вы ещё не подписались на канал.",
    },
    "gate_unmet_channel_and_group": {
        "en": "You still need to join both the channel and the group.",
        "ru": "Вам нужно подписаться на канал и вступить в группу.",
    },
    "gate_check_dm": {
        "en": "Please complete the channel requirement first - check your DM.",
        "ru": "Сначала выполните условие с каналом - проверьте личные сообщения.",
    },
    "access_granted": {
        "en": "Access granted!",
        "ru": "Доступ открыт!",
    },
    "duel_expired": {
        "en": "Duel expired: no response in time.",
        "ru": "Дуэль просрочена: не было ответа вовремя.",
    },
    "welcome_balance": {
        "en": "Welcome! Your balance: {balance} $APUGURL.",
        "ru": "Добро пожаловать! Ваш баланс: {balance} $APUGURL.",
    },
    "balance_text": {
        "en": "Your balance: {balance} $APUGURL.",
        "ru": "Ваш баланс: {balance} $APUGURL.",
    },
    "deposit_info": {
        "en": (
            "Your balance: {balance} $APUGURL.\n\n"
            "Deposit wallet (TON):\n<code>{wallet}</code>\n\n"
            "⚠️ You must include this comment with your transfer:\n<code>{comment}</code>\n\n"
            "Without this comment, the bot won't be able to determine who to credit.\n\n"
            "Crediting is automatic and takes a few minutes after the transfer is confirmed on the blockchain."
        ),
        "ru": (
            "Ваш баланс: {balance} $APUGURL.\n\n"
            "Кошелёк для пополнения (TON):\n<code>{wallet}</code>\n\n"
            "⚠️ Обязательно укажите этот комментарий к переводу:\n<code>{comment}</code>\n\n"
            "Без этого комментария бот не сможет определить, кому начислить средства.\n\n"
            "Зачисление происходит автоматически, в течение нескольких минут после подтверждения перевода в блокчейне."
        ),
    },
    "withdraw_usage": {
        "en": "Usage: /withdraw ADDRESS amount",
        "ru": "Использование: /withdraw АДРЕС сумма",
    },
    "withdraw_invalid_address": {
        "en": "Invalid TON address.",
        "ru": "Неверный TON-адрес.",
    },
    "error_invalid_amount": {
        "en": "Amount must be a positive whole number.",
        "ru": "Сумма должна быть положительным целым числом.",
    },
    "error_insufficient_balance": {
        "en": "Insufficient balance.",
        "ru": "Недостаточно средств.",
    },
    "withdraw_create_failed": {
        "en": "Could not create the withdrawal request.",
        "ru": "Не удалось создать заявку на вывод.",
    },
    "withdraw_submitted": {
        "en": "Withdrawal request #{id} for {amount} $APUGURL to {address} has been submitted for review. You'll be notified once it's processed.",
        "ru": "Заявка на вывод #{id} на {amount} $APUGURL на адрес {address} отправлена на рассмотрение. Вы получите уведомление после обработки.",
    },
    "withdraw_rejected_user": {
        "en": "Your withdrawal request #{id} was rejected. Your balance was refunded.",
        "ru": "Ваша заявка на вывод #{id} была отклонена. Баланс возвращён.",
    },
    "withdraw_failed_user": {
        "en": "Your withdrawal request #{id} failed and your balance was refunded. Please try again later.",
        "ru": "Заявка на вывод #{id} не удалась, баланс возвращён. Попробуйте позже.",
    },
    "withdraw_sent_user": {
        "en": "Your withdrawal of {amount} $APUGURL has been sent. Tx: {tx}",
        "ru": "Ваш вывод {amount} $APUGURL отправлен. Tx: {tx}",
    },
    "deposit_credited": {
        "en": "Deposit received: {amount} $APUGURL credited to your balance.",
        "ru": "Депозит получен: {amount} $APUGURL зачислено на ваш баланс.",
    },
    "deposit_below_minimum": {
        "en": "A deposit was received but was below the minimum of 1 $APUGURL, so no balance was credited.",
        "ru": "Депозит получен, но он меньше минимума в 1 $APUGURL, поэтому баланс не был начислен.",
    },
    "leaderboard_empty": {
        "en": "The leaderboard is empty.",
        "ru": "Таблица лидеров пуста.",
    },
    "leaderboard_header": {
        "en": "Leaderboard:",
        "ru": "Таблица лидеров:",
    },
    "top_gamblers_empty": {
        "en": "No one has gambled yet.",
        "ru": "Пока никто не играл в азартные игры.",
    },
    "top_gamblers_header": {
        "en": "🎲 Top Gamblers (dice + duel volume):",
        "ru": "🎲 Топ лудоманов (объём в дайсе и дуэлях):",
    },
    "top_patrons_empty": {
        "en": "No one has given anything away yet.",
        "ru": "Пока никто ничего не раздавал.",
    },
    "top_patrons_header": {
        "en": "🎁 Top Patrons (+fire volume given away):",
        "ru": "🎁 Топ дарителей (объём раздач через +fire):",
    },
    "top_list_line": {
        "en": "{position}. {label} - {total} $APUGURL",
        "ru": "{position}. {label} - {total} $APUGURL",
    },
    "top_talkers_empty": {
        "en": "No one has said anything yet.",
        "ru": "Пока никто ничего не писал.",
    },
    "top_talkers_header": {
        "en": "💬 Top Talkers:",
        "ru": "💬 Топ общительных:",
    },
    "top_talkers_line": {
        "en": "{position}. {label} - {total} messages",
        "ru": "{position}. {label} - {total} сообщений",
    },
    "apu_processing": {
        "en": "🐸 Turning your photo into Apu... this can take up to a minute.",
        "ru": "🐸 Превращаю фото в Апу... это может занять до минуты.",
    },
    "apu_failed": {
        "en": "Sorry, couldn't transform that photo. Please try again later.",
        "ru": "Не получилось преобразовать фото. Попробуйте позже.",
    },
    "apu_not_configured": {
        "en": "This feature isn't set up yet.",
        "ru": "Эта функция ещё не настроена.",
    },
    "promo_usage": {
        "en": "Usage: /create_promo NAME uses amount",
        "ru": "Использование: /create_promo НАЗВАНИЕ количество сумма",
    },
    "set_usage": {
        "en": "Usage: /set @username amount",
        "ru": "Использование: /set @username сумма",
    },
    "set_user_not_found": {
        "en": "That user could not be found.",
        "ru": "Пользователь не найден.",
    },
    "set_success": {
        "en": "{user}'s balance was set to {amount} $APUGURL.",
        "ru": "Баланс {user} установлен на {amount} $APUGURL.",
    },
    "promo_name_invalid": {
        "en": "Promo name must be 3-32 letters, digits, or underscores.",
        "ru": "Название промокода должно содержать 3-32 латинских буквы, цифры или подчёркивания.",
    },
    "promo_error_amount": {
        "en": "Uses and amount must be positive whole numbers.",
        "ru": "Количество и сумма должны быть положительными целыми числами.",
    },
    "promo_error_exists": {
        "en": "This promo name is already taken.",
        "ru": "Такое название промокода уже занято.",
    },
    "promo_error_funds": {
        "en": "Insufficient balance to fund this promo.",
        "ru": "Недостаточно средств для создания этого промокода.",
    },
    "promo_create_failed": {
        "en": "Could not create the promo code.",
        "ru": "Не удалось создать промокод.",
    },
    "promo_created": {
        "en": "Promo code {code} created: {uses} uses of {amount} $APUGURL each ({total} $APUGURL reserved).",
        "ru": "Промокод {code} создан: {uses} активаций по {amount} $APUGURL (зарезервировано {total} $APUGURL).",
    },
    "promo_not_found": {
        "en": "Promo code not found.",
        "ru": "Промокод не найден.",
    },
    "promo_exhausted": {
        "en": "This promo code has no uses left.",
        "ru": "У этого промокода закончились активации.",
    },
    "promo_already_redeemed": {
        "en": "You already redeemed this promo code.",
        "ru": "Вы уже активировали этот промокод.",
    },
    "promo_self_redeem": {
        "en": "You cannot redeem your own promo code.",
        "ru": "Нельзя активировать собственный промокод.",
    },
    "promo_redeem_failed": {
        "en": "Could not redeem the promo code.",
        "ru": "Не удалось активировать промокод.",
    },
    "promo_redeemed": {
        "en": "You received {amount} $APUGURL from promo code {code}.",
        "ru": "Вы получили {amount} $APUGURL по промокоду {code}.",
    },
    "promo_redeemed_notify": {
        "en": "{redeemer} activated your promo code {code}. Uses left: {left}.",
        "ru": "{redeemer} активировал(а) ваш промокод {code}. Осталось активаций: {left}.",
    },
    "my_promo_empty": {
        "en": "You have no active promo codes.",
        "ru": "У вас нет активных промокодов.",
    },
    "my_promo_header": {
        "en": "Your active promo codes:",
        "ru": "Ваши активные промокоды:",
    },
    "my_promo_line": {
        "en": "{code}: {amount} $APUGURL per use, {left} uses left, {used} activated, created {created}",
        "ru": "{code}: {amount} $APUGURL за активацию, осталось {left}, использовано {used}, создан {created}",
    },
    "dice_usage": {
        "en": "Usage: /dice amount\nFor example: /dice 100 — or press a preset amount:",
        "ru": "Использование: /dice сумма\nНапример: /dice 100 — или нажмите готовую сумму:",
    },
    "dice_bet_invalid": {
        "en": "Bet must be a positive whole number.",
        "ru": "Ставка должна быть положительным целым числом.",
    },
    "dice_even": {
        "en": "Even ×1.8",
        "ru": "Чёт ×1.8",
    },
    "dice_odd": {
        "en": "Odd ×1.8",
        "ru": "Нечет ×1.8",
    },
    "dice_choice_confirmed": {
        "en": "🎲 Bet: {amount} $APUGURL.\nYou chose: {choice}",
        "ru": "🎲 Ставка: {amount} $APUGURL.\nВы выбрали: {choice}",
    },
    "dice_prompt": {
        "en": "🎲 Bet: {amount} $APUGURL.\nWhat are you betting on?",
        "ru": "🎲 Ставка: {amount} $APUGURL.\nНа что ставите?",
    },
    "dice_not_your_bet": {
        "en": "This is not your bet.",
        "ru": "Это не ваша ставка.",
    },
    "dice_bet_failed": {
        "en": "Could not place the bet.",
        "ru": "Не удалось сделать ставку.",
    },
    "dice_won": {
        "en": "🎲 Rolled {roll}. You won {payout} $APUGURL!",
        "ru": "🎲 Выпало {roll}. Вы выиграли {payout} $APUGURL!",
    },
    "dice_lost": {
        "en": "🎲 Rolled {roll}. You lost your bet of {amount} $APUGURL.",
        "ru": "🎲 Выпало {roll}. Вы проиграли ставку {amount} $APUGURL.",
    },
    "no_bots": {
        "en": "You cannot interact with bots.",
        "ru": "Нельзя взаимодействовать с ботами.",
    },
    "fire_invalid_drop": {
        "en": "Amount must be at least 10 $APUGURL.",
        "ru": "Сумма должна быть не менее 10 $APUGURL.",
    },
    "fire_create_failed": {
        "en": "Could not create the fire.",
        "ru": "Не удалось запустить раздачу.",
    },
    "fire_cancelled_channel_only": {
        "en": "Fire cancelled: no eligible users (must be known to the bot and have joined the channel). $APUGURL was returned.",
        "ru": "Раздача отменена: нет подходящих участников (нужно быть известным боту и подписанным на канал). $APUGURL возвращён.",
    },
    "fire_cancelled_channel_and_group": {
        "en": "Fire cancelled: no eligible users (must be known to the bot and have joined the channel and the group). $APUGURL was returned.",
        "ru": "Раздача отменена: нет подходящих участников (нужно быть известным боту, подписанным на канал и состоять в группе). $APUGURL возвращён.",
    },
    "fire_gave_away": {
        "en": "🎁 {creator} gave away {amount} $APUGURL each to {count} active participants:",
        "ru": "🎁 {creator} раздал по {amount} $APUGURL {count} активным участникам:",
    },
    "fire_distributed": {
        "en": "🎁 {creator} distributed {total} $APUGURL among {count} active participants:",
        "ru": "🎁 {creator} распределил {total} $APUGURL между {count} активными участниками:",
    },
    "duel_accept_button": {
        "en": "Accept",
        "ru": "Принять",
    },
    "duel_decline_button": {
        "en": "Decline",
        "ru": "Отклонить",
    },
    "duel_usage": {
        "en": "Usage: reply to a message with +duel amount, or use +duel @username amount.",
        "ru": "Использование: ответьте на сообщение командой +duel сумма, либо +duel @username сумма.",
    },
    "duel_opponent_not_found": {
        "en": "The opponent could not be found.",
        "ru": "Соперник не найден.",
    },
    "duel_user_not_found": {
        "en": "Both players must be known to the bot.",
        "ru": "Оба игрока должны быть известны боту.",
    },
    "duel_insufficient_balance": {
        "en": "Both players must have enough $APUGURL for the duel.",
        "ru": "У обоих игроков должно быть достаточно $APUGURL для дуэли.",
    },
    "duel_self": {
        "en": "You cannot challenge yourself.",
        "ru": "Нельзя вызвать самого себя.",
    },
    "duel_create_failed": {
        "en": "Could not create the duel.",
        "ru": "Не удалось создать дуэль.",
    },
    "duel_challenge": {
        "en": "You challenged {opponent} to a duel for {amount} $APUGURL! ({seconds}s to respond)",
        "ru": "Вы вызвали {opponent} на дуэль на {amount} $APUGURL! (даётся {seconds} сек. на ответ)",
    },
    "self_transfer": {
        "en": "You cannot send $APUGURL to yourself.",
        "ru": "Нельзя отправить $APUGURL самому себе.",
    },
    "transfer_recipient_not_registered": {
        "en": "The recipient is not registered.",
        "ru": "Получатель не зарегистрирован.",
    },
    "transfer_failed": {
        "en": "The transfer failed.",
        "ru": "Перевод не удался.",
    },
    "transfer_sent": {
        "en": "{sender} sent {amount} $APUGURL to {recipient}.",
        "ru": "{sender} отправил(а) {amount} $APUGURL пользователю {recipient}.",
    },
    "send_usage": {
        "en": "Usage: +send @username amount",
        "ru": "Использование: +send @username сумма",
    },
    "duel_not_challenged_player": {
        "en": "Only the challenged player can respond.",
        "ru": "Ответить может только вызванный игрок.",
    },
    "duel_declined": {
        "en": "Duel declined.",
        "ru": "Дуэль отклонена.",
    },
    "duel_accepted": {
        "en": "Duel accepted!",
        "ru": "Дуэль принята!",
    },
    "duel_draw": {
        "en": "Draw. Both players keep their $APUGURL.",
        "ru": "Ничья. Оба игрока сохраняют свои $APUGURL.",
    },
    "duel_winner": {
        "en": "Winner: {winner}. They receive the loser's {amount} $APUGURL.",
        "ru": "Победитель: {winner}. Он получает {amount} $APUGURL проигравшего.",
    },
    "duel_not_found": {
        "en": "Duel not found.",
        "ru": "Дуэль не найдена.",
    },
    "duel_already_finished": {
        "en": "This duel has already finished.",
        "ru": "Эта дуэль уже завершена.",
    },
    "duel_one_side_insufficient": {
        "en": "One player no longer has enough $APUGURL.",
        "ru": "У одного из игроков больше не хватает $APUGURL.",
    },
    "duel_finish_failed": {
        "en": "Could not finish the duel.",
        "ru": "Не удалось завершить дуэль.",
    },
}


def t(lang: str | None, key: str, **kwargs) -> str:
    templates = MESSAGES.get(key)
    if not templates:
        return key
    template = templates.get(lang or DEFAULT_LANGUAGE) or templates.get(DEFAULT_LANGUAGE, key)
    return template.format(**kwargs) if kwargs else template
