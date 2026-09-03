"""Render the shared V2 card layout for English and Spanish."""

from __future__ import annotations

import re
from html import escape
from typing import Any

from .profiles import ENGLISH_VOCABULARY, SPANISH_TRAVEL, Profile


def _html(value: Any) -> str:
    return escape(str(value), quote=True)


def _english_target(content: dict[str, Any]) -> str:
    term = content["term"].strip()
    has_to = term.casefold().startswith("to ")
    lexical_term = term[3:].strip() if has_to else term
    verbal_only = all(
        re.search(r"\bverb\b", part.casefold()) is not None
        for part in content["parts_of_speech"]
    )
    return f"to {lexical_term}" if verbal_only else lexical_term


def _content_parts(
    profile: Profile,
    content: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]], str, str, str]:
    if profile is ENGLISH_VOCABULARY:
        classification = " / ".join(
            part.strip().capitalize() for part in content["parts_of_speech"]
        )
        return (
            _english_target(content),
            content["ipa"],
            content["senses"],
            "definition_en",
            "example_en",
            classification,
        )
    if profile is SPANISH_TRAVEL:
        return (
            content["phrase_es"],
            content["ipa"],
            content["senses"],
            "definition_es",
            "example_es",
            content["register"].strip().capitalize(),
        )
    raise ValueError(f"Perfil desconhecido: {profile.profile_id}")


def _render_content(profile: Profile, content: dict[str, Any]) -> tuple[str, str]:
    target, ipa, senses, definition_field, example_field, classification = _content_parts(
        profile, content
    )
    ipa = ipa.strip()
    if ipa.startswith("[") and ipa.endswith("]"):
        ipa = ipa[1:-1].strip()
    if not (ipa.startswith("/") and ipa.endswith("/")):
        ipa = f"/{ipa.strip('/')}/"

    meanings = []
    for index, sense in enumerate(senses):
        margin = ' style="margin-top:1em;"' if index else ""
        meanings.append(f"<div{margin}>{_html(sense[definition_field])}</div>")

    examples = "".join(
        f"<div>Ex.: {_html(sense[example_field])}</div>" for sense in senses
    )
    translations = " / ".join(_html(sense["meaning_pt_br"]) for sense in senses)
    metadata = (
        f"<div>{translations}</div>"
        f"<div>{_html(classification)}</div>"
        f"<div>{_html(ipa)}</div>"
    )
    body = (
        "".join(meanings)
        + f'<div style="margin-top:1em;">{examples}</div>'
        + f'<div style="margin-top:1em;">{metadata}</div>'
    )
    return _html(target), body


def build_note_fields(
    profile: Profile,
    raw_input: str,
    item_id: str,
    content: dict[str, Any],
    image_filename: str | None = None,
    main_audio_filename: str | None = None,
) -> dict[str, str]:
    """Build the exact shared field contract for one V2 note."""
    if not image_filename:
        raise ValueError("A imagem V2 é obrigatória")
    if not main_audio_filename:
        raise ValueError("O áudio principal V2 é obrigatório")

    target, body = _render_content(profile, content)
    return {
        "ItemId": item_id,
        "Input": _html(raw_input),
        "Target": target,
        "ContentHtml": body,
        "Image": (
            f'<img src="{_html(image_filename)}" '
            'style="max-width:100%;height:auto;">'
        ),
        "MainAudio": f"[sound:{_html(main_audio_filename)}]",
    }
