"""The two concrete V2 profiles and their final Anki contracts."""

from __future__ import annotations

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


ENGLISH_SCHEMA = {
    "type": "object",
    "properties": {
        "term": {"type": "string"},
        "ipa": {"type": "string"},
        "parts_of_speech": {"type": "array", "items": {"type": "string"}},
        "senses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "definition_en": {"type": "string"},
                    "meaning_pt_br": {"type": "string"},
                    "example_en": {"type": "string"},
                },
                "required": ["definition_en", "meaning_pt_br", "example_en"],
                "additionalProperties": False,
            },
        },
        "visual_prompt_en": {"type": "string"},
    },
    "required": ["term", "ipa", "parts_of_speech", "senses", "visual_prompt_en"],
    "additionalProperties": False,
}

SPANISH_SCHEMA = {
    "type": "object",
    "properties": {
        "phrase_es": {"type": "string"},
        "ipa": {"type": "string"},
        "register": {"type": "string", "enum": list(SPANISH_REGISTERS)},
        "senses": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "definition_es": {"type": "string"},
                    "meaning_pt_br": {"type": "string"},
                    "example_es": {"type": "string"},
                },
                "required": ["definition_es", "meaning_pt_br", "example_es"],
                "additionalProperties": False,
            },
        },
        "visual_prompt_en": {"type": "string"},
    },
    "required": ["phrase_es", "ipa", "register", "senses", "visual_prompt_en"],
    "additionalProperties": False,
}


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
)


def get_profile(profile_id: str) -> Profile:
    if profile_id == ENGLISH_VOCABULARY.profile_id:
        return ENGLISH_VOCABULARY
    if profile_id == SPANISH_TRAVEL.profile_id:
        return SPANISH_TRAVEL
    raise ValueError(f"Perfil desconhecido: {profile_id}")


def _require_non_empty_string(value: Any, field: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"Campo inv\u00e1lido ou vazio: {field}")


def _require_exact_keys(value: Mapping[str, Any], expected: set[str], label: str) -> None:
    if set(value) != expected:
        raise ValueError(f"Campos inv\u00e1lidos em {label}")


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


def validate_profile_content(profile: Profile, content: Any) -> dict[str, Any]:
    if not isinstance(content, dict):
        raise ValueError("A Anthropic n\u00e3o devolveu o objeto estruturado esperado")

    if profile is ENGLISH_VOCABULARY:
        required = {"term", "ipa", "parts_of_speech", "senses", "visual_prompt_en"}
        _require_exact_keys(content, required, profile.profile_id)
        for field in ("term", "ipa", "visual_prompt_en"):
            _require_non_empty_string(content[field], field)
        parts = content["parts_of_speech"]
        if not isinstance(parts, list) or not parts:
            raise ValueError("parts_of_speech deve conter ao menos uma classe")
        for part in parts:
            _require_non_empty_string(part, "parts_of_speech")
        _validate_senses(content, {"definition_en", "meaning_pt_br", "example_en"})
        return content

    if profile is SPANISH_TRAVEL:
        required = {"phrase_es", "ipa", "register", "senses", "visual_prompt_en"}
        _require_exact_keys(content, required, profile.profile_id)
        for field in ("phrase_es", "ipa", "register", "visual_prompt_en"):
            _require_non_empty_string(content[field], field)
        if content["register"] not in SPANISH_REGISTERS:
            raise ValueError("register deve ser neutral, informal ou formal")
        _validate_senses(content, {"definition_es", "meaning_pt_br", "example_es"})
        return content

    raise ValueError(f"Perfil desconhecido: {profile.profile_id}")
