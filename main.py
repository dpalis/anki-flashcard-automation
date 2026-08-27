#!/usr/bin/env python3
"""Local, sequential entry point for Anki Automation V2."""

from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import unicodedata
from html import unescape
from pathlib import Path
from typing import Any, Iterable

from modules.anki_connector import AnkiConnectError, AnkiConnector
from modules.audio_provider import AudioProviderError, GeminiAudioProvider
from modules.card_formatter import build_note_fields
from modules.image_provider import PollinationsImageProvider
from modules.llm_provider import ClaudeProvider, ProviderError
from modules.profiles import ENGLISH_VOCABULARY, get_profile, validate_profile_content


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SETTINGS_FILE = BASE_DIR / "config" / "settings.json"
STORAGE_BYTES_PER_ITEM = {
    "english_vocabulary": (88 * 1024, 364 * 1024),
    "spanish_travel": (32 * 1024, 192 * 1024),
}
POLLINATIONS_IMAGE_ESTIMATED_COST_USD = 0.002


class ProcessError(Exception):
    def __init__(self, stage: str, message: str, outcome_uncertain: bool = False) -> None:
        super().__init__(message)
        self.stage = stage
        self.outcome_uncertain = outcome_uncertain


def canonicalize_input(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("A entrada deve ser texto")
    normalized = unicodedata.normalize("NFC", value)
    canonical = " ".join(normalized.split()).casefold()
    try:
        canonical.encode("utf-8")
    except UnicodeEncodeError as exc:
        raise ValueError("A entrada cont\u00e9m Unicode inv\u00e1lido") from exc
    return canonical


def item_id_for(profile_id: str, value: str) -> str:
    canonical = canonicalize_input(value)
    if not canonical:
        raise ValueError("A entrada n\u00e3o pode ser vazia")
    payload = profile_id.encode("utf-8") + b"\0" + canonical.encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def estimate_storage(profile_id: str, item_count: int) -> dict[str, int]:
    """Return the plan's simple media storage range for a requested batch."""
    get_profile(profile_id)
    if type(item_count) is not int or item_count < 0:
        raise ValueError("A quantidade de itens deve ser um inteiro não negativo")
    minimum, maximum = STORAGE_BYTES_PER_ITEM[profile_id]
    return {
        "items": item_count,
        "min_bytes": item_count * minimum,
        "max_bytes": item_count * maximum,
    }


def load_legacy_blocklist(path: str | Path | None) -> set[str]:
    if path is None:
        raise ProcessError("legacy", "O caminho de processadas.json n\u00e3o foi configurado")
    legacy_path = Path(path)
    try:
        with legacy_path.open("r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProcessError("legacy", f"N\u00e3o foi poss\u00edvel ler o \u00edndice legado: {legacy_path}") from exc
    if not isinstance(data, dict) or not all(isinstance(key, str) for key in data):
        raise ProcessError("legacy", "processadas.json n\u00e3o \u00e9 um objeto JSON com chaves textuais")
    try:
        blocklist = {canonicalize_input(key) for key in data}
    except ValueError as exc:
        raise ProcessError("legacy", "processadas.json cont\u00e9m uma chave inv\u00e1lida") from exc
    if "" in blocklist:
        raise ProcessError("legacy", "processadas.json cont\u00e9m uma chave vazia")
    return blocklist


def _anki_call(stage: str, function: Any, *args: Any) -> Any:
    try:
        return function(*args)
    except AnkiConnectError as exc:
        raise ProcessError(
            stage,
            f"{exc.action}: {exc}",
            outcome_uncertain=exc.outcome_uncertain,
        ) from exc


def _redact_secrets(message: str) -> str:
    redacted = message
    for name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "POLLINATIONS_API_KEY"):
        secret = os.environ.get(name)
        if secret:
            redacted = redacted.replace(secret, "[redacted]")
    return redacted


def process_item(
    item: str,
    profile_id: str,
    *,
    provider: Any,
    image_provider: Any | None,
    audio_provider: Any,
    anki: Any,
    deck_name: str,
    legacy_path: str | Path | None,
) -> dict[str, Any]:
    """Process one item. All preflight completes before the provider is called."""
    try:
        profile = get_profile(profile_id)
        item_id = item_id_for(profile_id, item)
    except ValueError as exc:
        raise ProcessError("request", str(exc)) from exc

    exact = _anki_call("identity", anki.find_exact_items, item_id)
    if len(exact) == 1:
        return {
            "kind": "skipped",
            "item_id": item_id,
            "reason": "skipped_v2",
            "existing_input": unescape(exact[0]),
        }
    if len(exact) > 1:
        raise ProcessError(
            "identity",
            f"Foram encontradas {len(exact)} notes com o mesmo ItemId; verifique no Anki",
        )

    if profile is ENGLISH_VOCABULARY:
        if canonicalize_input(item) in load_legacy_blocklist(legacy_path):
            return {
                "kind": "skipped",
                "item_id": item_id,
                "reason": "skipped_legacy",
            }

    _anki_call("preflight", anki.ensure_ready, profile, deck_name)
    image_jpg = f"aa2_{item_id}_image.jpg"
    image_png = f"aa2_{item_id}_image.png"
    audio_filename = f"aa2_{item_id}_main.mp3"
    media_candidates = [audio_filename]
    if profile is ENGLISH_VOCABULARY:
        media_candidates = [image_jpg, image_png, audio_filename]
        if image_provider is None:
            raise ProcessError("settings", "O provider de imagem inglesa não foi configurado")
    if audio_provider is None:
        raise ProcessError("settings", "O provider de áudio não foi configurado")
    _anki_call("media", anki.ensure_media_absent, media_candidates)

    try:
        generated = provider.generate(profile, item)
    except Exception as exc:
        raise ProcessError("provider", _redact_secrets(str(exc))) from exc

    try:
        content = validate_profile_content(profile, generated)
    except ValueError as exc:
        raise ProcessError("validation", str(exc)) from exc

    metrics: dict[str, Any] = {}
    text_usage = getattr(provider, "last_usage", None)
    if isinstance(text_usage, dict):
        metrics["anthropic"] = dict(text_usage)

    image_filename = None
    prepared_media: list[tuple[str, bytes]] = []
    if profile is ENGLISH_VOCABULARY:
        try:
            image_bytes, image_extension = image_provider.generate(content["visual_prompt_en"])
        except Exception as exc:
            raise ProcessError("image_provider", _redact_secrets(str(exc))) from exc
        if image_extension not in {"jpg", "png"} or not isinstance(image_bytes, bytes):
            raise ProcessError("image_provider", "A Pollinations devolveu mídia inválida")
        image_filename = f"aa2_{item_id}_image.{image_extension}"
        prepared_media.append((image_filename, image_bytes))
        metrics["pollinations"] = {
            "image_bytes": len(image_bytes),
            "estimated_cost_usd": POLLINATIONS_IMAGE_ESTIMATED_COST_USD,
        }

    audio_text = content["term"] if profile is ENGLISH_VOCABULARY else content["phrase_es"]
    audio_locale = "en-US" if profile is ENGLISH_VOCABULARY else "es-US"
    try:
        audio_bytes, audio_metrics = audio_provider.generate(audio_text, audio_locale)
    except Exception as exc:
        raise ProcessError("audio_provider", _redact_secrets(str(exc))) from exc
    if not isinstance(audio_bytes, bytes) or not isinstance(audio_metrics, dict):
        raise ProcessError("audio_provider", "O Gemini devolveu mídia ou métricas inválidas")
    prepared_media.append((audio_filename, audio_bytes))
    metrics["gemini"] = dict(audio_metrics)

    uploaded_filenames = []
    for filename, data in prepared_media:
        try:
            stored = _anki_call("media", anki.store_media_file, filename, data)
        except ProcessError as exc:
            context = f"{exc}; ItemId={item_id}; mídia atual={filename}"
            if uploaded_filenames:
                context += f"; mídias enviadas={','.join(uploaded_filenames)}"
            raise ProcessError(exc.stage, context, exc.outcome_uncertain) from exc
        uploaded_filenames.append(stored)

    try:
        fields = build_note_fields(
            profile,
            item,
            item_id,
            content,
            image_filename,
            audio_filename,
        )
    except ValueError as exc:
        raise ProcessError("validation", str(exc)) from exc
    try:
        note_id = _anki_call("anki", anki.add_note, profile, deck_name, fields)
    except ProcessError as exc:
        context = f"{exc}; ItemId={item_id}"
        if uploaded_filenames:
            context += f"; mídias enviadas={','.join(uploaded_filenames)}"
        raise ProcessError(exc.stage, context, exc.outcome_uncertain) from exc
    return {
        "kind": "created",
        "item_id": item_id,
        "note_id": note_id,
        "metrics": metrics,
    }


def _empty_result(estimate: dict[str, int] | None = None) -> dict[str, Any]:
    return {"status": "ok", "estimate": estimate, "created": [], "skipped": [], "error": None}


def process_request(
    profile_id: str,
    items: Iterable[str],
    *,
    provider: Any,
    image_provider: Any | None,
    audio_provider: Any,
    anki: Any,
    deck_name: str,
    legacy_path: str | Path | None,
) -> dict[str, Any]:
    requested_items = list(items)
    if not requested_items:
        return _error_result("request", "O pedido deve conter ao menos um item")
    result = _empty_result(estimate_storage(profile_id, len(requested_items)))

    for item in requested_items:
        try:
            item_result = process_item(
                item,
                profile_id,
                provider=provider,
                image_provider=image_provider,
                audio_provider=audio_provider,
                anki=anki,
                deck_name=deck_name,
                legacy_path=legacy_path,
            )
        except ProcessError as exc:
            result["status"] = "error"
            result["error"] = {
                "item": item,
                "stage": exc.stage,
                "message": _redact_secrets(str(exc)),
                "outcome_uncertain": exc.outcome_uncertain,
            }
            break

        if item_result["kind"] == "created":
            created = {
                "item_id": item_result["item_id"],
                "note_id": item_result["note_id"],
            }
            if item_result.get("metrics"):
                created["metrics"] = item_result["metrics"]
            result["created"].append(created)
        else:
            skipped = {
                "item_id": item_result["item_id"],
                "reason": item_result["reason"],
            }
            if "existing_input" in item_result:
                skipped["existing_input"] = item_result["existing_input"]
            result["skipped"].append(skipped)
    return result


def read_items_file(path: str | Path) -> list[str]:
    try:
        with Path(path).open("r", encoding="utf-8") as handle:
            return [line.strip() for line in handle if line.strip()]
    except (OSError, UnicodeError) as exc:
        raise ProcessError("request", f"N\u00e3o foi poss\u00edvel ler o arquivo de entrada: {path}") from exc


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Cria notes V2 de ingl\u00eas ou espanhol no Anki")
    parser.add_argument("--json", action="store_true", help="L\u00ea um pedido JSON de stdin")
    parser.add_argument("--profile", choices=("english_vocabulary", "spanish_travel"))
    source = parser.add_mutually_exclusive_group()
    source.add_argument("--item", help="Processa um item")
    source.add_argument("--file", type=Path, help="Processa um item por linha, sem alterar o arquivo")
    parser.add_argument("--settings", type=Path, default=DEFAULT_SETTINGS_FILE)
    return parser


def _error_result(stage: str, message: str, item: str | None = None) -> dict[str, Any]:
    result = _empty_result()
    result["status"] = "error"
    result["error"] = {
        "item": item,
        "stage": stage,
        "message": _redact_secrets(message),
        "outcome_uncertain": False,
    }
    return result


def _confirmation_result(profile_id: str, items: list[str]) -> dict[str, Any]:
    result = _empty_result(estimate_storage(profile_id, len(items)))
    result["status"] = "needs_confirmation"
    return result


def _read_json_request() -> tuple[str, list[str], bool]:
    try:
        request = json.load(sys.stdin)
    except (json.JSONDecodeError, OSError) as exc:
        raise ProcessError("request", f"JSON de entrada inv\u00e1lido: {exc}") from exc
    if not isinstance(request, dict) or not set(request).issubset({"profile", "items", "confirmed"}):
        raise ProcessError("request", "O pedido JSON possui campos inv\u00e1lidos")
    profile_id = request.get("profile")
    items = request.get("items")
    confirmed = request.get("confirmed", False)
    if (
        not isinstance(profile_id, str)
        or not isinstance(items, list)
        or not all(isinstance(item, str) for item in items)
    ):
        raise ProcessError("request", "O pedido JSON requer profile e uma lista textual items")
    if not isinstance(confirmed, bool):
        raise ProcessError("request", "confirmed deve ser booleano")
    return profile_id, items, confirmed


def _load_settings(path: Path) -> dict[str, Any]:
    try:
        with path.open("r", encoding="utf-8") as handle:
            settings = json.load(handle)
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        raise ProcessError("settings", f"N\u00e3o foi poss\u00edvel ler as configura\u00e7\u00f5es: {path}") from exc
    if not isinstance(settings, dict):
        raise ProcessError("settings", "O arquivo de configura\u00e7\u00f5es deve ser um objeto JSON")
    return settings


def _resolve_setting_path(settings_path: Path, value: Any, label: str) -> Path:
    if not isinstance(value, str) or not value.strip():
        raise ProcessError("settings", f"Configura\u00e7\u00e3o ausente: {label}")
    path = Path(value)
    return path if path.is_absolute() else (settings_path.parent.parent / path).resolve()


def _run_configured(profile_id: str, items: list[str], settings_path: Path) -> dict[str, Any]:
    try:
        profile = get_profile(profile_id)
    except ValueError as exc:
        return _error_result("request", str(exc))
    for item in items:
        try:
            item_id_for(profile_id, item)
        except ValueError as exc:
            return _error_result("request", str(exc), item=item)

    try:
        settings = _load_settings(settings_path)
        configured_profiles = settings.get("profiles")
        if not isinstance(configured_profiles, dict):
            raise ProcessError("settings", "Configura\u00e7\u00e3o ausente ou inv\u00e1lida: profiles")
        profile_settings = configured_profiles.get(profile_id)
        if not isinstance(profile_settings, dict):
            raise ProcessError("settings", f"Configura\u00e7\u00e3o ausente para {profile_id}")
        deck_name = profile_settings.get("deck_name")
        model = profile_settings.get("anthropic_model")
        if not isinstance(deck_name, str) or not deck_name.strip():
            raise ProcessError("settings", f"deck_name ausente para {profile_id}")
        if not isinstance(model, str) or not model.strip():
            raise ProcessError("settings", f"anthropic_model ausente para {profile_id}")
        anki_url = settings.get("anki_url", "http://localhost:8765")
        if not isinstance(anki_url, str) or not anki_url.strip():
            raise ProcessError("settings", "anki_url inv\u00e1lida")

        anthropic_key = os.environ.get("ANTHROPIC_API_KEY")
        gemini_key = os.environ.get("GEMINI_API_KEY")
        pollinations_key = os.environ.get("POLLINATIONS_API_KEY")
        missing_keys = []
        if not anthropic_key:
            missing_keys.append("ANTHROPIC_API_KEY")
        if not gemini_key:
            missing_keys.append("GEMINI_API_KEY")
        if profile is ENGLISH_VOCABULARY and not pollinations_key:
            missing_keys.append("POLLINATIONS_API_KEY")
        if missing_keys:
            raise ProcessError(
                "settings",
                f"Credencial de ambiente ausente: {', '.join(missing_keys)}",
            )

        if profile is ENGLISH_VOCABULARY:
            legacy_path = _resolve_setting_path(
                settings_path, settings.get("legacy_index_path"), "legacy_index_path"
            )
            image_provider = PollinationsImageProvider(pollinations_key)
        else:
            legacy_path = None
            image_provider = None
        prompt_path = settings_path.parent / profile.prompt_filename
        provider = ClaudeProvider(anthropic_key, prompt_path, model)
        audio_provider = GeminiAudioProvider(gemini_key)
        anki = AnkiConnector(anki_url)
    except (ProcessError, ProviderError, AudioProviderError) as exc:
        if isinstance(exc, ProcessError):
            stage = exc.stage
        elif isinstance(exc, AudioProviderError):
            stage = "audio_provider"
        else:
            stage = "provider"
        return _error_result(stage, str(exc))

    return process_request(
        profile_id,
        items,
        provider=provider,
        image_provider=image_provider,
        audio_provider=audio_provider,
        anki=anki,
        deck_name=deck_name,
        legacy_path=legacy_path,
    )


def _confirm_cli(profile_id: str, items: list[str]) -> bool:
    estimate = estimate_storage(profile_id, len(items))
    print(
        "Estimativa de mídia: "
        f"{estimate['min_bytes']}-{estimate['max_bytes']} bytes para {len(items)} itens.",
        file=sys.stderr,
    )
    print("Continuar? [s/N] ", end="", file=sys.stderr, flush=True)
    answer = sys.stdin.readline().strip().casefold()
    return answer in {"s", "sim", "y", "yes"}


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.json:
        if args.profile or args.item or args.file:
            result = _error_result("request", "--json n\u00e3o pode ser combinado com --profile, --item ou --file")
        else:
            try:
                profile_id, items, confirmed = _read_json_request()
                estimate_storage(profile_id, len(items))
            except ProcessError as exc:
                result = _error_result(exc.stage, str(exc))
            except ValueError as exc:
                result = _error_result("request", str(exc))
            else:
                if not items:
                    result = _error_result("request", "O pedido deve conter ao menos um item")
                elif len(items) > 1 and not confirmed:
                    result = _confirmation_result(profile_id, items)
                else:
                    result = _run_configured(profile_id, items, args.settings)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0 if result["status"] != "error" else 1

    if not args.profile or (args.item is None and args.file is None):
        parser.error("--profile e exatamente um de --item/--file s\u00e3o obrigat\u00f3rios")
    try:
        items = [args.item] if args.item is not None else read_items_file(args.file)
        if not items:
            result = _error_result("request", "O pedido deve conter ao menos um item")
        elif len(items) > 1 and not _confirm_cli(args.profile, items):
            result = _confirmation_result(args.profile, items)
        else:
            result = _run_configured(args.profile, items, args.settings)
    except ProcessError as exc:
        result = _error_result(exc.stage, str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] != "error" else 1


if __name__ == "__main__":
    raise SystemExit(main())
