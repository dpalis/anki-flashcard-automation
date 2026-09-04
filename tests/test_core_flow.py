import base64
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
        "term": "Polish",
        "ipa": "/\u02c8p\u0252l\u026a\u0283/",
        "parts_of_speech": ["verb", "noun"],
        "senses": [
            {
                "definition_en": "To make a surface smooth and shiny.",
                "meaning_pt_br": "Polir uma superf\u00edcie.",
                "example_en": "She polished the table carefully.",
            }
        ],
        "visual_prompt_en": (
            "One coherent scene combining the common meanings of polish, without text."
        ),
    }
    value.update(overrides)
    return value


def spanish_content(**overrides):
    value = {
        "phrase_es": "Quisiera pedir la cuenta, por favor.",
        "ipa": "/ki\u02c8sje\u027ea pe\u02c8\u00f0i\u027e la \u02c8kwenta po\u027e fa\u02c8\u03b2o\u027e/",
        "register": "neutral",
        "senses": [
            {
                "definition_es": "Una forma cort\u00e9s y habitual de solicitar la cuenta.",
                "meaning_pt_br": "Gostaria de pedir a conta, por favor.",
                "example_es": "Disculpe, quisiera pedir la cuenta, por favor.",
            }
        ],
        "visual_prompt_en": (
            "A diner politely asking a server for the bill, without text or numbers."
        ),
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


class FakeImageProvider:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, prompt):
        self.calls.append(prompt)
        return b"\xff\xd8image\xff\xd9", "jpg"


class FakeAudioProvider:
    def __init__(self) -> None:
        self.calls = []

    def generate(self, text, locale):
        self.calls.append((text, locale))
        return b"ID3-audio", {"mp3_bytes": 9}


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

    def ensure_media_absent(self, filenames):
        self.calls.append(("media_preflight", tuple(filenames)))

    def store_media_file(self, filename, data):
        self.calls.append(("store_media", filename, data))
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
            }
        )
        self.assertEqual(content, validate_profile_content(ENGLISH_VOCABULARY, content))

    def test_schemas_reject_extra_missing_empty_and_refusal(self):
        cases = [
            (ENGLISH_VOCABULARY, {**english_content(), "extra": "no"}),
            (ENGLISH_VOCABULARY, english_content(senses=[])),
            (ENGLISH_VOCABULARY, english_content(term="   ")),
            (SPANISH_TRAVEL, spanish_content(register="regional")),
            (SPANISH_TRAVEL, spanish_content(senses=[])),
            (SPANISH_TRAVEL, spanish_content(senses=["not an object"])),
            (
                SPANISH_TRAVEL,
                spanish_content(
                    senses=[{"definition_es": "Definición.", "meaning_pt_br": "Tradução."}]
                ),
            ),
            (
                SPANISH_TRAVEL,
                spanish_content(
                    senses=[
                        {
                            "definition_es": "   ",
                            "meaning_pt_br": "Tradução.",
                            "example_es": "Un ejemplo.",
                        }
                    ]
                ),
            ),
            (SPANISH_TRAVEL, spanish_content(ipa="")),
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

    def write_legacy(self, content):
        path = self.base / "processadas.json"
        path.write_text(content, encoding="utf-8")
        return path

    def call(
        self,
        item,
        profile_id,
        provider,
        anki,
        legacy_path=None,
        image_provider=None,
        audio_provider=None,
    ):
        return process_item(
            item,
            profile_id,
            provider=provider,
            image_provider=image_provider or FakeImageProvider(),
            audio_provider=audio_provider or FakeAudioProvider(),
            anki=anki,
            deck_name="Anki Automation V2 QA",
            legacy_path=legacy_path,
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
                        call[0] in {"ensure_ready", "media_preflight", "store_media", "addNote"}
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
                call[0] in {"ensure_ready", "media_preflight", "store_media", "addNote"}
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

    def test_created_english_note_uses_one_add_note_and_main_audio(self):
        legacy = self.write_legacy("{}")
        before = legacy.read_bytes()
        provider = FakeProvider(english_content())
        anki = FakeAnki()
        result = self.call("polish", "english_vocabulary", provider, anki, legacy)
        add_calls = [call for call in anki.calls if call[0] == "addNote"]
        self.assertEqual(1, len(add_calls))
        fields = add_calls[0][3]
        self.assertTrue(fields["MainAudio"].startswith("[sound:aa2_"))
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
            def ensure_media_absent(self, filenames):
                self.calls.append(("media_preflight", tuple(filenames)))
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
            image_provider=FakeImageProvider(),
            audio_provider=FakeAudioProvider(),
            anki=anki,
            deck_name="QA",
            legacy_path=self.write_legacy("{}"),
        )
        self.assertEqual("error", result["status"])
        self.assertEqual("provider", result["error"]["stage"])
        self.assertEqual([("english_vocabulary", "first")], provider.calls)
        self.assertFalse(any(call[0] in {"store_media", "addNote"} for call in anki.calls))

    def test_rejected_media_upload_stops_before_add_note(self):
        class RejectedMediaAnki(FakeAnki):
            def store_media_file(self, filename, data):
                self.calls.append(("store_media", filename, data))
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
                senses=[
                    {
                        "definition_es": 'Se usa en "caf\u00e9" <ahora>.',
                        "meaning_pt_br": "Ol\u00e1 e adeus.",
                        "example_es": "Hola & adi\u00f3s.",
                    }
                ],
            )
        )
        anki = FakeAnki()
        self.call("<script>alert('x')</script>", "spanish_travel", provider, anki)
        fields = [call for call in anki.calls if call[0] == "addNote"][0][3]
        self.assertEqual("&lt;script&gt;alert(&#x27;x&#x27;)&lt;/script&gt;", fields["Input"])
        self.assertEqual("&lt;b&gt;Hola &amp; adi\u00f3s&lt;/b&gt;", fields["Target"])
        self.assertIn("&lt;ahora&gt;", fields["ContentHtml"])
        self.assertNotIn("<ahora>", fields["ContentHtml"])

    def test_request_stops_on_first_error_and_keeps_prior_results(self):
        class FailsSecond(FakeProvider):
            def generate(self, profile, item):
                self.calls.append((profile.profile_id, item))
                if item == "bad":
                    return spanish_content(senses=[])
                return spanish_content(phrase_es=item)

        provider = FailsSecond(None)
        anki = FakeAnki()
        result = process_request(
            "spanish_travel",
            ["good", "bad", "never"],
            provider=provider,
            image_provider=FakeImageProvider(),
            audio_provider=FakeAudioProvider(),
            anki=anki,
            deck_name="QA",
            legacy_path=self.base / "missing.json",
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
            image_provider=FakeImageProvider(),
            audio_provider=FakeAudioProvider(),
            anki=FailedAddAnki(),
            deck_name="QA",
            legacy_path=legacy,
        )
        self.assertEqual("error", result["status"])
        self.assertTrue(result["error"]["outcome_uncertain"])
        self.assertIn("ItemId=", result["error"]["message"])
        self.assertIn("m\u00eddias enviadas=aa2_", result["error"]["message"])


class ProfileAndFormattingTests(unittest.TestCase):
    def test_both_profiles_share_the_exact_two_card_contract(self):
        expected_fields = ("ItemId", "Input", "Target", "ContentHtml", "Image", "MainAudio")
        expected_templates = ("Target to Meaning", "Image to Target")
        expected_css = (
            ".card {\n"
            "    font-family: arial;\n"
            "    font-size: 20px;\n"
            "    text-align: center;\n"
            "    color: black;\n"
            "    background-color: white;\n"
            "}\n"
        )
        for profile in (ENGLISH_VOCABULARY, SPANISH_TRAVEL):
            with self.subTest(profile=profile.profile_id):
                self.assertEqual(expected_fields, profile.fields)
                self.assertEqual(expected_templates, tuple(profile.templates))
                self.assertEqual(expected_css, profile.css)

                target_card = profile.templates["Target to Meaning"]
                image_card = profile.templates["Image to Target"]
                self.assertIn("color:#0000ff", target_card["Front"])
                self.assertIn("font-weight:700", target_card["Front"])
                self.assertEqual("{{Image}}", image_card["Front"])
                self.assertTrue(target_card["Back"].startswith("{{FrontSide}}\n\n<hr id=answer>\n\n"))
                self.assertTrue(image_card["Back"].startswith("{{FrontSide}}\n\n<hr id=answer>\n\n"))
                self.assertIn("{{Image}}", target_card["Back"])
                self.assertNotIn("{{Image}}", image_card["Back"])
                self.assertIn("color:#0000ff", image_card["Back"])
                self.assertNotIn("{{MainAudio}}", target_card["Front"])
                self.assertNotIn("{{MainAudio}}", image_card["Front"])
                self.assertTrue(target_card["Back"].rstrip().endswith("{{MainAudio}}</div>"))
                self.assertTrue(image_card["Back"].rstrip().endswith("{{MainAudio}}</div>"))

    def test_common_meanings_examples_and_metadata_follow_the_reference_order(self):
        content = english_content()
        content["senses"][0]["definition_en"] = "A <clear> & useful definition."
        content["senses"].append(
            {
                "definition_en": "To refine something until it is ready.",
                "meaning_pt_br": "Aprimorar algo.",
                "example_en": "He polished the final draft.",
            }
        )
        fields = build_note_fields(
            ENGLISH_VOCABULARY,
            "<input>",
            "a" * 64,
            content,
            "aa2_" + "a" * 64 + "_image.png",
            "aa2_" + "a" * 64 + "_main.mp3",
        )
        body = fields["ContentHtml"]
        self.assertNotIn("<clear>", body)
        expected_in_order = (
            "A &lt;clear&gt; &amp; useful definition.",
            "To refine something until it is ready.",
            "Ex.: She polished the table carefully.",
            "Ex.: He polished the final draft.",
            "Polir uma superf\u00edcie. / Aprimorar algo.",
            "Verb / Noun",
            "/\u02c8p\u0252l\u026a\u0283/",
        )
        positions = [body.index(value) for value in expected_in_order]
        self.assertEqual(sorted(positions), positions)
        self.assertGreaterEqual(body.count('style="margin-top:1em;"'), 3)

    def test_english_target_uses_to_only_for_exclusively_verbal_items(self):
        cases = (
            ("Forsake", ["verb"], "to Forsake"),
            ("to Forsake", ["verb"], "to Forsake"),
            ("to Clutch", ["verb", "noun"], "Clutch"),
            ("Clutch", ["verb", "noun"], "Clutch"),
        )
        for term, parts, expected in cases:
            with self.subTest(term=term, parts=parts):
                fields = build_note_fields(
                    ENGLISH_VOCABULARY,
                    term,
                    "a" * 64,
                    english_content(term=term, parts_of_speech=parts),
                    "aa2_" + "a" * 64 + "_image.jpg",
                    "aa2_" + "a" * 64 + "_main.mp3",
                )
                self.assertEqual(expected, fields["Target"])

    def test_spanish_uses_the_same_body_model_with_register_as_classification(self):
        content = spanish_content(ipa="[kiˈsjeɾa peˈðiɾ la ˈkwenta]")
        fields = build_note_fields(
            SPANISH_TRAVEL,
            "Quero pedir a conta",
            "b" * 64,
            content,
            "aa2_" + "b" * 64 + "_image.jpg",
            "aa2_" + "b" * 64 + "_main.mp3",
        )
        self.assertEqual("Quisiera pedir la cuenta, por favor.", fields["Target"])
        self.assertIn("Una forma cort\u00e9s y habitual", fields["ContentHtml"])
        self.assertIn("Ex.: Disculpe, quisiera pedir la cuenta", fields["ContentHtml"])
        self.assertIn("Gostaria de pedir a conta, por favor.", fields["ContentHtml"])
        self.assertIn(">Neutral<", fields["ContentHtml"])
        self.assertIn(">/kiˈsjeɾa peˈðiɾ la ˈkwenta/<", fields["ContentHtml"])
        self.assertNotIn("/[", fields["ContentHtml"])
        self.assertTrue(fields["Image"].startswith('<img src="aa2_'))


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
        self.assertEqual(ENGLISH_VOCABULARY.css, create["css"])

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
        templates["Image to Target"]["Front"] += "<!-- drift -->"
        session = QueueSession(
            [ok(["QA"]), ok([ENGLISH_VOCABULARY.note_type]), ok(list(ENGLISH_VOCABULARY.fields)), ok(templates)]
        )
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError) as raised:
            connector.ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual("model_contract", raised.exception.action)
        self.assertNotIn("createModel", [c["action"] for c in session.calls])

    def test_existing_model_template_order_drift_stops_without_repair(self):
        templates = dict(reversed(tuple(ENGLISH_VOCABULARY.templates.items())))
        session = QueueSession(
            [
                ok(["QA"]),
                ok([ENGLISH_VOCABULARY.note_type]),
                ok(list(ENGLISH_VOCABULARY.fields)),
                ok(templates),
            ]
        )
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError) as raised:
            connector.ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual("model_contract", raised.exception.action)
        self.assertEqual(
            ["deckNames", "modelNames", "modelFieldNames", "modelTemplates"],
            [call["action"] for call in session.calls],
        )

    def test_matching_existing_model_is_accepted_without_mutation(self):
        session = QueueSession(
            [
                ok(["QA"]),
                ok([ENGLISH_VOCABULARY.note_type]),
                ok(list(ENGLISH_VOCABULARY.fields)),
                ok(copy.deepcopy(ENGLISH_VOCABULARY.templates)),
                ok({"css": ENGLISH_VOCABULARY.css}),
            ]
        )
        AnkiConnector(session=session).ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual(
            ["deckNames", "modelNames", "modelFieldNames", "modelTemplates", "modelStyling"],
            [call["action"] for call in session.calls],
        )

    def test_existing_model_styling_drift_stops_without_repair(self):
        session = QueueSession(
            [
                ok(["QA"]),
                ok([ENGLISH_VOCABULARY.note_type]),
                ok(list(ENGLISH_VOCABULARY.fields)),
                ok(copy.deepcopy(ENGLISH_VOCABULARY.templates)),
                ok({"css": ".card { font-size: 16px; }"}),
            ]
        )
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError) as raised:
            connector.ensure_ready(ENGLISH_VOCABULARY, "QA")
        self.assertEqual("model_contract", raised.exception.action)
        self.assertNotIn("updateModelStyling", [call["action"] for call in session.calls])

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

    def test_v2_media_preflight_and_store_use_aa2_names_and_refuse_collision(self):
        item_id = "b" * 64
        filenames = (
            f"aa2_{item_id}_image.jpg",
            f"aa2_{item_id}_image.png",
            f"aa2_{item_id}_main.mp3",
        )
        session = QueueSession([ok(False), ok(False), ok(False), ok(filenames[-1])])
        connector = AnkiConnector(session=session)
        connector.ensure_media_absent(filenames)
        self.assertEqual(filenames[-1], connector.store_media_file(filenames[-1], b"ID3-audio"))
        self.assertEqual(
            ["retrieveMediaFile", "retrieveMediaFile", "retrieveMediaFile", "storeMediaFile"],
            [c["action"] for c in session.calls],
        )
        encoded = session.calls[-1]["params"]["data"]
        self.assertEqual(b"ID3-audio", base64.b64decode(encoded))

        for existing in ("already-present", ""):
            with self.subTest(existing=existing):
                collision = QueueSession([ok(existing)])
                with self.assertRaises(AnkiConnectError):
                    AnkiConnector(session=collision).ensure_media_absent([filenames[0]])
                self.assertEqual(["retrieveMediaFile"], [c["action"] for c in collision.calls])

        mismatch = QueueSession([ok("other.mp3")])
        with self.assertRaises(AnkiConnectError) as raised:
            AnkiConnector(session=mismatch).store_media_file(filenames[-1], b"ID3-audio")
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
                    AnkiConnector(session=session).store_media_file(
                        f"aa2_{'c' * 64}_main.mp3",
                        b"ID3-audio",
                    )
                self.assertEqual("storeMediaFile", raised.exception.action)
                self.assertTrue(raised.exception.outcome_uncertain)
                self.assertEqual(1, len(session.calls))

    def test_invalid_v2_media_stops_before_anki(self):
        session = QueueSession([])
        connector = AnkiConnector(session=session)
        with self.assertRaises(AnkiConnectError):
            connector.ensure_media_absent(["fixture.png"])
        with self.assertRaises(AnkiConnectError):
            connector.store_media_file(f"aa2_{'c' * 64}_main.mp3", b"")
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
                        text=json.dumps(spanish_content(senses=[])),
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

    def test_prompts_require_pareto_content_and_one_image_for_displayed_meanings(self):
        english = (ROOT / "config" / "prompt_template.txt").read_text(encoding="utf-8")
        spanish = (ROOT / "config" / "spanish_prompt_template.txt").read_text(encoding="utf-8")
        for prompt in (english, spanish):
            with self.subTest(prompt=prompt[:20]):
                self.assertIn("significados apresentados", prompt)
                self.assertIn("significado mais comum", prompt)
                self.assertIn("uma única imagem coerente", prompt)
                self.assertIn("sem texto", prompt)
                self.assertIn("Relógios e calendários podem aparecer", prompt)
                self.assertIn("sem texto ou números legíveis", prompt)
                self.assertNotIn("placas, relógios, calendários ou marcas parecidas com texto", prompt)
                self.assertIn("Para cada um dos significados apresentados", prompt)
                self.assertIn("horário, data ou número exato", prompt)
                self.assertIn("uma única cena memorável", prompt)
                self.assertIn("Não use painéis, colagem ou cena dividida", prompt)
                self.assertIn("prefira pessoas, mãos, gestos, objetos", prompt)
                self.assertIn("superfícies que normalmente exibem texto ou números", prompt)
        self.assertIn("mais comum e útil no dia a dia", spanish)
        self.assertIn("registro", spanish)
        self.assertIn("não crie variantes", spanish.casefold())
        self.assertIn("preserve-a exatamente", spanish)
        self.assertIn("não a reformule", spanish)
        self.assertIn("equivalentes curtos", english)
        self.assertIn("equivalentes curtos", spanish)
        self.assertIn("não repita", english)
        self.assertIn("não repita", spanish)
        self.assertIn("sentence case", english)
        self.assertIn("`to ` em minúsculas", english)
        self.assertIn("não use `to`", english.casefold())


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
            settings_path.write_text(
                json.dumps(
                    {
                        "anki_url": "http://localhost:8765",
                        "legacy_index_path": str(legacy),
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
                    request = json.dumps(
                        {"profile": profile_id, "items": [item], "confirmed": True}
                    )
                    with (
                        patch.dict(
                            main_module.os.environ,
                            {
                                "ANTHROPIC_API_KEY": "anthropic-secret",
                                "GEMINI_API_KEY": "gemini-secret",
                                "POLLINATIONS_API_KEY": "pollinations-secret",
                            },
                            clear=True,
                        ),
                        patch.object(main_module, "ClaudeProvider", return_value=FakeProvider(content)),
                        patch.object(
                            main_module,
                            "PollinationsImageProvider",
                            return_value=FakeImageProvider(),
                        ),
                        patch.object(
                            main_module,
                            "GeminiAudioProvider",
                            return_value=FakeAudioProvider(),
                        ),
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
                {
                    "profile": "spanish_travel",
                    "items": ["\ud800"],
                    "confirmed": True,
                },
                ensure_ascii=True,
            )
            stdout = io.StringIO()
            with (
                patch.dict(
                    main_module.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "anthropic-secret",
                        "GEMINI_API_KEY": "gemini-secret",
                    },
                    clear=True,
                ),
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
