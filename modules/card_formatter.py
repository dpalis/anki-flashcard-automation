"""Render the shared V2 card layout for every registered language profile."""

from __future__ import annotations

import re
from html import escape
from typing import Any

from .profiles import Profile


def _html(value: Any) -> str:
    return escape(str(value), quote=True)


def _target(profile: Profile, content: dict[str, Any]) -> str:
    target = content[profile.romanization_field or profile.target_field].strip()
    marker = profile.identity_alias_prefix
    if marker is None:
        return target
    has_marker = target.casefold().startswith(marker)
    lexical_target = target[len(marker):].strip() if has_marker else target
    verbal_only = all(
        re.search(r"\bverb\b", part.casefold()) is not None
        for part in content[profile.classification_field]
    )
    return f"{marker}{lexical_target}" if verbal_only else lexical_target


def _content_parts(
    profile: Profile,
    content: dict[str, Any],
) -> tuple[str, str, list[dict[str, Any]], str, str, str]:
    classification_value = content[profile.classification_field]
    if profile.classification_multiple:
        classification = " / ".join(
            value.strip().capitalize() for value in classification_value
        )
    else:
        classification = classification_value.strip().capitalize()
    return (
        _target(profile, content),
        content[profile.pronunciation_field],
        content["senses"],
        profile.definition_field,
        profile.example_field,
        classification,
    )


def _render_content(profile: Profile, content: dict[str, Any]) -> tuple[str, str]:
    target, ipa, senses, definition_field, example_field, classification = _content_parts(
        profile, content
    )
    pronunciation = ipa.strip()
    if pronunciation.startswith("[") and pronunciation.endswith("]"):
        pronunciation = pronunciation[1:-1].strip()
    if not (pronunciation.startswith("/") and pronunciation.endswith("/")):
        pronunciation = f"/{pronunciation.strip('/')}/"

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
        f"<div>{_html(pronunciation)}</div>"
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
