"""Concrete Pollinations adapter for V2 images."""

from __future__ import annotations

from typing import Any
from urllib.parse import quote

import requests


POLLINATIONS_ENDPOINT = "https://gen.pollinations.ai/image"
POLLINATIONS_IMAGE_SIZE = 1024
MIN_IMAGE_BYTES = 512


class ImageProviderError(RuntimeError):
    pass


class PollinationsImageProvider:
    """Generate one validated Flux image without local persistence."""

    def __init__(
        self,
        api_key: str | None,
        *,
        session: Any | None = None,
        timeout: float = 60,
    ) -> None:
        self.api_key = api_key or ""
        self.session = session or requests.Session()
        self.timeout = timeout

    def generate(self, prompt: str) -> tuple[bytes, str]:
        """Return validated image bytes and their deterministic extension."""
        if not self.api_key:
            raise ImageProviderError("POLLINATIONS_API_KEY não está configurada")
        if not isinstance(prompt, str) or not prompt.strip():
            raise ImageProviderError("O prompt visual não pode ser vazio")

        url = f"{POLLINATIONS_ENDPOINT}/{quote(prompt, safe='')}"
        try:
            response = self.session.get(
                url,
                params={
                    "model": "flux",
                    "width": POLLINATIONS_IMAGE_SIZE,
                    "height": POLLINATIONS_IMAGE_SIZE,
                },
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Accept": "image/jpeg,image/png",
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
        except requests.RequestException as exc:
            raise ImageProviderError(
                f"Falha na API de imagem Pollinations: {self._redact(str(exc))}"
            ) from exc

        data = response.content
        content_type = str(response.headers.get("Content-Type") or "")
        mime_type = content_type.split(";", 1)[0].strip().casefold()
        if not isinstance(data, bytes) or len(data) < MIN_IMAGE_BYTES:
            raise ImageProviderError("A Pollinations devolveu uma imagem vazia ou pequena demais")
        if mime_type == "image/jpeg" and data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
            return data, "jpg"
        if mime_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
            return data, "png"
        raise ImageProviderError("A Pollinations não devolveu JPEG ou PNG válido")

    def _redact(self, value: str) -> str:
        return value.replace(self.api_key, "[redacted]") if self.api_key else value
