"""Contrato do árabe de viagem no mesmo fluxo dos demais idiomas."""

import io
import json
import unittest
from contextlib import redirect_stdout
from unittest.mock import patch

import main
from modules.card_formatter import build_note_fields
from modules.profiles import ARABIC_TRAVEL, get_profile, validate_profile_content
from test_core_flow import FakeAnki, FakeAudioProvider, FakeImageProvider, FakeProvider


def arabic_content():
    return {
        "phrase_ar": "شُكْرًا",
        "romanization": "Shukran",
        "ipa": "/ˈʃukran/",
        "register": "neutral",
        "senses": [{
            "definition_pt_br": "Para agradecer a alguém durante a viagem.",
            "meaning_pt_br": "Obrigado.",
            "example_romanization": "Shukran ʿala l-musāʿada.",
        }],
        "visual_prompt_en": "A traveler thanking a host, without text or numbers.",
    }


class ArabicTravelTests(unittest.TestCase):
    def test_profile_and_visible_fields_follow_the_shared_card_contract(self):
        profile = get_profile("arabic_travel")
        self.assertIs(ARABIC_TRAVEL, profile)
        content = validate_profile_content(profile, arabic_content())
        fields = build_note_fields(profile, "Obrigado", "id", content, "image.jpg", "audio.mp3")
        self.assertEqual("Shukran", fields["Target"])
        self.assertIn("Obrigado.", fields["ContentHtml"])
        self.assertIn("<div>/ˈʃukran/</div>", fields["ContentHtml"])
        self.assertNotIn("ش", fields["ContentHtml"])
        self.assertEqual("[sound:audio.mp3]", fields["MainAudio"])
        self.assertEqual(("Target to Meaning", "Image to Target"), tuple(profile.templates))

    def test_invalid_arabic_content_stops_before_media_and_writes(self):
        cases = []
        for field, values in {
            "phrase_ar": ("Shukran", "شكرا Shukran", "123"),
            "romanization": ("شكرا", "Shukran،", "Shukran ٣", ""),
            "ipa": ("/شكرا/", "/aش/", "/ːˈʲ/", ""),
        }.items():
            for value in values:
                content = arabic_content()
                content[field] = value
                cases.append(content)
        for field in ("definition_pt_br", "meaning_pt_br", "example_romanization"):
            content = arabic_content()
            content["senses"][0][field] = "Texto شكرا"
            cases.append(content)
        for content in cases:
            with self.subTest(content=content):
                image, audio, anki = FakeImageProvider(), FakeAudioProvider(), FakeAnki()
                with self.assertRaises(main.ProcessError) as raised:
                    main.process_item("Obrigado", "arabic_travel", provider=FakeProvider(content),
                                      image_provider=image, audio_provider=audio, anki=anki,
                                      deck_name="Árabe para Viagem", legacy_path=None)
                self.assertEqual("validation", raised.exception.stage)
                self.assertEqual([], image.calls)
                self.assertEqual([], audio.calls)
                self.assertFalse(any(call[0] in {"store_media", "addNote"} for call in anki.calls))

    def test_native_transcript_reaches_audio_and_same_input_is_skipped(self):
        content = arabic_content()
        provider, image, audio, anki = FakeProvider(content), FakeImageProvider(), FakeAudioProvider(), FakeAnki()
        kwargs = dict(provider=provider, image_provider=image, audio_provider=audio, anki=anki,
                      deck_name="Árabe para Viagem", legacy_path=None)
        result = main.process_item("Obrigado", "arabic_travel", **kwargs)
        self.assertEqual("created", result["kind"])
        self.assertEqual([(content["phrase_ar"], "ar-AE", ARABIC_TRAVEL.audio_instruction)], audio.calls)
        note_call = next(call for call in anki.calls if call[0] == "addNote")
        self.assertEqual("Árabe para Viagem", note_call[2])
        self.assertEqual("Shukran", note_call[3]["Target"])
        anki.existing = ["Obrigado"]
        result = main.process_item("  OBRIGADO  ", "arabic_travel", **kwargs)
        self.assertEqual("skipped_v2", result["reason"])
        self.assertEqual(1, len(provider.calls))
        self.assertEqual(1, len(audio.calls))

    def test_preview_needs_one_confirmation_without_loading_settings(self):
        request = {"profile": "arabic_travel", "items": ["Obrigado", "Onde fica o hotel?"]}
        stdout = io.StringIO()
        with (
            patch("sys.stdin", io.StringIO(json.dumps(request))),
            redirect_stdout(stdout),
            patch.object(main, "_run_configured") as configured,
        ):
            self.assertEqual(0, main.main(["--json"]))
        payload = json.loads(stdout.getvalue())
        self.assertEqual("needs_confirmation", payload["status"])
        self.assertEqual(2, payload["estimate"]["items"])
        self.assertEqual([], payload["created"])
        configured.assert_not_called()
