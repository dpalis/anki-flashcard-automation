"""Small HTML formatter for the two V2 note types."""

from __future__ import annotations

from html import escape
from typing import Any

from .profiles import ENGLISH_VOCABULARY, SPANISH_TRAVEL, Profile


def _html(value: Any) -> str:
    return escape(str(value), quote=True)


def _english_senses(content: dict[str, Any]) -> str:
    rendered = []
    for sense in content["senses"]:
        rendered.append(
            '<section class="sense">'
            f'<div class="definition-en">{_html(sense["definition_en"])}</div>'
            f'<div class="meaning-pt-br">{_html(sense["meaning_pt_br"])}</div>'
            f'<div class="example-en">{_html(sense["example_en"])}</div>'
            f'<div class="example-pt-br">{_html(sense["example_pt_br"])}</div>'
            "</section>"
        )
    return "".join(rendered)


def build_note_fields(
    profile: Profile,
    raw_input: str,
    item_id: str,
    content: dict[str, Any],
    image_filename: str | None = None,
    main_audio_filename: str | None = None,
) -> dict[str, str]:
    """Build escaped Anki fields for the two fixed profiles."""
    if not main_audio_filename:
        raise ValueError("O áudio principal V2 é obrigatório")
    main_audio = f"[sound:{_html(main_audio_filename)}]"
    if profile is ENGLISH_VOCABULARY:
        if not image_filename:
            raise ValueError("O perfil ingl\u00eas requer imagem")
        return {
            "ItemId": item_id,
            "Input": _html(raw_input),
            "Term": _html(content["term"]),
            "IPA": _html(content["ipa"]),
            "PartsOfSpeech": " / ".join(_html(part) for part in content["parts_of_speech"]),
            "SensesHtml": _english_senses(content),
            "Image": f'<img src="{_html(image_filename)}">',
            "MainAudio": main_audio,
            "ExampleAudio": "",
        }

    if profile is SPANISH_TRAVEL:
        return {
            "ItemId": item_id,
            "Input": _html(raw_input),
            "PhraseEs": _html(content["phrase_es"]),
            "TranslationPtBr": _html(content["translation_pt_br"]),
            "UsageContextPtBr": _html(content["usage_context_pt_br"]),
            "Register": _html(content["register"]),
            "ExampleEs": _html(content["example_es"]),
            "ExamplePtBr": _html(content["example_pt_br"]),
            "MainAudio": main_audio,
            "ExampleAudio": "",
        }

    raise ValueError(f"Perfil desconhecido: {profile.profile_id}")
