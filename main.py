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
from modules.card_formatter import build_note_fields
from modules.llm_provider import ClaudeProvider, ProviderError
from modules.profiles import ENGLISH_VOCABULARY, get_profile, validate_profile_content


BASE_DIR = Path(__file__).resolve().parent
DEFAULT_SETTINGS_FILE = BASE_DIR / "config" / "settings.json"


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


def process_item(
    item: str,
    profile_id: str,
    *,
    provider: Any,
    anki: Any,
    deck_name: str,
    legacy_path: str | Path | None,
    qa_image_path: str | Path | None,
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

    prepared_image = None
    if profile is ENGLISH_VOCABULARY:
        if qa_image_path is None:
            raise ProcessError("media", "A imagem-fixture de QA n\u00e3o foi configurada")
        prepared_image = _anki_call(
            "media",
            anki.prepare_qa_image,
            item_id,
            qa_image_path,
        )

    try:
        generated = provider.generate(profile, item)
    except Exception as exc:
        raise ProcessError("provider", str(exc)) from exc

    try:
        content = validate_profile_content(profile, generated)
    except ValueError as exc:
        raise ProcessError("validation", str(exc)) from exc

    image_filename = None
    if prepared_image is not None:
        image_filename = _anki_call("media", anki.store_qa_image, *prepared_image)

    try:
        fields = build_note_fields(profile, item, item_id, content, image_filename)
    except ValueError as exc:
        raise ProcessError("validation", str(exc)) from exc
    try:
        note_id = _anki_call("anki", anki.add_note, profile, deck_name, fields)
    except ProcessError as exc:
        context = f"{exc}; ItemId={item_id}"
        if image_filename:
            context += f"; m\u00eddia enviada={image_filename}"
        raise ProcessError(exc.stage, context, exc.outcome_uncertain) from exc
    return {
        "kind": "created",
        "item_id": item_id,
        "note_id": note_id,
    }


def _empty_result() -> dict[str, Any]:
    return {"status": "ok", "estimate": None, "created": [], "skipped": [], "error": None}


def process_request(
    profile_id: str,
    items: Iterable[str],
    *,
    provider: Any,
    anki: Any,
    deck_name: str,
    legacy_path: str | Path | None,
    qa_image_path: str | Path | None,
) -> dict[str, Any]:
    result = _empty_result()
    requested_items = list(items)
    if not requested_items:
        return _error_result("request", "O pedido deve conter ao menos um item")

    for item in requested_items:
        try:
            item_result = process_item(
                item,
                profile_id,
                provider=provider,
                anki=anki,
                deck_name=deck_name,
                legacy_path=legacy_path,
                qa_image_path=qa_image_path,
            )
        except ProcessError as exc:
            result["status"] = "error"
            result["error"] = {
                "item": item,
                "stage": exc.stage,
                "message": str(exc),
                "outcome_uncertain": exc.outcome_uncertain,
            }
            break

        if item_result["kind"] == "created":
            result["created"].append(
                {"item_id": item_result["item_id"], "note_id": item_result["note_id"]}
            )
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
        "message": message,
        "outcome_uncertain": False,
    }
    return result


def _read_json_request() -> tuple[str, list[str]]:
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
    return profile_id, items


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

        if profile is ENGLISH_VOCABULARY:
            legacy_path = _resolve_setting_path(
                settings_path, settings.get("legacy_index_path"), "legacy_index_path"
            )
            qa_image_path = _resolve_setting_path(
                settings_path, settings.get("qa_image_path"), "qa_image_path"
            )
        else:
            legacy_path = None
            qa_image_path = None
        prompt_path = settings_path.parent / profile.prompt_filename
        provider = ClaudeProvider(os.environ.get("ANTHROPIC_API_KEY"), prompt_path, model)
        anki = AnkiConnector(anki_url)
    except (ProcessError, ProviderError) as exc:
        stage = exc.stage if isinstance(exc, ProcessError) else "provider"
        return _error_result(stage, str(exc))

    return process_request(
        profile_id,
        items,
        provider=provider,
        anki=anki,
        deck_name=deck_name,
        legacy_path=legacy_path,
        qa_image_path=qa_image_path,
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.json:
        if args.profile or args.item or args.file:
            result = _error_result("request", "--json n\u00e3o pode ser combinado com --profile, --item ou --file")
        else:
            try:
                profile_id, items = _read_json_request()
            except ProcessError as exc:
                result = _error_result(exc.stage, str(exc))
            else:
                result = _run_configured(profile_id, items, args.settings)
        print(json.dumps(result, ensure_ascii=True, separators=(",", ":")))
        return 0 if result["status"] == "ok" else 1

    if not args.profile or (args.item is None and args.file is None):
        parser.error("--profile e exatamente um de --item/--file s\u00e3o obrigat\u00f3rios")
    try:
        items = [args.item] if args.item is not None else read_items_file(args.file)
        result = _run_configured(args.profile, items, args.settings)
    except ProcessError as exc:
        result = _error_result(exc.stage, str(exc))
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0 if result["status"] == "ok" else 1


if __name__ == "__main__":
    raise SystemExit(main())
