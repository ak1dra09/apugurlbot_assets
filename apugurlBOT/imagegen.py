from __future__ import annotations

import base64
import logging

import aiohttp

logger = logging.getLogger(__name__)

API_URL = "https://gen.pollinations.ai/v1/images/edits"

APU_PROMPT = (
    'Transform the person in the reference image into the "Apu Apustaja" frog meme character, '
    "female version. 2D flat vector illustration, MS Paint aesthetic, thick black outlines, flat "
    "solid colors, absolutely no 3D shading or realistic textures. The character MUST have green "
    "frog skin, big bulging cartoon eyes with white circular highlights, cute blush marks on cheeks, "
    "and thick pink lips. The character must be wearing a pink hair bow on the head and a pink dress "
    "with a white Peter Pan collar and white buttons. Keep the original pose of the uploaded image. "
    "Solid white background. Cute, funny, internet meme style."
)

REQUEST_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    ),
}


class ImageGenError(RuntimeError):
    pass


async def transform_to_apu(image_url: str, api_key: str) -> bytes:
    """Ask Pollinations' kontext model to turn image_url into the Apu Apustaja character."""
    if not api_key:
        raise ImageGenError("POLLINATIONS_API_KEY is not configured")
    payload = {
        "prompt": APU_PROMPT,
        "model": "kontext",
        "image": image_url,
        "response_format": "b64_json",
        "n": 1,
    }
    headers = {**REQUEST_HEADERS, "Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=90)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.post(API_URL, json=payload) as response:
                if response.status != 200:
                    body = (await response.text())[:300]
                    raise ImageGenError(f"Pollinations request failed: HTTP {response.status} {body}")
                data = await response.json()
        items = data.get("data") or []
        if not items or not items[0].get("b64_json"):
            raise ImageGenError(f"Pollinations returned no image data: {str(data)[:300]}")
        return base64.b64decode(items[0]["b64_json"])
    except aiohttp.ClientError as error:
        raise ImageGenError("Pollinations request failed") from error
