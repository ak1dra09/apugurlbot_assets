from __future__ import annotations

import aiohttp
from ton_core import Address


class TonApiError(RuntimeError):
    pass


class TonApi:
    def __init__(self, jetton_master_address: str, api_key: str | None = None) -> None:
        self.jetton_master_address = jetton_master_address
        self.api_key = api_key
        self.base_url = "https://tonapi.io/v2"

    async def _get(self, path: str, params: dict | None = None) -> dict:
        headers = {"Authorization": f"Bearer {self.api_key}"} if self.api_key else {}
        url = f"{self.base_url}{path}"
        try:
            timeout = aiohttp.ClientTimeout(total=15)
            async with aiohttp.ClientSession(headers=headers, timeout=timeout) as session:
                async with session.get(url, params=params) as response:
                    if response.status != 200:
                        raise TonApiError(f"TonAPI returned HTTP {response.status}")
                    return await response.json()
        except (aiohttp.ClientError, TimeoutError) as error:
            raise TonApiError("TonAPI request failed") from error

    async def get_jetton_balance(self, wallet_address: str) -> int:
        payload = await self._get(f"/accounts/{wallet_address}/jettons")
        target = Address(self.jetton_master_address)
        for item in payload.get("balances", []):
            jetton = item.get("jetton", {})
            address = jetton.get("address")
            if not address:
                continue
            try:
                if Address(address) != target:
                    continue
            except Exception:
                continue
            try:
                return int(item.get("balance", 0))
            except (TypeError, ValueError) as error:
                raise TonApiError("TonAPI returned an invalid balance") from error
        return 0

    async def get_jetton_total_supply(self) -> int:
        payload = await self._get(f"/jettons/{self.jetton_master_address}")
        try:
            return int(payload.get("total_supply", 0))
        except (TypeError, ValueError) as error:
            raise TonApiError("TonAPI returned an invalid total supply") from error

    async def get_incoming_jetton_transfers(self, wallet_address: str, after_lt: int) -> list[dict]:
        """Return new JettonTransfer actions received by wallet_address since after_lt.

        Each item: {event_id, lt, raw_amount, sender_address, comment}
        """
        params = {
            "limit": 100,
            "sort_order": "asc",
            "subject_only": "true",
        }
        if after_lt:
            params["after_lt"] = after_lt
        payload = await self._get(f"/accounts/{wallet_address}/events", params=params)
        target = Address(self.jetton_master_address)
        transfers: list[dict] = []
        for event in payload.get("events", []):
            if event.get("in_progress"):
                continue
            lt = event.get("lt")
            for action in event.get("actions", []):
                if action.get("type") != "JettonTransfer" or action.get("status") != "ok":
                    continue
                data = action.get("JettonTransfer") or {}
                jetton = data.get("jetton") or {}
                address = jetton.get("address")
                if not address:
                    continue
                try:
                    if Address(address) != target:
                        continue
                except Exception:
                    continue
                recipient = (data.get("recipient") or {}).get("address")
                try:
                    if recipient and Address(recipient) != Address(wallet_address):
                        continue
                except Exception:
                    pass
                try:
                    raw_amount = int(data.get("amount", 0))
                except (TypeError, ValueError):
                    continue
                sender_address = (data.get("sender") or {}).get("address")
                transfers.append(
                    {
                        "event_id": event.get("event_id"),
                        "lt": lt,
                        "raw_amount": raw_amount,
                        "sender_address": sender_address,
                        "comment": data.get("comment"),
                    }
                )
        return transfers


# Example request made by get_jetton_balance:
# GET https://tonapi.io/v2/accounts/<WALLET_ADDRESS>/jettons
# Authorization: Bearer <TONAPI_KEY>  (optional for low-volume/public access)
# Then select balances[].jetton.address == JETTON_MASTER_ADDRESS (compared as parsed
# TON addresses, since TonAPI returns raw "0:hex" form while config may use EQ/UQ form).
#
# Example request made by get_incoming_jetton_transfers:
# GET https://tonapi.io/v2/accounts/<WALLET_ADDRESS>/events?after_lt=<LT>&limit=100&sort_order=asc&subject_only=true
# Then select actions[] where type == "JettonTransfer" and JettonTransfer.jetton.address
# matches JETTON_MASTER_ADDRESS, reading amount/sender/comment from JettonTransfer.
