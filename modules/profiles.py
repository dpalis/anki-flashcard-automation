"""Explicit language profiles for the shared V2 study-card contract."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Mapping


CARD_FIELDS = (
    "ItemId",
    "Input",
    "Target",
    "ContentHtml",
    "Image",
    "MainAudio",
)

CARD_CSS = (
    ".card {\n"
    "    font-family: arial;\n"
    "    font-size: 20px;\n"
    "    text-align: center;\n"
    "    color: black;\n"
    "    background-color: white;\n"
    "}\n"
)
TARGET_HTML = '<div style="color:#0000ff;font-weight:700;">{{Target}}</div>'
CONTENT_HTML = '<div style="margin-top:1em;">{{ContentHtml}}</div>'
AUDIO_HTML = '<div style="margin-top:1em;">{{MainAudio}}</div>'
ANSWER_PREFIX = "{{FrontSide}}\n\n<hr id=answer>\n\n"

CARD_TEMPLATES = {
    "Target to Meaning": {
        "Front": TARGET_HTML,
        "Back": ANSWER_PREFIX + "\n".join(("{{Image}}", CONTENT_HTML, AUDIO_HTML)),
    },
    "Image to Target": {
        "Front": "{{Image}}",
        "Back": ANSWER_PREFIX + "\n".join((TARGET_HTML, CONTENT_HTML, AUDIO_HTML)),
    },
}

SPANISH_REGISTERS = ("neutral", "informal", "formal")
JAPANESE_REGISTERS = ("neutral", "informal", "polite", "formal")


def _language_schema(
    *,
    target_field: str,
    pronunciation_field: str,
    classification_field: str,
    classification_schema: Mapping[str, Any],
    definition_field: str,
    example_field: str,
) -> dict[str, Any]:
    return {
        "type": "object",
        "properties": {
            target_field: {"type": "string"},
            pronunciation_field: {"type": "string"},
            classification_field: dict(classification_schema),
            "senses": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        definition_field: {"type": "string"},
                        "meaning_pt_br": {"type": "string"},
                        example_field: {"type": "string"},
                    },
                    "required": [definition_field, "meaning_pt_br", example_field],
                    "additionalProperties": False,
                },
            },
            "visual_prompt_en": {"type": "string"},
        },
        "required": [
            target_field,
            pronunciation_field,
            classification_field,
            "senses",
            "visual_prompt_en",
        ],
        "additionalProperties": False,
    }


ENGLISH_SCHEMA = _language_schema(
    target_field="term",
    pronunciation_field="ipa",
    classification_field="parts_of_speech",
    classification_schema={"type": "array", "items": {"type": "string"}},
    definition_field="definition_en",
    example_field="example_en",
)

SPANISH_SCHEMA = _language_schema(
    target_field="phrase_es",
    pronunciation_field="ipa",
    classification_field="register",
    classification_schema={"type": "string", "enum": list(SPANISH_REGISTERS)},
    definition_field="definition_es",
    example_field="example_es",
)

JAPANESE_SCHEMA = _language_schema(
    target_field="phrase_ja",
    pronunciation_field="ipa",
    classification_field="register",
    classification_schema={"type": "string", "enum": list(JAPANESE_REGISTERS)},
    definition_field="definition_pt_br",
    example_field="example_romaji",
)
JAPANESE_SCHEMA["properties"]["romaji"] = {"type": "string"}
JAPANESE_SCHEMA["required"].append("romaji")


@dataclass(frozen=True)
class Profile:
    profile_id: str
    note_type: str
    fields: tuple[str, ...]
    templates: Mapping[str, Mapping[str, str]]
    css: str
    prompt_filename: str
    tags: tuple[str, ...]
    output_schema: Mapping[str, Any]
    target_field: str
    pronunciation_field: str
    classification_field: str
    definition_field: str
    example_field: str
    audio_locale: str
    audio_instruction: str
    classification_multiple: bool = False
    allowed_classifications: tuple[str, ...] = ()
    romanization_field: str | None = None
    identity_alias_prefix: str | None = None
    reads_legacy_index: bool = False

    @property
    def card_templates(self) -> tuple[dict[str, str], ...]:
        return tuple(
            {"Name": name, "Front": html["Front"], "Back": html["Back"]}
            for name, html in self.templates.items()
        )


ENGLISH_VOCABULARY = Profile(
    profile_id="english_vocabulary",
    note_type="Anki Automation V2 - English",
    fields=CARD_FIELDS,
    templates=CARD_TEMPLATES,
    css=CARD_CSS,
    prompt_filename="prompt_template.txt",
    tags=("anki-automation-v2", "english"),
    output_schema=ENGLISH_SCHEMA,
    target_field="term",
    pronunciation_field="ipa",
    classification_field="parts_of_speech",
    definition_field="definition_en",
    example_field="example_en",
    audio_locale="en-US",
    audio_instruction=(
        "Use clear, natural contemporary American English at a comfortable study pace."
    ),
    classification_multiple=True,
    identity_alias_prefix="to ",
    reads_legacy_index=True,
)

SPANISH_TRAVEL = Profile(
    profile_id="spanish_travel",
    note_type="Anki Automation V2 - Spanish",
    fields=CARD_FIELDS,
    templates=CARD_TEMPLATES,
    css=CARD_CSS,
    prompt_filename="spanish_prompt_template.txt",
    tags=("anki-automation-v2", "spanish", "latin-america"),
    output_schema=SPANISH_SCHEMA,
    target_field="phrase_es",
    pronunciation_field="ipa",
    classification_field="register",
    definition_field="definition_es",
    example_field="example_es",
    audio_locale="es-US",
    audio_instruction=(
        "Use neutral Latin American Spanish as spoken across the Americas, without a "
        "country-specific accent, at a comfortable study pace."
    ),
    allowed_classifications=SPANISH_REGISTERS,
)

JAPANESE_TRAVEL = Profile(
    profile_id="japanese_travel",
    note_type="Anki Automation V2 - Japanese",
    fields=CARD_FIELDS,
    templates=CARD_TEMPLATES,
    css=CARD_CSS,
    prompt_filename="japanese_prompt_template.txt",
    tags=("anki-automation-v2", "japanese", "travel"),
    output_schema=JAPANESE_SCHEMA,
    target_field="phrase_ja",
    pronunciation_field="ipa",
    classification_field="register",
    definition_field="definition_pt_br",
    example_field="example_romaji",
    audio_locale="ja-JP",
    audio_instruction=(
        "Use clear, natural contemporary Japanese as spoken in Japan at a comfortable "
        "study pace."
    ),
    allowed_classifications=JAPANESE_REGISTERS,
    romanization_field="romaji",
)

LANGUAGE_PROFILES = (ENGLISH_VOCABULARY, SPANISH_TRAVEL, JAPANESE_TRAVEL)
_PROFILES_BY_ID = {profile.profile_id: profile for profile in LANGUAGE_PROFILES}


def profile_ids() -> tuple[str, ...]:
    return tuple(_PROFILES_BY_ID)


def is_registered_profile(profile: Profile) -> bool:
    return _PROFILES_BY_ID.get(profile.profile_id) is profile


def get_profile(profile_id: str) -> Profile:
    try:
        return _PROFILES_BY_ID[profile_id]
    except KeyError as exc:
        raise ValueError(f"Perfil desconhecido: {profile_id}") from exc


def _require_non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo inválido ou vazio: {field}")


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"Campos inválidos em {label}")


def _validate_senses(content: dict[str, Any], fields: set[str]) -> None:
    senses = content["senses"]
    if not isinstance(senses, list) or not senses:
        raise ValueError("senses deve conter ao menos um sentido")
    for sense in senses:
        if not isinstance(sense, dict):
            raise ValueError("Cada sentido deve ser um objeto")
        _require_exact_keys(sense, fields, "sense")
        for field in fields:
            _require_non_empty_string(sense[field], field)


def _require_latin_text(value: str, field: str) -> None:
    # Portuguese ordinal indicators are alphabetic but lack LATIN in their Unicode names.
    letters = [character for character in value if character.isalpha() and character not in "ªº"]
    if (
        not letters
        or any("LATIN" not in unicodedata.name(character, "") for character in letters)
        or any(
            "\u3000" <= character <= "\u303f" or "\uff00" <= character <= "\uffef"
            for character in value
        )
    ):
        raise ValueError(f"{field} deve usar somente alfabeto latino, sem escrita japonesa")


def validate_profile_content(profile: Profile, content: Any) -> dict[str, Any]:
    if not is_registered_profile(profile):
        raise ValueError(f"Perfil desconhecido: {profile.profile_id}")
    if not isinstance(content, dict):
        raise ValueError("A Anthropic não devolveu o objeto estruturado esperado")

    required = set(profile.output_schema["required"])
    _require_exact_keys(content, required, profile.profile_id)
    for field in (
        profile.target_field,
        profile.pronunciation_field,
        "visual_prompt_en",
    ):
        _require_non_empty_string(content[field], field)
    if profile.romanization_field:
        romaji = content[profile.romanization_field]
        _require_non_empty_string(romaji, profile.romanization_field)
        _require_latin_text(romaji, profile.romanization_field)
        if re.search(
            r"[\u3000-\u30ff\u3400-\u9fff\uff00-\uffef]",
            content[profile.pronunciation_field],
        ):
            raise ValueError("ipa deve conter a transcrição fonética, sem escrita japonesa")

    # Pontuação, diacríticos e modificadores (ː, ˈ, ʲ) sozinhos não são pronúncia.
    if not any(
        unicodedata.category(character) in {"Ll", "Lu", "Lt"}
        for character in content[profile.pronunciation_field]
    ):
        raise ValueError("ipa deve conter letras fonéticas, não apenas pontuação ou modificadores")

    classification = content[profile.classification_field]
    if profile.classification_multiple:
        if not isinstance(classification, list) or not classification:
            raise ValueError(
                f"{profile.classification_field} deve conter ao menos uma classificação"
            )
        for value in classification:
            _require_non_empty_string(value, profile.classification_field)
    else:
        _require_non_empty_string(classification, profile.classification_field)
        if (
            profile.allowed_classifications
            and classification not in profile.allowed_classifications
        ):
            allowed = ", ".join(profile.allowed_classifications)
            raise ValueError(f"{profile.classification_field} deve ser {allowed}")

    _validate_senses(
        content,
        {profile.definition_field, "meaning_pt_br", profile.example_field},
    )
    if profile.romanization_field:
        for sense in content["senses"]:
            for field in (profile.definition_field, "meaning_pt_br", profile.example_field):
                _require_latin_text(sense[field], field)
    return content
