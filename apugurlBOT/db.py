from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Iterator


@dataclass(frozen=True)
class User:
    tg_id: int
    username: str | None
    full_name: str | None
    wallet_address: str | None
    balance: int
    snapshot_done: bool


class Database:
    def __init__(self, path: str) -> None:
        self.connection = sqlite3.connect(path, check_same_thread=False)
        self.connection.row_factory = sqlite3.Row
        self.connection.execute("PRAGMA foreign_keys = ON")
        self.connection.execute("PRAGMA journal_mode = WAL")

    def close(self) -> None:
        self.connection.close()

    def init_schema(self) -> None:
        self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                tg_id INTEGER PRIMARY KEY,
                username TEXT,
                full_name TEXT,
                wallet_address TEXT UNIQUE,
                balance INTEGER NOT NULL DEFAULT 0 CHECK (balance >= 0),
                snapshot_done INTEGER NOT NULL DEFAULT 0 CHECK (snapshot_done IN (0, 1)),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_users_wallet_address
                ON users(wallet_address) WHERE wallet_address IS NOT NULL;
            CREATE INDEX IF NOT EXISTS idx_users_username ON users(username COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS drops (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                creator_tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                total_amount INTEGER NOT NULL CHECK (total_amount > 0),
                winners_limit INTEGER NOT NULL CHECK (winners_limit > 0),
                share_amount INTEGER NOT NULL CHECK (share_amount > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS drop_claims (
                drop_id INTEGER NOT NULL REFERENCES drops(id) ON DELETE CASCADE,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                claimed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (drop_id, tg_id)
            );

            CREATE TABLE IF NOT EXISTS drop_entries (
                drop_id INTEGER NOT NULL REFERENCES drops(id) ON DELETE CASCADE,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                username TEXT,
                joined_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (drop_id, tg_id)
            );

            CREATE TABLE IF NOT EXISTS duels (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                chat_id INTEGER NOT NULL,
                challenger_id INTEGER NOT NULL REFERENCES users(tg_id),
                opponent_id INTEGER NOT NULL REFERENCES users(tg_id),
                amount INTEGER NOT NULL CHECK (amount > 0),
                status TEXT NOT NULL DEFAULT 'pending',
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS chat_members (
                chat_id INTEGER NOT NULL,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                username TEXT,
                full_name TEXT,
                is_bot INTEGER NOT NULL DEFAULT 0,
                seen_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (chat_id, tg_id)
            );

            CREATE TABLE IF NOT EXISTS promo_codes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                code TEXT NOT NULL UNIQUE,
                creator_tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                amount_per_use INTEGER NOT NULL CHECK (amount_per_use > 0),
                uses_remaining INTEGER NOT NULL CHECK (uses_remaining >= 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            CREATE UNIQUE INDEX IF NOT EXISTS idx_promo_codes_code ON promo_codes(code COLLATE NOCASE);

            CREATE TABLE IF NOT EXISTS promo_redemptions (
                promo_id INTEGER NOT NULL REFERENCES promo_codes(id) ON DELETE CASCADE,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                redeemed_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                PRIMARY KEY (promo_id, tg_id)
            );

            CREATE TABLE IF NOT EXISTS deposit_cursor (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                last_lt INTEGER NOT NULL DEFAULT 0
            );

            CREATE TABLE IF NOT EXISTS deposit_events (
                event_id TEXT PRIMARY KEY,
                tg_id INTEGER REFERENCES users(tg_id),
                raw_amount TEXT NOT NULL,
                credited_amount INTEGER NOT NULL,
                sender_address TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );

            CREATE TABLE IF NOT EXISTS withdrawals (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                amount INTEGER NOT NULL CHECK (amount > 0),
                destination_address TEXT NOT NULL,
                status TEXT NOT NULL DEFAULT 'pending',
                tx_hash TEXT,
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
                resolved_at TEXT
            );

            CREATE TABLE IF NOT EXISTS dice_bets (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                tg_id INTEGER NOT NULL REFERENCES users(tg_id),
                amount INTEGER NOT NULL CHECK (amount > 0),
                created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            );
            """
        )
        columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(drops)")}
        if "closed" not in columns:
            self.connection.execute("ALTER TABLE drops ADD COLUMN closed INTEGER NOT NULL DEFAULT 0")
        user_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(users)")}
        if "full_name" not in user_columns:
            self.connection.execute("ALTER TABLE users ADD COLUMN full_name TEXT")
        if "membership_verified_at" not in user_columns:
            self.connection.execute("ALTER TABLE users ADD COLUMN membership_verified_at TEXT")
        if "language" not in user_columns:
            self.connection.execute("ALTER TABLE users ADD COLUMN language TEXT")
        if "message_count" not in user_columns:
            self.connection.execute("ALTER TABLE users ADD COLUMN message_count INTEGER NOT NULL DEFAULT 0")
        member_columns = {row["name"] for row in self.connection.execute("PRAGMA table_info(chat_members)")}
        if "full_name" not in member_columns:
            self.connection.execute("ALTER TABLE chat_members ADD COLUMN full_name TEXT")
        if "is_bot" not in member_columns:
            self.connection.execute("ALTER TABLE chat_members ADD COLUMN is_bot INTEGER NOT NULL DEFAULT 0")
        self.connection.commit()

    @contextmanager
    def transaction(self) -> Iterator[sqlite3.Connection]:
        try:
            self.connection.execute("BEGIN IMMEDIATE")
            yield self.connection
            self.connection.commit()
        except Exception:
            self.connection.rollback()
            raise

    def upsert_telegram_user(self, tg_id: int, username: str | None, full_name: str | None = None) -> None:
        self.connection.execute(
            """
            INSERT INTO users(tg_id, username, full_name) VALUES (?, ?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET username = excluded.username, full_name = excluded.full_name
            """,
            (tg_id, username, full_name),
        )
        self.connection.commit()

    def get_membership_verified_at(self, tg_id: int) -> str | None:
        row = self.connection.execute(
            "SELECT membership_verified_at FROM users WHERE tg_id = ?", (tg_id,)
        ).fetchone()
        return row["membership_verified_at"] if row else None

    def mark_membership_verified(self, tg_id: int) -> None:
        self.connection.execute(
            """
            INSERT INTO users(tg_id, membership_verified_at) VALUES (?, CURRENT_TIMESTAMP)
            ON CONFLICT(tg_id) DO UPDATE SET membership_verified_at = CURRENT_TIMESTAMP
            """,
            (tg_id,),
        )
        self.connection.commit()

    def get_language(self, tg_id: int) -> str | None:
        row = self.connection.execute("SELECT language FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
        return row["language"] if row else None

    def set_language(self, tg_id: int, language: str) -> None:
        self.connection.execute(
            """
            INSERT INTO users(tg_id, language) VALUES (?, ?)
            ON CONFLICT(tg_id) DO UPDATE SET language = excluded.language
            """,
            (tg_id, language),
        )
        self.connection.commit()

    def touch_chat_member(
        self,
        chat_id: int,
        tg_id: int,
        username: str | None,
        full_name: str | None = None,
        is_bot: bool = False,
    ) -> None:
        self.upsert_telegram_user(tg_id, username, full_name)
        self.connection.execute(
            """
            INSERT INTO chat_members(chat_id, tg_id, username, full_name, is_bot) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, tg_id) DO UPDATE SET
                username = excluded.username, full_name = excluded.full_name, is_bot = excluded.is_bot, seen_at = CURRENT_TIMESTAMP
            """,
            (chat_id, tg_id, username, full_name, int(is_bot)),
        )
        self.connection.commit()

    def get_user(self, tg_id: int) -> User | None:
        row = self.connection.execute(
            """
            SELECT tg_id, username, full_name, wallet_address, balance, snapshot_done
            FROM users WHERE tg_id = ?
            """,
            (tg_id,),
        ).fetchone()
        return User(**dict(row)) if row else None

    def get_leaderboard(self, limit: int = 10) -> list[User]:
        rows = self.connection.execute(
            """
            SELECT tg_id, username, full_name, wallet_address, balance, snapshot_done
            FROM users ORDER BY balance DESC, tg_id ASC LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [User(**dict(row)) for row in rows]

    def get_all_users(self) -> list[User]:
        rows = self.connection.execute(
            """
            SELECT tg_id, username, full_name, wallet_address, balance, snapshot_done
            FROM users ORDER BY balance DESC, tg_id ASC
            """
        ).fetchall()
        return [User(**dict(row)) for row in rows]

    def get_users_missing_full_name(self) -> list[tuple[int, str]]:
        rows = self.connection.execute(
            "SELECT tg_id, username FROM users WHERE full_name IS NULL AND username IS NOT NULL"
        ).fetchall()
        return [(row["tg_id"], row["username"]) for row in rows]

    def find_by_username(self, username: str) -> User | None:
        row = self.connection.execute(
            """
            SELECT tg_id, username, full_name, wallet_address, balance, snapshot_done
            FROM users WHERE username = ? COLLATE NOCASE
            """,
            (username.lstrip("@"),),
        ).fetchone()
        return User(**dict(row)) if row else None

    def bind_wallet_snapshot(self, tg_id: int, wallet_address: str, balance: int) -> None:
        with self.transaction() as connection:
            owner = connection.execute(
                "SELECT tg_id FROM users WHERE wallet_address = ?",
                (wallet_address,),
            ).fetchone()
            if owner and owner["tg_id"] != tg_id:
                raise ValueError("wallet_already_bound")
            current = connection.execute(
                "SELECT wallet_address, snapshot_done FROM users WHERE tg_id = ?",
                (tg_id,),
            ).fetchone()
            if not current:
                raise ValueError("user_not_found")
            if current["wallet_address"] and current["wallet_address"] != wallet_address:
                raise ValueError("user_already_has_wallet")
            if current["snapshot_done"]:
                return
            connection.execute(
                """
                UPDATE users
                SET wallet_address = ?, balance = ?, snapshot_done = 1
                WHERE tg_id = ?
                """,
                (wallet_address, balance, tg_id),
            )

    def transfer(self, sender_id: int, recipient_id: int, amount: int) -> None:
        if amount <= 0:
            raise ValueError("invalid_amount")
        with self.transaction() as connection:
            sender = connection.execute(
                "SELECT balance FROM users WHERE tg_id = ?", (sender_id,)
            ).fetchone()
            recipient = connection.execute(
                "SELECT tg_id FROM users WHERE tg_id = ?", (recipient_id,)
            ).fetchone()
            if not sender:
                raise ValueError("sender_not_found")
            if not recipient:
                raise ValueError("recipient_not_registered")
            if sender["balance"] < amount:
                raise ValueError("insufficient_balance")
            connection.execute("UPDATE users SET balance = balance - ? WHERE tg_id = ?", (amount, sender_id))
            connection.execute("UPDATE users SET balance = balance + ? WHERE tg_id = ?", (amount, recipient_id))

    def add_balance(self, tg_id: int, amount: int) -> None:
        if amount <= 0:
            raise ValueError("invalid_amount")
        with self.transaction() as connection:
            user = connection.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            if not user:
                raise ValueError("user_not_found")
            connection.execute("UPDATE users SET balance = balance + ? WHERE tg_id = ?", (amount, tg_id))

    def set_balance(self, tg_id: int, amount: int) -> None:
        if amount < 0:
            raise ValueError("invalid_amount")
        with self.transaction() as connection:
            user = connection.execute("SELECT tg_id FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            if not user:
                raise ValueError("user_not_found")
            connection.execute("UPDATE users SET balance = ? WHERE tg_id = ?", (amount, tg_id))

    def place_bet(self, tg_id: int, amount: int) -> None:
        if amount <= 0:
            raise ValueError("invalid_amount")
        with self.transaction() as connection:
            user = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            if not user:
                raise ValueError("user_not_found")
            if user["balance"] < amount:
                raise ValueError("insufficient_balance")
            connection.execute("UPDATE users SET balance = balance - ? WHERE tg_id = ?", (amount, tg_id))

    def record_dice_bet(self, tg_id: int, amount: int) -> None:
        self.connection.execute(
            "INSERT INTO dice_bets(tg_id, amount) VALUES (?, ?)", (tg_id, amount)
        )
        self.connection.commit()

    def create_duel(self, chat_id: int, challenger_id: int, opponent_id: int, amount: int) -> int:
        if amount <= 0:
            raise ValueError("invalid_amount")
        if challenger_id == opponent_id:
            raise ValueError("self_duel")
        with self.transaction() as connection:
            challenger = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (challenger_id,)).fetchone()
            opponent = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (opponent_id,)).fetchone()
            if not challenger or not opponent:
                raise ValueError("user_not_found")
            if challenger["balance"] < amount or opponent["balance"] < amount:
                raise ValueError("insufficient_balance")
            cursor = connection.execute(
                "INSERT INTO duels(chat_id, challenger_id, opponent_id, amount) VALUES (?, ?, ?, ?)",
                (chat_id, challenger_id, opponent_id, amount),
            )
            return cursor.lastrowid

    def get_duel(self, duel_id: int):
        return self.connection.execute("SELECT * FROM duels WHERE id = ?", (duel_id,)).fetchone()

    def cancel_duel(self, duel_id: int) -> None:
        with self.transaction() as connection:
            duel = connection.execute("SELECT status FROM duels WHERE id = ?", (duel_id,)).fetchone()
            if not duel:
                raise ValueError("duel_not_found")
            if duel["status"] != "pending":
                raise ValueError("duel_finished")
            connection.execute("UPDATE duels SET status = 'declined' WHERE id = ?", (duel_id,))

    def resolve_duel(self, duel_id: int, challenger_roll: int, opponent_roll: int) -> tuple[int, int, int, int, str]:
        with self.transaction() as connection:
            duel = connection.execute("SELECT * FROM duels WHERE id = ?", (duel_id,)).fetchone()
            if not duel:
                raise ValueError("duel_not_found")
            if duel["status"] != "pending":
                raise ValueError("duel_finished")
            challenger = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (duel["challenger_id"],)).fetchone()
            opponent = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (duel["opponent_id"],)).fetchone()
            if not challenger or not opponent or challenger["balance"] < duel["amount"] or opponent["balance"] < duel["amount"]:
                connection.execute("UPDATE duels SET status = 'cancelled' WHERE id = ?", (duel_id,))
                raise ValueError("insufficient_balance")
            if challenger_roll > opponent_roll:
                winner_id, loser_id, result = duel["challenger_id"], duel["opponent_id"], "challenger"
            elif opponent_roll > challenger_roll:
                winner_id, loser_id, result = duel["opponent_id"], duel["challenger_id"], "opponent"
            else:
                winner_id = loser_id = 0
                result = "draw"
            if result != "draw":
                connection.execute("UPDATE users SET balance = balance - ? WHERE tg_id = ?", (duel["amount"], loser_id))
                connection.execute("UPDATE users SET balance = balance + ? WHERE tg_id = ?", (duel["amount"], winner_id))
            connection.execute("UPDATE duels SET status = 'finished' WHERE id = ?", (duel_id,))
            return duel["challenger_id"], duel["opponent_id"], duel["amount"], winner_id, result

    def create_drop(self, chat_id: int, creator_id: int, total: int, winners: int) -> tuple[int, int]:
        if total <= 0 or winners <= 0 or total // winners <= 0:
            raise ValueError("invalid_drop")
        share = total // winners
        with self.transaction() as connection:
            creator = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (creator_id,)).fetchone()
            if not creator:
                raise ValueError("creator_not_registered")
            if creator["balance"] < total:
                raise ValueError("insufficient_balance")
            connection.execute("UPDATE users SET balance = balance - ? WHERE tg_id = ?", (total, creator_id))
            cursor = connection.execute(
                "INSERT INTO drops(chat_id, creator_tg_id, total_amount, winners_limit, share_amount) VALUES (?, ?, ?, ?, ?)",
                (chat_id, creator_id, total, winners, share),
            )
            return cursor.lastrowid, share

    def join_drop(self, drop_id: int, tg_id: int, username: str | None) -> None:
        with self.transaction() as connection:
            drop = connection.execute("SELECT * FROM drops WHERE id = ?", (drop_id,)).fetchone()
            if not drop:
                raise ValueError("drop_not_found")
            if drop["creator_tg_id"] == tg_id:
                raise ValueError("creator_cannot_claim")
            if not connection.execute("SELECT 1 FROM users WHERE tg_id = ?", (tg_id,)).fetchone():
                raise ValueError("recipient_not_registered")
            if drop["closed"]:
                raise ValueError("drop_finished")
            if connection.execute("SELECT 1 FROM drop_entries WHERE drop_id = ? AND tg_id = ?", (drop_id, tg_id)).fetchone():
                raise ValueError("already_claimed")
            connection.execute(
                "INSERT INTO drop_entries(drop_id, tg_id, username) VALUES (?, ?, ?)",
                (drop_id, tg_id, username),
            )

    def finish_drop(self, drop_id: int) -> tuple[int, list[tuple[int, str | None]], int]:
        with self.transaction() as connection:
            drop = connection.execute("SELECT * FROM drops WHERE id = ?", (drop_id,)).fetchone()
            if not drop:
                raise ValueError("drop_not_found")
            if drop["closed"]:
                return drop["share_amount"], [], 0
            entries = connection.execute(
                """
                SELECT tg_id, username FROM drop_entries
                WHERE drop_id = ? ORDER BY RANDOM() LIMIT ?
                """,
                (drop_id, drop["winners_limit"]),
            ).fetchall()
            connection.execute("UPDATE drops SET closed = 1 WHERE id = ?", (drop_id,))
            for entry in entries:
                connection.execute(
                    "INSERT INTO drop_claims(drop_id, tg_id) VALUES (?, ?)",
                    (drop_id, entry["tg_id"]),
                )
                connection.execute(
                    "UPDATE users SET balance = balance + ? WHERE tg_id = ?",
                    (drop["share_amount"], entry["tg_id"]),
                )
            return drop["share_amount"], [(entry["tg_id"], entry["username"]) for entry in entries], len(entries)

    def get_chat_member_ids(self, chat_id: int, exclude_tg_id: int) -> list[int]:
        rows = self.connection.execute(
            """
            SELECT tg_id FROM chat_members
            WHERE chat_id = ? AND tg_id != ? AND tg_id != 777000 AND is_bot = 0
            """,
            (chat_id, exclude_tg_id),
        ).fetchall()
        return [row["tg_id"] for row in rows]

    def finish_drop_with_winners(
        self, drop_id: int, winner_ids: list[int]
    ) -> tuple[list[tuple[int, str | None, str | None, int]], int]:
        with self.transaction() as connection:
            drop = connection.execute("SELECT * FROM drops WHERE id = ?", (drop_id,)).fetchone()
            if not drop:
                raise ValueError("drop_not_found")
            if drop["closed"]:
                return [], 0
            connection.execute("UPDATE drops SET closed = 1 WHERE id = ?", (drop_id,))
            if not winner_ids:
                connection.execute(
                    "UPDATE users SET balance = balance + ? WHERE tg_id = ?",
                    (drop["total_amount"], drop["creator_tg_id"]),
                )
                return [], 0
            base_amount, remainder = divmod(drop["total_amount"], len(winner_ids))
            payouts = []
            for index, tg_id in enumerate(winner_ids):
                payout = base_amount + (1 if index < remainder else 0)
                connection.execute(
                    "INSERT INTO drop_claims(drop_id, tg_id) VALUES (?, ?)",
                    (drop_id, tg_id),
                )
                connection.execute(
                    "UPDATE users SET balance = balance + ? WHERE tg_id = ?",
                    (payout, tg_id),
                )
                winner = connection.execute(
                    "SELECT username, full_name FROM users WHERE tg_id = ?", (tg_id,)
                ).fetchone()
                payouts.append((tg_id, winner["username"] if winner else None, winner["full_name"] if winner else None, payout))
            return payouts, len(payouts)

    def create_promo(self, creator_id: int, code: str, uses: int, amount_per_use: int) -> None:
        if uses <= 0 or amount_per_use <= 0:
            raise ValueError("invalid_amount")
        total = uses * amount_per_use
        with self.transaction() as connection:
            if connection.execute("SELECT 1 FROM promo_codes WHERE code = ? COLLATE NOCASE", (code,)).fetchone():
                raise ValueError("promo_exists")
            creator = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (creator_id,)).fetchone()
            if not creator:
                raise ValueError("user_not_found")
            if creator["balance"] < total:
                raise ValueError("insufficient_balance")
            connection.execute("UPDATE users SET balance = balance - ? WHERE tg_id = ?", (total, creator_id))
            connection.execute(
                "INSERT INTO promo_codes(code, creator_tg_id, amount_per_use, uses_remaining) VALUES (?, ?, ?, ?)",
                (code, creator_id, amount_per_use, uses),
            )

    def get_active_promos(self, creator_id: int) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT
                p.code,
                p.amount_per_use,
                p.uses_remaining,
                p.created_at,
                (SELECT COUNT(*) FROM promo_redemptions r WHERE r.promo_id = p.id) AS redeemed_count
            FROM promo_codes p
            WHERE p.creator_tg_id = ? AND p.uses_remaining > 0
            ORDER BY p.created_at DESC
            """,
            (creator_id,),
        ).fetchall()
        return [dict(row) for row in rows]

    def redeem_promo(self, code: str, tg_id: int) -> tuple[int, int, int]:
        with self.transaction() as connection:
            promo = connection.execute("SELECT * FROM promo_codes WHERE code = ? COLLATE NOCASE", (code,)).fetchone()
            if not promo:
                raise ValueError("promo_not_found")
            if promo["creator_tg_id"] == tg_id:
                raise ValueError("self_redeem")
            if promo["uses_remaining"] <= 0:
                raise ValueError("promo_exhausted")
            if connection.execute(
                "SELECT 1 FROM promo_redemptions WHERE promo_id = ? AND tg_id = ?", (promo["id"], tg_id)
            ).fetchone():
                raise ValueError("already_redeemed")
            connection.execute(
                "INSERT INTO promo_redemptions(promo_id, tg_id) VALUES (?, ?)", (promo["id"], tg_id)
            )
            uses_remaining = promo["uses_remaining"] - 1
            connection.execute(
                "UPDATE promo_codes SET uses_remaining = ? WHERE id = ?", (uses_remaining, promo["id"])
            )
            connection.execute(
                "UPDATE users SET balance = balance + ? WHERE tg_id = ?", (promo["amount_per_use"], tg_id)
            )
            return promo["amount_per_use"], promo["creator_tg_id"], uses_remaining

    def get_deposit_cursor(self) -> int:
        row = self.connection.execute("SELECT last_lt FROM deposit_cursor WHERE id = 1").fetchone()
        return row["last_lt"] if row else 0

    def set_deposit_cursor(self, last_lt: int) -> None:
        self.connection.execute(
            """
            INSERT INTO deposit_cursor(id, last_lt) VALUES (1, ?)
            ON CONFLICT(id) DO UPDATE SET last_lt = excluded.last_lt
            """,
            (last_lt,),
        )
        self.connection.commit()

    def credit_deposit(
        self,
        event_id: str,
        tg_id: int,
        raw_amount: int,
        credited_amount: int,
        sender_address: str | None,
    ) -> bool:
        with self.transaction() as connection:
            if connection.execute(
                "SELECT 1 FROM deposit_events WHERE event_id = ?", (event_id,)
            ).fetchone():
                return False
            connection.execute(
                """
                INSERT INTO deposit_events(event_id, tg_id, raw_amount, credited_amount, sender_address)
                VALUES (?, ?, ?, ?, ?)
                """,
                (event_id, tg_id, str(raw_amount), credited_amount, sender_address),
            )
            if credited_amount > 0:
                connection.execute(
                    "UPDATE users SET balance = balance + ? WHERE tg_id = ?", (credited_amount, tg_id)
                )
            return True

    def create_withdrawal(self, tg_id: int, amount: int, destination_address: str) -> int:
        if amount <= 0:
            raise ValueError("invalid_amount")
        with self.transaction() as connection:
            user = connection.execute("SELECT balance FROM users WHERE tg_id = ?", (tg_id,)).fetchone()
            if not user:
                raise ValueError("user_not_found")
            if user["balance"] < amount:
                raise ValueError("insufficient_balance")
            connection.execute("UPDATE users SET balance = balance - ? WHERE tg_id = ?", (amount, tg_id))
            cursor = connection.execute(
                "INSERT INTO withdrawals(tg_id, amount, destination_address) VALUES (?, ?, ?)",
                (tg_id, amount, destination_address),
            )
            return cursor.lastrowid

    def get_withdrawal(self, withdrawal_id: int):
        return self.connection.execute(
            "SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,)
        ).fetchone()

    def resolve_withdrawal(self, withdrawal_id: int, status: str, tx_hash: str | None = None) -> None:
        with self.transaction() as connection:
            withdrawal = connection.execute(
                "SELECT * FROM withdrawals WHERE id = ?", (withdrawal_id,)
            ).fetchone()
            if not withdrawal:
                raise ValueError("withdrawal_not_found")
            if withdrawal["status"] != "pending":
                raise ValueError("withdrawal_finished")
            connection.execute(
                "UPDATE withdrawals SET status = ?, tx_hash = ?, resolved_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, tx_hash, withdrawal_id),
            )
            if status in ("rejected", "failed"):
                connection.execute(
                    "UPDATE users SET balance = balance + ? WHERE tg_id = ?",
                    (withdrawal["amount"], withdrawal["tg_id"]),
                )

    def get_statistics(self) -> dict:
        total_deposits = self.connection.execute(
            "SELECT COALESCE(SUM(credited_amount), 0) AS total FROM deposit_events"
        ).fetchone()["total"]
        total_withdrawals = self.connection.execute(
            "SELECT COALESCE(SUM(amount), 0) AS total FROM withdrawals WHERE status = 'sent'"
        ).fetchone()["total"]
        total_balance = self.connection.execute(
            "SELECT COALESCE(SUM(balance), 0) AS total FROM users"
        ).fetchone()["total"]
        return {
            "total_deposits": total_deposits,
            "total_withdrawals": total_withdrawals,
            "total_balance": total_balance,
        }

    def _resolve_user_rows(self, rows) -> list[dict]:
        result = []
        for row in rows:
            user = self.connection.execute(
                "SELECT username, full_name FROM users WHERE tg_id = ?", (row["tg_id"],)
            ).fetchone()
            result.append({
                "tg_id": row["tg_id"],
                "username": user["username"] if user else None,
                "full_name": user["full_name"] if user else None,
                "total": row["total"],
            })
        return result

    def get_top_gamblers(self, limit: int = 10) -> list[dict]:
        rows = self.connection.execute(
            """
            WITH combined AS (
                SELECT tg_id, amount FROM dice_bets
                UNION ALL
                SELECT challenger_id AS tg_id, amount FROM duels WHERE status = 'finished'
                UNION ALL
                SELECT opponent_id AS tg_id, amount FROM duels WHERE status = 'finished'
            )
            SELECT tg_id, SUM(amount) AS total FROM combined
            GROUP BY tg_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return self._resolve_user_rows(rows)

    def increment_message_count(self, tg_id: int) -> None:
        self.connection.execute(
            """
            INSERT INTO users(tg_id, message_count) VALUES (?, 1)
            ON CONFLICT(tg_id) DO UPDATE SET message_count = message_count + 1
            """,
            (tg_id,),
        )
        self.connection.commit()

    def get_top_talkers(self, limit: int = 10) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT tg_id, username, full_name, message_count AS total
            FROM users
            WHERE message_count > 0
            ORDER BY message_count DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return [dict(row) for row in rows]

    def get_top_patrons(self, limit: int = 10) -> list[dict]:
        rows = self.connection.execute(
            """
            SELECT d.creator_tg_id AS tg_id, SUM(d.total_amount) AS total
            FROM drops d
            WHERE EXISTS (SELECT 1 FROM drop_claims dc WHERE dc.drop_id = d.id)
            GROUP BY d.creator_tg_id
            ORDER BY total DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
        return self._resolve_user_rows(rows)
