"""Concrete Gemini TTS adapter for V2 main audio."""

from __future__ import annotations

import base64
import io
import shutil
import subprocess
import tempfile
import wave
from pathlib import Path
from typing import Any, Callable

import requests


GEMINI_AUDIO_ENDPOINT = "https://generativelanguage.googleapis.com/v1beta/interactions"
GEMINI_AUDIO_MODEL = "gemini-3.1-flash-tts-preview"
GEMINI_AUDIO_VOICE = "Iapetus"
GEMINI_API_REVISION = "2026-05-20"
SUPPORTED_LOCALES = frozenset({"en-US", "es-US"})
MIN_MP3_BYTES = 512


class AudioProviderError(RuntimeError):
    pass


class GeminiAudioProvider:
    """Generate one MP3 with the fixed Gemini model and Iapetus voice."""

    def __init__(
        self,
        api_key: str | None,
        *,
        session: Any | None = None,
        timeout: float = 120,
        ffmpeg_path: str = "ffmpeg",
        run_command: Callable[..., Any] = subprocess.run,
    ) -> None:
        self.api_key = api_key or ""
        self.session = session or requests.Session()
        self.timeout = timeout
        self.ffmpeg_path = ffmpeg_path
        self.run_command = run_command
        if shutil.which(self.ffmpeg_path) is None:
            raise AudioProviderError("ffmpeg não está disponível para converter o áudio")

    def generate(self, text: str, locale: str) -> tuple[bytes, dict[str, Any]]:
        """Generate one 24 kHz mono 96 kb/s MP3 and return its usage metrics."""
        if not self.api_key:
            raise AudioProviderError("GEMINI_API_KEY não está configurada")
        if locale not in SUPPORTED_LOCALES:
            raise AudioProviderError(f"Locale de áudio não suportado: {locale}")
        if not isinstance(text, str) or not text.strip():
            raise AudioProviderError("O texto do áudio não pode ser vazio")
        payload = {
            "model": GEMINI_AUDIO_MODEL,
            "input": self._prompt(text, locale),
            "response_format": {"type": "audio"},
            "generation_config": {
                "speech_config": [
                    {
                        "voice": GEMINI_AUDIO_VOICE,
                        "language": locale,
                    }
                ]
            },
            "store": False,
        }
        try:
            response = self.session.post(
                GEMINI_AUDIO_ENDPOINT,
                json=payload,
                headers={
                    "Api-Revision": GEMINI_API_REVISION,
                    "Content-Type": "application/json",
                    "x-goog-api-key": self.api_key,
                },
                timeout=self.timeout,
            )
            response.raise_for_status()
            envelope = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AudioProviderError(
                f"Falha na API de áudio Gemini: {self._redact(str(exc))}"
            ) from exc

        audio_block = self._single_audio_block(envelope)
        wav_bytes = self._wav_bytes(audio_block)
        mp3_bytes = self._convert_to_mp3(wav_bytes)
        metrics = self._usage_metrics(envelope, len(mp3_bytes))
        return mp3_bytes, metrics

    @staticmethod
    def _prompt(text: str, locale: str) -> str:
        if locale == "en-US":
            instruction = (
                "Read only the transcript below, exactly once, without an introduction "
                "or extra words. Use clear, natural contemporary American English at a "
                "comfortable study pace."
            )
        else:
            instruction = (
                "Read only the transcript below, exactly once, without an introduction "
                "or extra words. Use neutral Latin American Spanish as spoken across the "
                "Americas, without a country-specific accent, at a comfortable study pace."
            )
        return f"{instruction}\n\nTRANSCRIPT:\n{text}"

    @staticmethod
    def _single_audio_block(envelope: Any) -> dict[str, Any]:
        if not isinstance(envelope, dict) or envelope.get("status") != "completed":
            raise AudioProviderError("A interação Gemini não foi concluída")
        steps = envelope.get("steps")
        if not isinstance(steps, list):
            raise AudioProviderError("A resposta Gemini não contém steps válidos")

        audio_blocks = []
        for step in steps:
            if not isinstance(step, dict):
                raise AudioProviderError("A resposta Gemini contém um step inválido")
            content = step.get("content")
            if not isinstance(content, list):
                raise AudioProviderError("A resposta Gemini contém content inválido")
            for block in content:
                if isinstance(block, dict) and block.get("type") == "audio":
                    audio_blocks.append(block)
        if len(audio_blocks) != 1:
            raise AudioProviderError(
                f"A resposta Gemini trouxe {len(audio_blocks)} blocos de áudio; esperado: 1"
            )
        return audio_blocks[0]

    @staticmethod
    def _wav_bytes(audio: dict[str, Any]) -> bytes:
        try:
            raw = base64.b64decode(audio["data"], validate=True)
        except (KeyError, TypeError, ValueError) as exc:
            raise AudioProviderError("O Gemini devolveu áudio base64 inválido") from exc

        mime_type = str(audio.get("mime_type") or "").split(";", 1)[0].strip().casefold()
        if raw[:4] == b"RIFF" and raw[8:12] == b"WAVE":
            if mime_type and mime_type not in {"audio/wav", "audio/wave", "audio/x-wav"}:
                raise AudioProviderError(f"MIME de áudio inesperado: {mime_type}")
            GeminiAudioProvider._validate_wav(raw)
            return raw

        mime_type = mime_type or "audio/l16"
        if mime_type != "audio/l16":
            raise AudioProviderError(f"MIME de áudio inesperado: {mime_type or 'ausente'}")
        try:
            sample_rate_value = audio.get("sample_rate", 24000)
            channels_value = audio.get("channels", 1)
            sample_rate = int(24000 if sample_rate_value is None else sample_rate_value)
            channels = int(1 if channels_value is None else channels_value)
        except (TypeError, ValueError) as exc:
            raise AudioProviderError("O PCM Gemini não informa sample rate e canais válidos") from exc
        if sample_rate != 24000 or channels != 1 or len(raw) < 2 or len(raw) % 2:
            raise AudioProviderError("O Gemini não devolveu PCM L16 mono a 24 kHz válido")

        target = io.BytesIO()
        with wave.open(target, "wb") as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(24000)
            wav_file.writeframes(raw)
        return target.getvalue()

    @staticmethod
    def _validate_wav(data: bytes) -> None:
        try:
            with wave.open(io.BytesIO(data), "rb") as wav_file:
                valid = (
                    wav_file.getnchannels() == 1
                    and wav_file.getsampwidth() == 2
                    and wav_file.getframerate() == 24000
                    and wav_file.getnframes() > 0
                )
        except (EOFError, wave.Error) as exc:
            raise AudioProviderError("O Gemini devolveu WAV inválido") from exc
        if not valid:
            raise AudioProviderError("O Gemini não devolveu WAV L16 mono a 24 kHz válido")

    def _convert_to_mp3(self, wav_bytes: bytes) -> bytes:
        with tempfile.TemporaryDirectory(prefix="anki-audio-") as temporary:
            base = Path(temporary)
            wav_path = base / "input.wav"
            part_path = base / "output.part.mp3"
            wav_path.write_bytes(wav_bytes)
            command = [
                self.ffmpeg_path,
                "-nostdin",
                "-hide_banner",
                "-loglevel",
                "error",
                "-n",
                "-i",
                str(wav_path),
                "-map_metadata",
                "-1",
                "-vn",
                "-ac",
                "1",
                "-ar",
                "24000",
                "-c:a",
                "libmp3lame",
                "-b:a",
                "96k",
                str(part_path),
            ]
            try:
                self.run_command(
                    command,
                    check=True,
                    capture_output=True,
                    text=True,
                    timeout=self.timeout,
                )
                mp3_bytes = part_path.read_bytes()
            except subprocess.TimeoutExpired as exc:
                raise AudioProviderError(
                    "A conversão de áudio excedeu o tempo limite"
                ) from exc
            except subprocess.CalledProcessError as exc:
                detail = self._redact(str(exc.stderr or "ffmpeg falhou"))
                raise AudioProviderError(f"Falha ao converter áudio para MP3: {detail}") from exc
            except OSError as exc:
                raise AudioProviderError(f"Falha ao executar ffmpeg: {exc}") from exc
            if not self._is_mp3(mp3_bytes):
                raise AudioProviderError("O ffmpeg não produziu um MP3 válido")
            return mp3_bytes

    @staticmethod
    def _is_mp3(data: bytes) -> bool:
        if len(data) < MIN_MP3_BYTES:
            return False
        if data.startswith(b"ID3"):
            return True
        limit = min(len(data) - 1, 4096)
        return any(
            data[index] == 0xFF and data[index + 1] & 0xE0 == 0xE0
            for index in range(max(limit, 0))
        )

    @staticmethod
    def _token_count(usage: Any, field: str, modality: str) -> int | None:
        if not isinstance(usage, dict):
            return None
        entries = usage.get(field)
        if not isinstance(entries, list):
            return None
        for entry in entries:
            if isinstance(entry, dict) and entry.get("modality") == modality:
                value = entry.get("tokens")
                if type(value) is int and value >= 0:
                    return value
        return None

    @classmethod
    def _usage_metrics(cls, envelope: dict[str, Any], mp3_bytes: int) -> dict[str, Any]:
        usage = envelope.get("usage")
        input_tokens = cls._token_count(usage, "input_tokens_by_modality", "text")
        audio_tokens = cls._token_count(usage, "output_tokens_by_modality", "audio")
        estimated_cost = None
        if input_tokens is not None and audio_tokens is not None:
            estimated_cost = round(
                input_tokens / 1_000_000 + audio_tokens * 20 / 1_000_000,
                8,
            )
        return {
            "input_tokens": input_tokens,
            "audio_tokens": audio_tokens,
            "mp3_bytes": mp3_bytes,
            "estimated_cost_usd": estimated_cost,
        }

    def _redact(self, value: str) -> str:
        return value.replace(self.api_key, "[redacted]") if self.api_key else value
