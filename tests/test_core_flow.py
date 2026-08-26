import copy
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

import main as main_module
from main import (
    ProcessError,
    build_parser,
    canonicalize_input,
    item_id_for,
    process_item,
    process_request,
    read_items_file,
)
from modules.anki_connector import AnkiConnectError, AnkiConnector
from modules.card_formatter import build_note_fields
from modules.llm_provider import ClaudeProvider, ProviderError
from modules.profiles import (
    ENGLISH_VOCABULARY,
    SPANISH_TRAVEL,
    get_profile,
    validate_profile_content,
)


ROOT = Path(__file__).resolve().parents[1]


def english_content(**overrides):
    value = {
        "term": "polish",
        "ipa": "/\u02c8p\u0252l\u026a\u0283/",
        "parts_of_speech": ["verb", "noun"],
        "senses": [
            {
                "definition_en": "To make a surface smooth and shiny.",
                "meaning_pt_br": "Polir uma superf\u00edcie.",
                "example_en": "She polished the table carefully.",
                "example_pt_br": "Ela poliu a mesa com cuidado.",
            }
        ],
        "visual_prompt_en": "Hands making a plain wooden surface shine, without text.",
    }
    value.update(overrides)
    return value


def spanish_content(**overrides):
    value = {
        "phrase_es": "Quisiera pedir la cuenta, por favor.",
        "translation_pt_br": "Gostaria de pedir a conta, por favor.",
        "usage_context_pt_br": "Forma neutra e cort\u00eas adequada nas Am\u00e9ricas.",
        "register": "neutral",
        "example_es": "Disculpe, quisiera pedir la cuenta, por favor.",
        "example_pt_br": "Com licen\u00e7a, gostaria de pedir a conta, por favor.",
    }
    value.update(overrides)
    return value


class FakeProvider:
    def __init__(self, content) -> None:
        self.content = content
        self.calls = []

    def generate(self, profile, item):
        self.calls.append((profile.profile_id, item))
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


class FakeAnki:
    def __init__(self, existing=None, note_id=1234) -> None:
        self.existing = list(existing or [])
        self.note_id = note_id
        self.calls = []

    def find_exact_items(self, item_id):
        self.calls.append(("find", item_id))
        return self.existing

    def ensure_ready(self, profile, deck_name):
        self.calls.append(("ensure_ready", profile.profile_id, deck_name))

    def prepare_qa_image(self, item_id, image_path):
        self.calls.append(("prepare_media", item_id, str(image_path)))
        return f"aa2_{item_id}_image.png", "encoded-fixture"

    def store_qa_image(self, filename, encoded_data):
        self.calls.append(("store_media", filename, encoded_data))
        return filename

    def add_note(self, profile, deck_name, fields):
        self.calls.append(("addNote", profile.profile_id, deck_name, fields))
        return self.note_id


class CoreIdentityTests(unittest.TestCase):
    def test_canonicalization_and_item_id_are_deterministic(self):
        composed = "  CAF\u00c9\t au   lait "
        decomposed = "cafe\u0301 au lait"
        self.assertEqual("caf\u00e9 au lait", canonicalize_input(composed))
        self.assertEqual(canonicalize_input(composed), canonicalize_input(decomposed))
        expected = hashlib.sha256(b"english_vocabulary\0caf\xc3\xa9 au lait").hexdigest()
        self.assertEqual(expected, item_id_for("english_vocabulary", composed))
        self.assertEqual(
            item_id_for("english_vocabulary", "Polish"),
            item_id_for("english_vocabulary", "polish"),
        )
        self.assertNotEqual(
            item_id_for("english_vocabulary", "polish"),
            item_id_for("spanish_travel", "polish"),
        )

    def test_invalid_unicode_is_rejected_as_a_request_error(self):
        with self.assertRaisesRegex(ValueError, "Unicode"):
            item_id_for("spanish_travel", "\ud800")

    def test_only_the_two_fixed_profiles_exist(self):
        self.assertIs(ENGLISH_VOCABULARY, get_profile("english_vocabulary"))
        self.assertIs(SPANISH_TRAVEL, get_profile("spanish_travel"))
        with self.assertRaises(ValueError):
            get_profile("japanese")


class SchemaTests(unittest.TestCase):
    def test_english_schema_accepts_multiple_complete_senses(self):
        content = english_content()
        content["senses"].append(
            {
                "definition_en": "To improve or refine something.",
                "meaning_pt_br": "Aprimorar algo.",
                "example_en": "He polished the final draft.",
                "example_pt_br": "Ele aprimorou a vers\u00e3o final.",
            }
        )
        self.assertEqual(content, validate_profile_content(ENGLISH_VOCABULARY, content))

    def test_schemas_reject_extra_missing_empty_and_refusal(self):
        cases = [
            (ENGLISH_VOCABULARY, {**english_content(), "extra": "no"}),
            (ENGLISH_VOCABULARY, english_content(senses=[])),
            (ENGLISH_VOCABULARY, english_content(term="   ")),
            (SPANISH_TRAVEL, spanish_content(register="regional")),
            (SPANISH_TRAVEL, spanish_content(example_es="")),
            (SPANISH_TRAVEL, {**spanish_content(), "extra": "no"}),
            (SPANISH_TRAVEL, None),
        ]
        for profile, content in cases:
            with self.subTest(profile=profile.profile_id, content=content):
                with self.assertRaises(ValueError):
                    validate_profile_content(profile, content)


class ProcessItemTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.image = self.base / "qa-image.png"
        self.image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")

    def write_legacy(self, content):
        path = self.base / "processadas.json"
        path.write_text(content, encoding="utf-8")
        return path

    def call(self, item, profile_id, provider, anki, legacy_path=None):
        return process_item(
            item,
            profile_id,
            provider=provider,
            anki=anki,
            deck_name="Anki Automation V2 QA",
            legacy_path=legacy_path,
            qa_image_path=self.image,
        )

    def test_missing_or_invalid_legacy_stops_english_before_mutation_or_provider(self):
        for legacy_path in (self.base / "missing.json", self.write_legacy("not json")):
            provider = FakeProvider(english_content())
            anki = FakeAnki()
            with self.subTest(path=legacy_path):
                with self.assertRaises(ProcessError) as raised:
                    self.call("luculent", "english_vocabulary", provider, anki, legacy_path)
                self.assertEqual("legacy", raised.exception.stage)
                self.assertEqual([], provider.calls)
                self.assertFalse(
                    any(
                        call[0] in {"ensure_ready", "prepare_media", "store_media", "addNote"}
                        for call in anki.calls
                    )
                )

    def test_spanish_never_reads_the_legacy_index(self):
        provider = FakeProvider(spanish_content())
        anki = FakeAnki()
        result = self.call(
            "Quero pedir a conta",
            "spanish_travel",
            provider,
            anki,
            self.base / "missing.json",
        )
        self.assertEqual("created", result["kind"])
        self.assertEqual(1, len(provider.calls))

    def test_legacy_match_skips_with_unicode_case_and_spacing_variants(self):
        legacy = self.write_legacy(json.dumps({" CAF\u00c9   AU LAIT ": {}}))
        provider = FakeProvider(english_content())
        anki = FakeAnki()
        result = self.call("cafe\u0301 au\t lait", "english_vocabulary", provider, anki, legacy)
        self.assertEqual("skipped_legacy", result["reason"])
        self.assertEqual([], provider.calls)
        self.assertFalse(
            any(
                call[0] in {"ensure_ready", "prepare_media", "store_media", "addNote"}
                for call in anki.calls
            )
        )

    def test_one_exact_v2_match_skips_and_reports_existing_input(self):
        provider = FakeProvider(spanish_content())
        anki = FakeAnki(existing=["Polish"])
        result = self.call("polish", "spanish_travel", provider, anki)
        self.assertEqual("skipped_v2", result["reason"])
        self.assertEqual("Polish", result["existing_input"])
        self.assertEqual([], provider.calls)

    def test_multiple_exact_v2_matches_stop_as_conflict(self):
        provider = FakeProvider(spanish_content())
        anki = FakeAnki(existing=["x", "x"])
        with self.assertRaises(ProcessError) as raised:
            self.call("x", "spanish_travel", provider, anki)
        self.assertEqual("identity", raised.exception.stage)
        self.assertEqual([], provider.calls)

    def test_created_english_note_uses_one_add_note_and_empty_audio(self):
        legacy = self.write_legacy("{}")
        before = legacy.read_bytes()
        provider = FakeProvider(english_content())
        anki = FakeAnki()
        result = self.call("polish", "english_vocabulary", provider, anki, legacy)
        add_calls = [call for call in anki.calls if call[0] == "addNote"]
        self.assertEqual(1, len(add_calls))
        fields = add_calls[0][3]
        self.assertEqual("", fields["MainAudio"])
        self.assertEqual("", fields["ExampleAudio"])
        self.assertTrue(fields["Image"].startswith('<img src="aa2_'))
        self.assertEqual(1234, result["note_id"])
        self.assertEqual(before, legacy.read_bytes())

    def test_note_type_drift_stops_before_provider(self):
        class DriftedAnki(FakeAnki):
            def ensure_ready(self, profile, deck_name):
                self.calls.append(("ensure_ready", profile.profile_id, deck_name))
                raise AnkiConnectError("model_contract", "drift")

        provider = FakeProvider(spanish_content())
        with self.assertRaises(ProcessError) as raised:
            self.call("Quero pagar", "spanish_travel", provider, DriftedAnki())
        self.assertEqual("preflight", raised.exception.stage)
        self.assertEqual([], provider.calls)

    def test_english_media_preflight_stops_before_provider(self):
        class MediaCollisionAnki(FakeAnki):
            def prepare_qa_image(self, item_id, image_path):
                self.calls.append(("prepare_media", item_id, str(image_path)))
                raise AnkiConnectError("retrieveMediaFile", "collision")

        provider = FakeProvider(english_content())
        legacy = self.write_legacy("{}")
        with self.assertRaises(ProcessError) as raised:
            self.call("polish", "english_vocabulary", provider, MediaCollisionAnki(), legacy)
        self.assertEqual("media", raised.exception.stage)
        self.assertEqual([], provider.calls)

    def test_provider_error_stops_before_media_upload_and_later_items(self):
        provider = FakeProvider(RuntimeError("provider unavailable"))
        anki = FakeAnki()
        result = process_request(
            "english_vocabulary",
            ["first", "never"],
            provider=provider,
            anki=anki,
            deck_name="QA",
            legacy_path=self.write_legacy("{}"),
            qa_image_path=self.image,
        )
        self.assertEqual("error", result["status"])
        self.assertEqual("provider", result["error"]["stage"])
        self.assertEqual([("english_vocabulary", "first")], provider.calls)
        self.assertFalse(any(call[0] in {"store_media", "addNote"} for call in anki.calls))

    def test_rejected_media_upload_stops_before_add_note(self):
        class RejectedMediaAnki(FakeAnki):
            def store_qa_image(self, filename, encoded_data):
                self.calls.append(("store_media", filename, encoded_data))
                raise AnkiConnectError("storeMediaFile", "filename mismatch")

        provider = FakeProvider(english_content())
        anki = RejectedMediaAnki()
        with self.assertRaises(ProcessError) as raised:
            self.call(
                "polish",
                "english_vocabulary",
                provider,
                anki,
                self.write_legacy("{}"),
            )
        self.assertEqual("media", raised.exception.stage)
        self.assertFalse(any(call[0] == "addNote" for call in anki.calls))

    def test_html_from_input_and_provider_is_escaped(self):
        provider = FakeProvider(
            spanish_content(
                phrase_es="<b>Hola & adi\u00f3s</b>",
                usage_context_pt_br='Use em "caf\u00e9" <agora>.',
            )
        )
        anki = FakeAnki()
        self.call("<script>alert('x')</script>", "spanish_travel", provider, anki)
        fields = [call for call in anki.calls if call[0] == "addNote"][0][3]
        self.assertEqual("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", fields["Input"])
        self.assertEqual("&lt;b&gt;Hola &amp; adi\u00f3s&lt;/b&gt;", fields["PhraseEs"])
        self.assertNotIn("<agora>", fields["UsageContextPtBr"])

    def test_request_stops_on_first_error_and_keeps_prior_results(self):
        class FailsSecond(FakeProvider):
            def generate(self, profile, item):
                self.calls.append((profile.profile_id, item))
                if item == "bad":
                    return spanish_content(example_es="")
                return spanish_content(phrase_es=item)

        provider = FailsSecond(None)
        anki = FakeAnki()
        result = process_request(
            "spanish_travel",
            ["good", "bad", "never"],
            provider=provider,
            anki=anki,
            deck_name="QA",
            legacy_path=self.base / "missing.json",
            qa_image_path=self.image,
        )
        self.assertEqual({"status", "estimate", "created", "skipped", "error"}, set(result))
        self.assertEqual("error", result["status"])
        self.assertEqual(1, len(result["created"]))
        self.assertEqual("bad", result["error"]["item"])
        self.assertEqual("validation", result["error"]["stage"])
        self.assertFalse(result["error"]["outcome_uncertain"])
        self.assertEqual(2, len(provider.calls))

    def test_add_note_error_reports_identity_and_uploaded_media(self):
        class FailedAddAnki(FakeAnki):
            def add_note(self, profile, deck_name, fields):
                raise AnkiConnectError("addNote", "timeout", outcome_uncertain=True)

        legacy = self.write_legacy("{}")
        result = process_request(
            "english_vocabulary",
            ["polish"],
            provider=FakeProvider(english_content()),
            anki=FailedAddAnki(),
            deck_name="QA",
            legacy_path=legacy,
            qa_image_path=self.image,
        )
        self.assertEqual("error", result["status"])
        self.assertTrue(result["error"]["outcome_uncertain"])
        self.assertIn("ItemId=", result["error"]["message"])
        self.assertIn("m\u00eddia enviada=aa2_", result["error"]["message"])


class ProfileAndFormattingTests(unittest.TestCase):
    def test_field_order_and_template_names_are_final(self):
        self.assertEqual(
            ("ItemId", "Input", "Term", "IPA", "PartsOfSpeech", "SensesHtml", "Image", "MainAudio", "ExampleAudio"),
            ENGLISH_VOCABULARY.fields,
        )
        self.assertEqual(("Image to Term", "Term to Meaning"), tuple(ENGLISH_VOCABULARY.templates))
        self.assertEqual(
            ("ItemId", "Input", "PhraseEs", "TranslationPtBr", "UsageContextPtBr", "Register", "ExampleEs", "ExamplePtBr", "MainAudio", "ExampleAudio"),
            SPANISH_TRAVEL.fields,
        )
        self.assertEqual(("Portuguese to Spanish", "Spanish to Portuguese"), tuple(SPANISH_TRAVEL.templates))

    def test_english_senses_are_rendered_as_escaped_html(self):
        content = english_content()
        content["senses"][0]["definition_en"] = "A <clear> & useful definition."
        fields = build_note_fields(
            ENGLISH_VOCABULARY,
            "<input>",
            "a" * 64,
            content,
            "aa2_" + "a" * 64 + "_image.png",
        )
        self.assertIn("A &lt;clear&gt; &amp; useful definition.", fields["SensesHtml"])
        self.assertNotIn("<clear>", fields["SensesHtml"])


class FakeResponse:
    def __init__(self, payload=None, json_error=None):
        self.payload = payload
        self.json_error = json_error

    def raise_for_status(self):
        return None

    def json(self):
        if self.json_error:
            raise self.json_error
        return self.payload


class QueueSession:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def post(self, url, json, timeout):
        self.calls.append(json)
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ok(result):
    return FakeResponse({"result": result, "error": None})


class AnkiConnectorTests(unittest.TestCase):
    def test_find_notes_postfilters_exact_item_id(self):
        item_id = "a" * 64
        session = QueueSession(
            [
                ok([1, 2]),
                ok(
                    [
                        {"noteId": 1, "fields": {"ItemId": {"value": item_id}, "Input": {"value": "One"}}},
                        {"noteId": 2, "fields": {"ItemId": {"value": "other"}, "Input": {"value": "Two"}}},
                    ]
                ),
            ]
        )
        connector = AnkiConnector(session=session)
        self.assertEqual(["One"], connector.find_exact_items(item_id))
        self.assertEqual(f"ItemId:{item_id}", session.calls[0]["params"]["query"])

    def test_absent_model_is_created_once_with_exact_contract(self):
        session = QueueSession([ok(["QA"]), ok([]), ok(42)])
        connector = AnkiConnector(session=session)
        connector.ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual(["deckNames", "modelNames", "createModel"], [c["action"] for c in session.calls])
        create = session.calls[-1]["params"]
        self.assertEqual(list(ENGLISH_VOCABULARY.fields), create["inOrderFields"])
        self.assertEqual(list(ENGLISH_VOCABULARY.card_templates), create["cardTemplates"])

    def test_create_model_transport_or_invalid_response_is_uncertain_and_not_retried(self):
        cases = [
            requests.Timeout("slow"),
            FakeResponse({"result": 42, "error": None, "extra": True}),
        ]
        for response in cases:
            with self.subTest(response=response):
                session = QueueSession([ok(["QA"]), ok([]), response])
                connector = AnkiConnector(session=session)
                with self.assertRaises(AnkiConnectError) as raised:
                    connector.ensure_ready(ENGLISH_VOCABULARY, "QA")
                self.assertEqual("createModel", raised.exception.action)
                self.assertTrue(raised.exception.outcome_uncertain)
                self.assertEqual(1, [call["action"] for call in session.calls].count("createModel"))

    def test_existing_model_drift_stops_without_repair(self):
        templates = copy.deepcopy(ENGLISH_VOCABULARY.templates)
        templates["Image to Term"]["Front"] += "<!-- drift -->"
        session = QueueSession(
            [ok(["QA"]), ok([ENGLISH_VOCABULARY.note_type]), ok(list(ENGLISH_VOCABULARY.fields)), ok(templates)]
        )
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError) as raised:
            connector.ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual("model_contract", raised.exception.action)
        self.assertNotIn("createModel", [c["action"] for c in session.calls])

    def test_matching_existing_model_is_accepted_without_mutation(self):
        session = QueueSession(
            [
                ok(["QA"]),
                ok([ENGLISH_VOCABULARY.note_type]),
                ok(list(ENGLISH_VOCABULARY.fields)),
                ok(copy.deepcopy(ENGLISH_VOCABULARY.templates)),
            ]
        )
        AnkiConnector(session=session).ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual(
            ["deckNames", "modelNames", "modelFieldNames", "modelTemplates"],
            [call["action"] for call in session.calls],
        )

    def test_missing_deck_stops_without_creating_it(self):
        session = QueueSession([ok(["Other Deck"])])
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError):
            connector.ensure_ready(SPANISH_TRAVEL, "QA")
        self.assertEqual(["deckNames"], [c["action"] for c in session.calls])

    def test_add_note_explicit_error_is_definitive_and_not_retried(self):
        response = FakeResponse({"result": None, "error": "cannot add note"})
        session = QueueSession([response])
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError) as raised:
            connector.add_note(SPANISH_TRAVEL, "QA", {name: "" for name in SPANISH_TRAVEL.fields})
        self.assertEqual("addNote", raised.exception.action)
        self.assertFalse(raised.exception.outcome_uncertain)
        self.assertEqual(1, len(session.calls))

    def test_successful_add_note_uses_the_exact_profile_contract(self):
        for profile in (ENGLISH_VOCABULARY, SPANISH_TRAVEL):
            with self.subTest(profile=profile.profile_id):
                fields = {name: f"value-{name}" for name in profile.fields}
                session = QueueSession([ok(1234)])
                note_id = AnkiConnector(session=session).add_note(profile, "QA", fields)
                self.assertEqual(1234, note_id)
                note = session.calls[0]["params"]["note"]
                self.assertEqual(
                    {
                        "deckName": "QA",
                        "modelName": profile.note_type,
                        "fields": fields,
                        "tags": list(profile.tags),
                        "options": {"allowDuplicate": False},
                    },
                    note,
                )

    def test_add_note_timeout_or_malformed_response_is_uncertain_and_not_retried(self):
        cases = [
            requests.Timeout("slow"),
            FakeResponse(json_error=ValueError("not json")),
            FakeResponse({"result": 1, "error": None, "extra": True}),
        ]
        for response in cases:
            with self.subTest(response=response):
                session = QueueSession([response])
                connector = AnkiConnector(session=session)
                with self.assertRaises(AnkiConnectError) as raised:
                    connector.add_note(SPANISH_TRAVEL, "QA", {name: "" for name in SPANISH_TRAVEL.fields})
                self.assertTrue(raised.exception.outcome_uncertain)
                self.assertEqual(1, len(session.calls))

    def test_add_note_rejects_boolean_and_non_positive_ids_as_uncertain(self):
        for note_id in (True, False, 0, -1):
            with self.subTest(note_id=note_id):
                session = QueueSession([ok(note_id)])
                connector = AnkiConnector(session=session)
                with self.assertRaises(AnkiConnectError) as raised:
                    connector.add_note(
                        SPANISH_TRAVEL,
                        "QA",
                        {name: "" for name in SPANISH_TRAVEL.fields},
                    )
                self.assertTrue(raised.exception.outcome_uncertain)

    def test_connector_has_no_legacy_mutation_methods(self):
        connector = AnkiConnector(session=QueueSession([]))
        for method in ("update_note", "delete_note", "change_deck", "create_deck"):
            self.assertFalse(hasattr(connector, method))

    def test_qa_media_uses_aa2_name_and_refuses_collision(self):
        item_id = "b" * 64
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "fixture.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nvalid fixture")
            filename = f"aa2_{item_id}_image.png"
            session = QueueSession([ok(False), ok(filename)])
            connector = AnkiConnector(session=session)
            prepared = connector.prepare_qa_image(item_id, image)
            self.assertEqual(filename, connector.store_qa_image(*prepared))
            self.assertEqual(["retrieveMediaFile", "storeMediaFile"], [c["action"] for c in session.calls])
            self.assertEqual(filename, session.calls[-1]["params"]["filename"])

            for existing in ("already-present", ""):
                with self.subTest(existing=existing):
                    collision = QueueSession([ok(existing)])
                    with self.assertRaises(AnkiConnectError):
                        AnkiConnector(session=collision).prepare_qa_image(item_id, image)
                    self.assertEqual(["retrieveMediaFile"], [c["action"] for c in collision.calls])

            mismatch = QueueSession([ok("other.png")])
            with self.assertRaises(AnkiConnectError) as raised:
                AnkiConnector(session=mismatch).store_qa_image(filename, "encoded-fixture")
            self.assertEqual("storeMediaFile", raised.exception.action)
            self.assertTrue(raised.exception.outcome_uncertain)

    def test_store_media_transport_or_invalid_response_is_uncertain_and_not_retried(self):
        cases = [
            requests.Timeout("slow"),
            FakeResponse({"result": "fixture.png", "error": None, "extra": True}),
        ]
        for response in cases:
            with self.subTest(response=response):
                session = QueueSession([response])
                with self.assertRaises(AnkiConnectError) as raised:
                    AnkiConnector(session=session).store_qa_image("fixture.png", "encoded-fixture")
                self.assertEqual("storeMediaFile", raised.exception.action)
                self.assertTrue(raised.exception.outcome_uncertain)
                self.assertEqual(1, len(session.calls))

    def test_invalid_qa_media_stops_before_anki(self):
        with tempfile.TemporaryDirectory() as tmp:
            image = Path(tmp) / "fixture.png"
            image.write_bytes(b"not an image")
            session = QueueSession([])
            with self.assertRaises(AnkiConnectError):
                AnkiConnector(session=session).prepare_qa_image("c" * 64, image)
            self.assertEqual([], session.calls)


class MessagesFake:
    def __init__(self, message):
        self.message = message
        self.calls = []

    def create(self, **kwargs):
        self.calls.append(kwargs)
        return self.message


class AnthropicStructuredOutputTests(unittest.TestCase):
    def provider(self, message):
        temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(temp_dir.cleanup)
        prompt = Path(temp_dir.name) / "prompt.txt"
        prompt.write_text("Generate the requested card.", encoding="utf-8")
        client = SimpleNamespace(messages=MessagesFake(message))
        return ClaudeProvider("secret", prompt, client=client), client

    def test_provider_sends_output_config_schema_and_validates_locally(self):
        message = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(english_content()))],
        )
        provider, client = self.provider(message)
        self.assertEqual(english_content(), provider.generate(ENGLISH_VOCABULARY, "polish"))
        call = client.messages.calls[0]
        self.assertEqual("json_schema", call["output_config"]["format"]["type"])
        self.assertIs(ENGLISH_VOCABULARY.output_schema, call["output_config"]["format"]["schema"])
        self.assertNotIn("output_format", call)

    def test_provider_rejects_refusal_empty_and_invalid_local_shape(self):
        messages = [
            SimpleNamespace(stop_reason="refusal", content=[]),
            SimpleNamespace(stop_reason="end_turn", content=[]),
            SimpleNamespace(
                stop_reason="end_turn",
                content=[
                    SimpleNamespace(
                        type="text",
                        text=json.dumps(spanish_content(example_es="")),
                    )
                ],
            ),
        ]
        for message in messages:
            with self.subTest(message=message):
                provider, _ = self.provider(message)
                with self.assertRaises(ProviderError):
                    provider.generate(SPANISH_TRAVEL, "Quero pagar")

    def test_production_client_disables_retries_and_has_a_finite_timeout(self):
        prompt = ROOT / "config" / "prompt_template.txt"
        client = SimpleNamespace(
            messages=MessagesFake(SimpleNamespace(stop_reason="end_turn", content=[]))
        )
        constructor = Mock(return_value=client)
        fake_module = SimpleNamespace(Anthropic=constructor)
        with patch.dict(sys.modules, {"anthropic": fake_module}):
            provider = ClaudeProvider("secret", prompt)
            self.assertIs(client, provider._client())
        constructor.assert_called_once_with(
            api_key="secret",
            max_retries=0,
            timeout=60.0,
        )

    def test_provider_redacts_the_api_key_from_errors(self):
        class FailingMessages:
            def create(self, **kwargs):
                raise RuntimeError("request failed for secret-key")

        provider = ClaudeProvider(
            "secret-key",
            ROOT / "config" / "prompt_template.txt",
            client=SimpleNamespace(messages=FailingMessages()),
        )
        with self.assertRaises(ProviderError) as raised:
            provider.generate(SPANISH_TRAVEL, "Quero pagar")
        self.assertNotIn("secret-key", str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))

    def test_spanish_prompt_is_real_utf8_not_literal_unicode_escapes(self):
        prompt = (ROOT / "config" / "spanish_prompt_template.txt").read_text(encoding="utf-8")
        self.assertIn("intenção", prompt)
        self.assertIn("Américas", prompt)
        self.assertNotIn("\\u", prompt)


class CliContractTests(unittest.TestCase):
    def test_parser_has_profile_and_exactly_one_item_source_but_no_reset(self):
        help_text = build_parser().format_help()
        self.assertIn("--profile", help_text)
        self.assertIn("--item", help_text)
        self.assertIn("--file", help_text)
        self.assertNotIn("reset", help_text.lower())

    def test_input_file_is_read_only(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "items.txt"
            original = b"one\n\ntwo\n"
            path.write_bytes(original)
            self.assertEqual(["one", "two"], read_items_file(path))
            self.assertEqual(original, path.read_bytes())

    def test_direct_cli_and_wrapper_emit_only_one_json_object_on_stdout(self):
        for command in ([sys.executable, "main.py", "--json"], ["./run.sh", "--json"]):
            with self.subTest(command=command):
                completed = subprocess.run(
                    command,
                    cwd=ROOT,
                    input="not-json",
                    text=True,
                    capture_output=True,
                    check=False,
                )
                self.assertNotEqual(0, completed.returncode)
                payload = json.loads(completed.stdout)
                self.assertEqual("error", payload["status"])
                self.assertEqual(1, len(completed.stdout.strip().splitlines()))

    def test_valid_json_uses_the_same_flow_for_both_profiles(self):
        with tempfile.TemporaryDirectory() as tmp:
            base = Path(tmp)
            settings_path = base / "config" / "settings.json"
            settings_path.parent.mkdir()
            legacy = base / "processadas.json"
            legacy.write_text("{}", encoding="utf-8")
            image = base / "qa-image.png"
            image.write_bytes(b"\x89PNG\r\n\x1a\nfixture")
            settings_path.write_text(
                json.dumps(
                    {
                        "anki_url": "http://localhost:8765",
                        "legacy_index_path": str(legacy),
                        "qa_image_path": str(image),
                        "profiles": {
                            "english_vocabulary": {
                                "deck_name": "QA",
                                "anthropic_model": "claude-sonnet-4-6",
                            },
                            "spanish_travel": {
                                "deck_name": "QA",
                                "anthropic_model": "claude-sonnet-4-6",
                            },
                        },
                    }
                ),
                encoding="utf-8",
            )

            cases = (
                ("english_vocabulary", "polish", english_content()),
                ("spanish_travel", "Quero pagar", spanish_content()),
            )
            for profile_id, item, content in cases:
                with self.subTest(profile=profile_id):
                    stdout = io.StringIO()
                    request = json.dumps({"profile": profile_id, "items": [item]})
                    with (
                        patch.object(main_module, "ClaudeProvider", return_value=FakeProvider(content)),
                        patch.object(main_module, "AnkiConnector", return_value=FakeAnki()),
                        patch.object(sys, "stdin", io.StringIO(request)),
                        redirect_stdout(stdout),
                    ):
                        exit_code = main_module.main(["--json", "--settings", str(settings_path)])
                    self.assertEqual(0, exit_code)
                    payload = json.loads(stdout.getvalue())
                    self.assertEqual("ok", payload["status"])
                    self.assertEqual(1, len(payload["created"]))
                    self.assertEqual(1, len(stdout.getvalue().strip().splitlines()))

    def test_json_error_remains_parseable_for_a_lone_surrogate(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings_path = Path(tmp) / "settings.json"
            settings_path.write_text(
                json.dumps(
                    {
                        "profiles": {
                            "spanish_travel": {
                                "deck_name": "QA",
                                "anthropic_model": "claude-sonnet-4-6",
                            }
                        }
                    }
                ),
                encoding="utf-8",
            )
            request = json.dumps(
                {"profile": "spanish_travel", "items": ["\ud800"]},
                ensure_ascii=True,
            )
            stdout = io.StringIO()
            with (
                patch.object(main_module, "ClaudeProvider", return_value=FakeProvider(spanish_content())),
                patch.object(main_module, "AnkiConnector", return_value=FakeAnki()),
                patch.object(sys, "stdin", io.StringIO(request)),
                redirect_stdout(stdout),
            ):
                exit_code = main_module.main(["--json", "--settings", str(settings_path)])
            self.assertEqual(1, exit_code)
            payload = json.loads(stdout.getvalue())
            self.assertEqual("request", payload["error"]["stage"])
            self.assertIn("\\ud800", stdout.getvalue())

    def test_wrapper_contains_no_install_checks_or_human_output(self):
        wrapper = (ROOT / "run.sh").read_text(encoding="utf-8")
        for forbidden in ("pip install", "caffeinate", "echo ", "curl ", "ANTHROPIC_API_KEY"):
            self.assertNotIn(forbidden, wrapper)


if __name__ == "__main__":
    unittest.main()
