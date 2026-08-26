from __future__ import annotations

import logging
from urllib.parse import quote

import aiohttp

logger = logging.getLogger(__name__)

APU_PROMPT = (
    'Transform the person in the reference image into the "Apu Apustaja" frog meme character, '
    "female version. 2D flat vector illustration, MS Paint aesthetic, thick black outlines, flat "
    "solid colors, absolutely no 3D shading or realistic textures. The character MUST have green "
    "frog skin, big bulging cartoon eyes with white circular highlights, cute blush marks on cheeks, "
    "and thick pink lips. The character must be wearing a pink hair bow on the head and a pink dress "
    "with a white Peter Pan collar and white buttons. Keep the original pose of the uploaded image. "
    "Solid white background. Cute, funny, internet meme style."
)


class ImageGenError(RuntimeError):
    pass


async def transform_to_apu(image_url: str, api_key: str) -> bytes:
    """Ask Pollinations' kontext model to turn image_url into the Apu Apustaja character."""
    if not api_key:
        raise ImageGenError("POLLINATIONS_API_KEY is not configured")
    encoded_prompt = quote(APU_PROMPT, safe="")
    url = f"https://image.pollinations.ai/prompt/{encoded_prompt}"
    params = {
        "model": "kontext",
        "image": image_url,
        "width": 1024,
        "height": 1024,
        "nologo": "true",
    }
    headers = {"Authorization": f"Bearer {api_key}"}
    timeout = aiohttp.ClientTimeout(total=90)
    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as session:
            async with session.get(url, params=params) as response:
                content_type = response.headers.get("Content-Type", "")
                if response.status != 200 or not content_type.startswith("image/"):
                    body = (await response.text())[:200]
                    raise ImageGenError(f"Pollinations request failed: HTTP {response.status} {body}")
                return await response.read()
    except aiohttp.ClientError as error:
        raise ImageGenError("Pollinations request failed") from error
