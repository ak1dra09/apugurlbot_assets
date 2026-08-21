from __future__ import annotations

import json
from pathlib import Path

from aiohttp import web

from wallet import WalletManager


class ConnectWebServer:
    def __init__(self, wallets: WalletManager, manifest_url: str, host: str, port: int) -> None:
        self.wallets = wallets
        self.manifest_url = manifest_url
        self.host = host
        self.port = port
        self.runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/connect", self.connect_page)
        app.router.add_post("/wallet-connected", self.wallet_connected)
        app.router.add_get("/tonconnect-manifest.json", self.manifest)
        self.runner = web.AppRunner(app)
        await self.runner.setup()
        await web.TCPSite(self.runner, self.host, self.port).start()

    async def stop(self) -> None:
        if self.runner:
            await self.runner.cleanup()

    async def connect_page(self, request: web.Request) -> web.Response:
        token = request.query.get("token")
        if not token:
            raise web.HTTPBadRequest(text="Missing connection token")
        page = (Path(__file__).with_name("connect.html")).read_text(encoding="utf-8")
        page = page.replace("__MANIFEST_URL__", self.manifest_url)
        return web.Response(text=page, content_type="text/html")

    async def wallet_connected(self, request: web.Request) -> web.Response:
        try:
            payload = await request.json()
            token = str(payload["token"])
            address = str(payload["address"])
            if not address or len(address) > 128:
                raise ValueError("invalid_address")
            await self.wallets.complete_connection(token, address)
        except (KeyError, json.JSONDecodeError, ValueError) as error:
            return web.json_response({"ok": False, "error": str(error)}, status=400)
        except Exception:
            return web.json_response({"ok": False, "error": "connection_failed"}, status=500)
        return web.json_response({"ok": True})

    async def manifest(self, request: web.Request) -> web.Response:
        path = Path(__file__).with_name("tonconnect-manifest.json")
        return web.json_response(json.loads(path.read_text(encoding="utf-8")))
