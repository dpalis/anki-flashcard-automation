"""The two concrete V2 profiles and their final Anki contracts."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


ENGLISH_FIELDS = (
    "ItemId",
    "Input",
    "Term",
    "IPA",
    "PartsOfSpeech",
    "SensesHtml",
    "Image",
    "MainAudio",
    "ExampleAudio",
)

SPANISH_FIELDS = (
    "ItemId",
    "Input",
    "PhraseEs",
    "TranslationPtBr",
    "UsageContextPtBr",
    "Register",
    "ExampleEs",
    "ExamplePtBr",
    "MainAudio",
    "ExampleAudio",
)

SPANISH_REGISTERS = ("neutral", "informal", "formal")


ENGLISH_TEMPLATES = {
    "Image to Term": {
        "Front": "{{Image}}",
        "Back": (
            "{{FrontSide}}\n<hr id=answer>\n"
            '<div class="term">{{Term}}</div>\n'
            '<div class="ipa">{{IPA}}</div>\n'
            '<div class="parts-of-speech">{{PartsOfSpeech}}</div>\n'
            '<div class="senses">{{SensesHtml}}</div>\n'
            "{{MainAudio}}{{ExampleAudio}}"
        ),
    },
    "Term to Meaning": {
        "Front": '<div class="term">{{Term}}</div>\n{{MainAudio}}',
        "Back": (
            "{{FrontSide}}\n<hr id=answer>\n"
            "{{Image}}\n"
            '<div class="ipa">{{IPA}}</div>\n'
            '<div class="parts-of-speech">{{PartsOfSpeech}}</div>\n'
            '<div class="senses">{{SensesHtml}}</div>\n'
            "{{ExampleAudio}}"
        ),
    },
}

SPANISH_TEMPLATES = {
    "Portuguese to Spanish": {
        "Front": '<div class="translation">{{TranslationPtBr}}</div>',
        "Back": (
            "{{FrontSide}}\n<hr id=answer>\n"
            '<div class="phrase">{{PhraseEs}}</div>\n'
            "{{MainAudio}}\n"
            '<div class="context">{{UsageContextPtBr}}</div>\n'
            '<div class="register">{{Register}}</div>\n'
            '<div class="example-es">{{ExampleEs}}</div>\n'
            '<div class="example-pt-br">{{ExamplePtBr}}</div>\n'
            "{{ExampleAudio}}"
        ),
    },
    "Spanish to Portuguese": {
        "Front": '<div class="phrase">{{PhraseEs}}</div>\n{{MainAudio}}',
        "Back": (
            "{{FrontSide}}\n<hr id=answer>\n"
            '<div class="translation">{{TranslationPtBr}}</div>\n'
            '<div class="context">{{UsageContextPtBr}}</div>\n'
            '<div class="register">{{Register}}</div>\n'
            '<div class="example-es">{{ExampleEs}}</div>\n'
            '<div class="example-pt-br">{{ExamplePtBr}}</div>\n'
            "{{ExampleAudio}}"
        ),
    },
}


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
                    "example_pt_br": {"type": "string"},
                },
                "required": ["definition_en", "meaning_pt_br", "example_en", "example_pt_br"],
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
        "translation_pt_br": {"type": "string"},
        "usage_context_pt_br": {"type": "string"},
        "register": {"type": "string", "enum": list(SPANISH_REGISTERS)},
        "example_es": {"type": "string"},
        "example_pt_br": {"type": "string"},
    },
    "required": [
        "phrase_es",
        "translation_pt_br",
        "usage_context_pt_br",
        "register",
        "example_es",
        "example_pt_br",
    ],
    "additionalProperties": False,
}


@dataclass(frozen=True)
class Profile:
    profile_id: str
    note_type: str
    fields: tuple[str, ...]
    templates: Mapping[str, Mapping[str, str]]
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
    note_type="Anki Automation V2 - English Vocabulary",
    fields=ENGLISH_FIELDS,
    templates=ENGLISH_TEMPLATES,
    prompt_filename="prompt_template.txt",
    tags=("anki-automation-v2", "english"),
    output_schema=ENGLISH_SCHEMA,
)

SPANISH_TRAVEL = Profile(
    profile_id="spanish_travel",
    note_type="Anki Automation V2 - Spanish Travel",
    fields=SPANISH_FIELDS,
    templates=SPANISH_TEMPLATES,
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
        senses = content["senses"]
        if not isinstance(senses, list) or not senses:
            raise ValueError("senses deve conter ao menos um sentido")
        sense_fields = {"definition_en", "meaning_pt_br", "example_en", "example_pt_br"}
        for sense in senses:
            if not isinstance(sense, dict):
                raise ValueError("Cada sentido deve ser um objeto")
            _require_exact_keys(sense, sense_fields, "sense")
            for field in sense_fields:
                _require_non_empty_string(sense[field], field)
        return content

    if profile is SPANISH_TRAVEL:
        required = {
            "phrase_es",
            "translation_pt_br",
            "usage_context_pt_br",
            "register",
            "example_es",
            "example_pt_br",
        }
        _require_exact_keys(content, required, profile.profile_id)
        for field in required:
            _require_non_empty_string(content[field], field)
        if content["register"] not in SPANISH_REGISTERS:
            raise ValueError("register deve ser neutral, informal ou formal")
        return content

    raise ValueError(f"Perfil desconhecido: {profile.profile_id}")
