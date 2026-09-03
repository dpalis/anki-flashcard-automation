"""Concrete Pollinations adapter for V2 images."""

from __future__ import annotations

import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests


POLLINATIONS_ENDPOINT = "https://gen.pollinations.ai/image"
POLLINATIONS_IMAGE_SIZE = 1024
MIN_IMAGE_BYTES = 512
VISION_HELPER = Path(__file__).resolve().parents[1] / "scripts" / "detect_visible_text.swift"
NO_TEXT_PREFIX = (
    "IMPORTANT: No text, no words, no letters, no numbers, no text-like symbols, "
    "no signs, no labels, no logos, no typography of any kind. "
)


class ImageProviderError(RuntimeError):
    pass


def detect_visible_text(data: bytes, extension: str) -> tuple[str, ...]:
    """Return OCR findings from one generated image using native macOS Vision."""
    if not VISION_HELPER.is_file():
        raise ImageProviderError("O verificador local de texto da imagem não foi encontrado")

    try:
        cache_dir = Path(tempfile.gettempdir()) / "anki-automation-swift-cache"
        cache_dir.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="anki-image-check-") as temporary:
            image_path = Path(temporary) / f"image.{extension}"
            image_path.write_bytes(data)
            environment = os.environ.copy()
            environment["SWIFT_MODULECACHE_PATH"] = str(cache_dir)
            environment["CLANG_MODULE_CACHE_PATH"] = str(cache_dir)
            completed = subprocess.run(
                ["/usr/bin/swift", str(VISION_HELPER), str(image_path)],
                check=True,
                capture_output=True,
                text=True,
                timeout=45,
                env=environment,
            )
    except subprocess.TimeoutExpired as exc:
        raise ImageProviderError("A verificação local da imagem excedeu o tempo limite") from exc
    except subprocess.CalledProcessError as exc:
        detail = str(exc.stderr or "Vision falhou").strip()
        raise ImageProviderError(f"Falha ao verificar texto na imagem: {detail}") from exc
    except OSError as exc:
        raise ImageProviderError(f"Falha ao executar a verificação local da imagem: {exc}") from exc

    return tuple(
        line.strip()
        for line in completed.stdout.splitlines()
        if line.strip() and any(character.isalnum() for character in line)
    )


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

        visual_prompt = f"{NO_TEXT_PREFIX}{prompt.strip()}"
        url = f"{POLLINATIONS_ENDPOINT}/{quote(visual_prompt, safe='')}"
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
            extension = "jpg"
        elif mime_type == "image/png" and data.startswith(b"\x89PNG\r\n\x1a\n"):
            extension = "png"
        else:
            raise ImageProviderError("A Pollinations não devolveu JPEG ou PNG válido")

        findings = detect_visible_text(data, extension)
        if findings:
            summary = "; ".join(findings[:3])
            raise ImageProviderError(
                f"A imagem gerada contém texto ou números legíveis ({summary}); "
                "nenhum áudio ou card foi criado"
            )
        return data, extension

    def _redact(self, value: str) -> str:
        return value.replace(self.api_key, "[redacted]") if self.api_key else value
