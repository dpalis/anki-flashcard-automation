"""Direct Anthropic Structured Outputs integration for the two V2 profiles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from .profiles import Profile, validate_profile_content


class ProviderError(Exception):
    pass


class ClaudeProvider:
    def __init__(
        self,
        api_key: str | None,
        prompt_template_path: str | Path,
        model: str = "claude-sonnet-4-6",
        *,
        client: Any | None = None,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.client = client
        try:
            self.prompt_template = Path(prompt_template_path).read_text(encoding="utf-8")
        except (OSError, UnicodeError) as exc:
            raise ProviderError(f"Template de prompt n\u00e3o encontrado: {prompt_template_path}") from exc

    def _client(self) -> Any:
        if self.client is not None:
            return self.client
        if not self.api_key:
            raise ProviderError("ANTHROPIC_API_KEY n\u00e3o est\u00e1 configurada")
        try:
            import anthropic
        except ImportError as exc:
            raise ProviderError("A depend\u00eancia anthropic n\u00e3o est\u00e1 instalada") from exc
        self.client = anthropic.Anthropic(
            api_key=self.api_key,
            max_retries=0,
            timeout=60.0,
        )
        return self.client

    def generate(self, profile: Profile, item: str) -> dict[str, Any]:
        prompt = f"{self.prompt_template.rstrip()}\n\nEntrada do usu\u00e1rio: {item}"
        try:
            message = self._client().messages.create(
                model=self.model,
                max_tokens=2500,
                messages=[{"role": "user", "content": prompt}],
                output_config={
                    "format": {
                        "type": "json_schema",
                        "schema": profile.output_schema,
                    }
                },
            )
        except ProviderError:
            raise
        except Exception as exc:
            message_text = str(exc)
            if self.api_key:
                message_text = message_text.replace(self.api_key, "[redacted]")
            raise ProviderError(f"Falha na API da Anthropic: {message_text}") from exc

        if getattr(message, "stop_reason", None) == "refusal":
            raise ProviderError("A Anthropic recusou a gera\u00e7\u00e3o")
        if getattr(message, "stop_reason", None) == "max_tokens":
            raise ProviderError("A resposta estruturada atingiu o limite de tokens")

        text = None
        for block in getattr(message, "content", []):
            block_type = getattr(block, "type", None)
            if block_type == "refusal":
                raise ProviderError("A Anthropic recusou a gera\u00e7\u00e3o")
            if block_type == "text":
                text = getattr(block, "text", None)
                if text:
                    break
        if not text:
            raise ProviderError("A Anthropic n\u00e3o devolveu conte\u00fado estruturado")

        try:
            content = json.loads(text)
        except (TypeError, json.JSONDecodeError) as exc:
            raise ProviderError("A Anthropic devolveu JSON inv\u00e1lido") from exc
        try:
            return validate_profile_content(profile, content)
        except ValueError as exc:
            raise ProviderError(f"Resposta estruturada inv\u00e1lida: {exc}") from exc
