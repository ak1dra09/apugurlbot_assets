from __future__ import annotations

import logging

from ton_core import Address, NetworkGlobalID, to_nano
from tonutils.clients import TonapiClient
from tonutils.contracts import JettonTransferBuilder, WalletV5R1

logger = logging.getLogger(__name__)


class HotWalletError(RuntimeError):
    pass


class HotWallet:
    """Sends $APUGURL jetton withdrawals from a dedicated hot wallet."""

    def __init__(
        self,
        mnemonic: str,
        jetton_master_address: str,
        decimals: int,
        tonapi_key: str | None = None,
    ) -> None:
        self.mnemonic = mnemonic
        self.jetton_master_address = jetton_master_address
        self.decimals = decimals
        self.tonapi_key = tonapi_key

    async def send_jetton(self, destination_address: str, amount: int) -> str:
        """Send `amount` whole $APUGURL tokens to destination_address. Returns the tx hash."""
        if not self.mnemonic:
            raise HotWalletError("HOT_WALLET_MNEMONIC is not configured")
        try:
            destination = Address(destination_address)
        except Exception as error:
            raise HotWalletError("Invalid destination address") from error

        client = TonapiClient(network=NetworkGlobalID.MAINNET, api_key=self.tonapi_key)
        await client.connect()
        try:
            wallet, _, _, _ = WalletV5R1.from_mnemonic(client, self.mnemonic)
            jetton_amount = to_nano(amount, decimals=self.decimals)
            message = await wallet.transfer_message(
                JettonTransferBuilder(
                    destination=destination,
                    jetton_amount=jetton_amount,
                    jetton_master_address=Address(self.jetton_master_address),
                    forward_amount=1,
                    amount=to_nano(0.05),
                )
            )
            return message.normalized_hash
        except Exception as error:
            logger.exception("Failed to send withdrawal to %s", destination_address)
            raise HotWalletError(str(error)) from error
        finally:
            await client.close()
