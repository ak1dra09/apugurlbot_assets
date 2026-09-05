from __future__ import annotations

import asyncio
import logging
import secrets
from collections.abc import Awaitable, Callable
from typing import Any

from db import Database
from tonapi import TonApi

logger = logging.getLogger(__name__)
WalletConnected = Callable[[int, str, int], Awaitable[None]]


class WalletManager:
    def __init__(
        self,
        manifest_url: str,
        database: Database,
        tonapi: TonApi,
        divisor: int,
        public_url: str = "",
        admin_ids: frozenset[int] = frozenset(),
    ) -> None:
        self.manifest_url = manifest_url
        self.database = database
        self.tonapi = tonapi
        self.divisor = divisor
        self.public_url = public_url
        self.admin_ids = admin_ids
        self.tasks: dict[int, asyncio.Task[Any]] = {}
        self.sessions: dict[str, int] = {}

    def create_link(self, tg_id: int) -> str:
        if not self.public_url:
            raise RuntimeError("TONCONNECT_PUBLIC_URL is required")
        token = secrets.token_urlsafe(32)
        self.sessions[token] = tg_id
        return f"{self.public_url}/connect?token={token}&ngrok-skip-browser-warning=true"

    async def complete_connection(self, token: str, address: str) -> None:
        tg_id = self.sessions.pop(token, None)
        if tg_id is None:
            raise ValueError("invalid_connection_session")
        await self._process_connection(tg_id, {"account": {"address": address}})

    def _status_changed(self, tg_id: int, wallet: Any) -> None:
        task = self.tasks.get(tg_id)
        if task and not task.done():
            task.cancel()
        self.tasks[tg_id] = asyncio.create_task(self._process_connection(tg_id, wallet))

    async def _process_connection(self, tg_id: int, wallet: Any) -> None:
        address = self._extract_address(wallet)
        if not address:
            return
        try:
            # Token-based initial drops are disabled. Wallet binding starts at zero.
            self.database.bind_wallet_snapshot(tg_id, address, 0)
        except ValueError as error:
            logger.warning("Wallet binding rejected for %s: %s", tg_id, error)
        except Exception:
            logger.exception("Unexpected wallet connection error for %s", tg_id)

    @staticmethod
    def _extract_address(wallet: Any) -> str | None:
        if isinstance(wallet, dict):
            account = wallet.get("account", wallet)
            if isinstance(account, dict):
                return account.get("address")
        account = getattr(wallet, "account", None)
        if isinstance(account, dict):
            return account.get("address")
        return getattr(account, "address", None)
