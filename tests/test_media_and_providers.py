import base64
import io
import json
import subprocess
import tempfile
import unittest
import wave
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

import requests

import main as main_module
from main import ProcessError, estimate_storage, item_id_for, process_item
from modules.anki_connector import AnkiConnectError
from modules.audio_provider import AudioProviderError, GeminiAudioProvider
from modules.image_provider import ImageProviderError, PollinationsImageProvider


ROOT = Path(__file__).resolve().parents[1]


def english_content():
    return {
        "term": "polish",
        "ipa": "/ˈpɒlɪʃ/",
        "parts_of_speech": ["verb"],
        "senses": [
            {
                "definition_en": "To make a surface smooth and shiny.",
                "meaning_pt_br": "Polir uma superfície.",
                "example_en": "She polished the table carefully.",
                "example_pt_br": "Ela poliu a mesa com cuidado.",
            }
        ],
        "visual_prompt_en": "Hands polishing a plain wooden table, without text.",
    }


def spanish_content():
    return {
        "phrase_es": "Quisiera pedir la cuenta, por favor.",
        "translation_pt_br": "Gostaria de pedir a conta, por favor.",
        "usage_context_pt_br": "Forma neutra e cortês adequada nas Américas.",
        "register": "neutral",
        "example_es": "Disculpe, quisiera pedir la cuenta, por favor.",
        "example_pt_br": "Com licença, gostaria de pedir a conta, por favor.",
    }


def valid_wav() -> bytes:
    target = io.BytesIO()
    with wave.open(target, "wb") as wav_file:
        wav_file.setnchannels(1)
        wav_file.setsampwidth(2)
        wav_file.setframerate(24000)
        wav_file.writeframes(b"\x00\x01" * 800)
    return target.getvalue()


def valid_mp3() -> bytes:
    return b"ID3" + b"\x00" * 1024


def valid_jpeg() -> bytes:
    return b"\xff\xd8\xff" + b"image" * 150 + b"\xff\xd9"


def valid_png() -> bytes:
    return b"\x89PNG\r\n\x1a\n" + b"image" * 150


def interaction(audio: bytes, *, mime_type: str = "audio/l16", blocks: int = 1):
    content = [
        {
            "type": "audio",
            "data": base64.b64encode(audio).decode("ascii"),
            "mime_type": mime_type,
            "sample_rate": 24000,
            "channels": 1,
        }
        for _ in range(blocks)
    ]
    return {
        "status": "completed",
        "steps": [{"content": content}],
        "usage": {
            "input_tokens_by_modality": [{"modality": "text", "tokens": 11}],
            "output_tokens_by_modality": [{"modality": "audio", "tokens": 29}],
        },
    }


class HttpResponse:
    def __init__(self, *, payload=None, content=b"", content_type=""):
        self.payload = payload
        self.content = content
        self.headers = {"Content-Type": content_type}

    def raise_for_status(self):
        return None

    def json(self):
        if isinstance(self.payload, Exception):
            raise self.payload
        return self.payload


class RecordingSession:
    def __init__(self, *, posts=(), gets=()):
        self.posts = list(posts)
        self.gets = list(gets)
        self.post_calls = []
        self.get_calls = []

    def post(self, url, **kwargs):
        self.post_calls.append((url, kwargs))
        response = self.posts.pop(0)
        if isinstance(response, Exception):
            raise response
        return response

    def get(self, url, **kwargs):
        self.get_calls.append((url, kwargs))
        response = self.gets.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def ffmpeg_fake(paths, *, failure=False):
    def run(command, **kwargs):
        wav_path = Path(command[command.index("-i") + 1])
        part_path = Path(command[-1])
        paths.extend((wav_path, part_path))
        if not wav_path.exists():
            raise AssertionError("temporary WAV must exist during conversion")
        part_path.write_bytes(valid_mp3())
        if failure:
            raise subprocess.CalledProcessError(1, command, stderr="conversion failed")
        return SimpleNamespace(returncode=0, stdout="", stderr="")

    return run


class GeminiAudioProviderTests(unittest.TestCase):
    def test_iapetus_payload_for_both_locales_is_single_shot_and_returns_metrics(self):
        session = RecordingSession(
            posts=[
                HttpResponse(payload=interaction(b"\x00\x01" * 800)),
                HttpResponse(payload=interaction(valid_wav(), mime_type="audio/wav")),
            ]
        )
        temporary_paths = []
        provider = GeminiAudioProvider(
            "gemini-secret",
            session=session,
            run_command=ffmpeg_fake(temporary_paths),
        )

        for locale in ("en-US", "es-US"):
            with self.subTest(locale=locale):
                mp3, metrics = provider.generate("Study phrase", locale)
                self.assertTrue(mp3.startswith(b"ID3"))
                self.assertEqual(11, metrics["input_tokens"])
                self.assertEqual(29, metrics["audio_tokens"])
                self.assertEqual(len(mp3), metrics["mp3_bytes"])
                self.assertGreater(metrics["estimated_cost_usd"], 0)

        self.assertEqual(2, len(session.post_calls))
        for locale, (url, call) in zip(("en-US", "es-US"), session.post_calls):
            self.assertEqual(
                "https://generativelanguage.googleapis.com/v1beta/interactions",
                url,
            )
            self.assertEqual("gemini-secret", call["headers"]["x-goog-api-key"])
            self.assertEqual("2026-05-20", call["headers"]["Api-Revision"])
            self.assertNotIn("gemini-secret", url)
            payload = call["json"]
            self.assertEqual("gemini-3.1-flash-tts-preview", payload["model"])
            self.assertEqual({"type": "audio"}, payload["response_format"])
            self.assertIs(False, payload["store"])
            self.assertEqual(
                [{"voice": "Iapetus", "language": locale}],
                payload["generation_config"]["speech_config"],
            )
        self.assertTrue(temporary_paths)
        self.assertTrue(all(not path.exists() for path in temporary_paths))

    def test_invalid_audio_shapes_fail_after_one_call(self):
        cases = (
            interaction(b"\x00\x01" * 800, blocks=0),
            interaction(b"\x00\x01" * 800, blocks=2),
            interaction(b"not pcm", mime_type="audio/mpeg"),
            {
                "status": "completed",
                "steps": [{"content": [{"type": "audio", "data": "%%%"}]}],
            },
        )
        for payload in cases:
            with self.subTest(payload=payload):
                session = RecordingSession(posts=[HttpResponse(payload=payload)])
                provider = GeminiAudioProvider(
                    "secret",
                    session=session,
                    run_command=Mock(),
                )
                with self.assertRaises(AudioProviderError):
                    provider.generate("hello", "en-US")
                self.assertEqual(1, len(session.post_calls))

    def test_audio_uses_documented_defaults_when_metadata_is_omitted(self):
        for source_audio in (b"\x00\x01" * 800, valid_wav()):
            with self.subTest(wav=source_audio.startswith(b"RIFF")):
                payload = interaction(source_audio)
                audio = payload["steps"][0]["content"][0]
                for field in ("mime_type", "sample_rate", "channels"):
                    audio.pop(field)
                paths = []
                provider = GeminiAudioProvider(
                    "secret",
                    session=RecordingSession(posts=[HttpResponse(payload=payload)]),
                    run_command=ffmpeg_fake(paths),
                )
                mp3, _ = provider.generate("hello", "en-US")
                self.assertTrue(mp3.startswith(b"ID3"))
                self.assertTrue(all(not path.exists() for path in paths))

    def test_conversion_failure_removes_wav_and_partial(self):
        session = RecordingSession(
            posts=[HttpResponse(payload=interaction(b"\x00\x01" * 800))]
        )
        paths = []
        provider = GeminiAudioProvider(
            "secret",
            session=session,
            run_command=ffmpeg_fake(paths, failure=True),
        )
        with self.assertRaises(AudioProviderError):
            provider.generate("hello", "en-US")
        self.assertEqual(1, len(session.post_calls))
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_conversion_timeout_is_bounded_and_removes_temporary_files(self):
        session = RecordingSession(
            posts=[HttpResponse(payload=interaction(b"\x00\x01" * 800))]
        )
        paths = []

        def timeout_runner(command, **kwargs):
            wav_path = Path(command[command.index("-i") + 1])
            part_path = Path(command[-1])
            paths.extend((wav_path, part_path))
            self.assertEqual(120, kwargs["timeout"])
            raise subprocess.TimeoutExpired(command, kwargs["timeout"])

        provider = GeminiAudioProvider(
            "secret",
            session=session,
            run_command=timeout_runner,
        )
        with self.assertRaisesRegex(AudioProviderError, "tempo limite"):
            provider.generate("hello", "en-US")
        self.assertEqual(1, len(session.post_calls))
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_successful_ffmpeg_with_invalid_output_is_rejected_and_cleaned(self):
        session = RecordingSession(
            posts=[HttpResponse(payload=interaction(b"\x00\x01" * 800))]
        )
        paths = []

        def invalid_output_runner(command, **kwargs):
            wav_path = Path(command[command.index("-i") + 1])
            part_path = Path(command[-1])
            paths.extend((wav_path, part_path))
            part_path.write_bytes(b"not an mp3")
            return SimpleNamespace(returncode=0, stdout="", stderr="")

        provider = GeminiAudioProvider(
            "secret",
            session=session,
            run_command=invalid_output_runner,
        )
        with self.assertRaisesRegex(AudioProviderError, "MP3 válido"):
            provider.generate("hello", "en-US")
        self.assertEqual(1, len(session.post_calls))
        self.assertTrue(paths)
        self.assertTrue(all(not path.exists() for path in paths))

    def test_transport_error_redacts_secret_without_retry(self):
        session = RecordingSession(posts=[requests.Timeout("failed for gemini-secret")])
        provider = GeminiAudioProvider("gemini-secret", session=session)
        with self.assertRaises(AudioProviderError) as raised:
            provider.generate("hello", "en-US")
        self.assertNotIn("gemini-secret", str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))
        self.assertEqual(1, len(session.post_calls))

    def test_missing_ffmpeg_stops_before_the_paid_call(self):
        session = RecordingSession(posts=[HttpResponse(payload=interaction(valid_wav()))])
        with patch("modules.audio_provider.shutil.which", return_value=None):
            with self.assertRaisesRegex(AudioProviderError, "ffmpeg"):
                GeminiAudioProvider("secret", session=session)
        self.assertEqual([], session.post_calls)


class PollinationsImageProviderTests(unittest.TestCase):
    def test_flux_get_uses_bearer_without_key_in_url_and_accepts_jpeg_or_png(self):
        session = RecordingSession(
            gets=[
                HttpResponse(content=valid_jpeg(), content_type="image/jpeg"),
                HttpResponse(content=valid_png(), content_type="image/png; charset=binary"),
            ]
        )
        provider = PollinationsImageProvider("pollinations-secret", session=session)

        self.assertEqual((valid_jpeg(), "jpg"), provider.generate("a visual prompt"))
        self.assertEqual((valid_png(), "png"), provider.generate("another prompt"))
        self.assertEqual(2, len(session.get_calls))
        for url, call in session.get_calls:
            self.assertTrue(url.startswith("https://gen.pollinations.ai/image/"))
            self.assertNotIn("pollinations-secret", url)
            self.assertEqual("Bearer pollinations-secret", call["headers"]["Authorization"])
            self.assertEqual("image/jpeg,image/png", call["headers"]["Accept"])
            self.assertEqual({"model": "flux", "width": 1024, "height": 1024}, call["params"])
            self.assertNotIn("nologo", call["params"])
            self.assertNotIn("quality", call["params"])

    def test_mime_or_signature_mismatch_is_terminal(self):
        cases = (
            HttpResponse(content=valid_jpeg(), content_type="image/png"),
            HttpResponse(
                content=b"\xff\xd8" + b"not-jpeg" * 100 + b"\xff\xd9",
                content_type="image/jpeg",
            ),
            HttpResponse(content=b"not an image" * 100, content_type="image/jpeg"),
            HttpResponse(content=valid_png(), content_type="image/webp"),
        )
        for response in cases:
            with self.subTest(content_type=response.headers["Content-Type"]):
                session = RecordingSession(gets=[response])
                with self.assertRaises(ImageProviderError):
                    PollinationsImageProvider("secret", session=session).generate("prompt")
                self.assertEqual(1, len(session.get_calls))

    def test_transport_error_redacts_secret_without_retry(self):
        session = RecordingSession(gets=[requests.Timeout("failed for image-secret")])
        provider = PollinationsImageProvider("image-secret", session=session)
        with self.assertRaises(ImageProviderError) as raised:
            provider.generate("prompt")
        self.assertNotIn("image-secret", str(raised.exception))
        self.assertIn("[redacted]", str(raised.exception))
        self.assertEqual(1, len(session.get_calls))


class TextProviderUsageTests(unittest.TestCase):
    def test_anthropic_provider_records_real_input_and_output_tokens(self):
        message = SimpleNamespace(
            stop_reason="end_turn",
            content=[SimpleNamespace(type="text", text=json.dumps(spanish_content()))],
            usage=SimpleNamespace(input_tokens=37, output_tokens=83),
        )
        messages = SimpleNamespace(create=Mock(return_value=message))
        provider = main_module.ClaudeProvider(
            "secret",
            ROOT / "config" / "spanish_prompt_template.txt",
            client=SimpleNamespace(messages=messages),
        )
        self.assertEqual(spanish_content(), provider.generate(main_module.get_profile("spanish_travel"), "x"))
        self.assertEqual({"input_tokens": 37, "output_tokens": 83}, provider.last_usage)


class FakeTextProvider:
    def __init__(self, content, events=None):
        self.content = content
        self.calls = []
        self.events = events
        self.last_usage = {"input_tokens": 7, "output_tokens": 13}

    def generate(self, profile, item):
        self.calls.append((profile.profile_id, item))
        if self.events is not None:
            self.events.append("text")
        return self.content


class FakeImageProvider:
    def __init__(self, events=None):
        self.calls = []
        self.events = events

    def generate(self, prompt):
        self.calls.append(prompt)
        if self.events is not None:
            self.events.append("image")
        return valid_jpeg(), "jpg"


class FakeAudioProvider:
    def __init__(self, events=None):
        self.calls = []
        self.events = events

    def generate(self, text, locale):
        self.calls.append((text, locale))
        if self.events is not None:
            self.events.append("audio")
        return valid_mp3(), {
            "input_tokens": 3,
            "audio_tokens": 5,
            "mp3_bytes": len(valid_mp3()),
            "estimated_cost_usd": 0.000103,
        }


class FakeAnki:
    def __init__(self, *, existing=(), events=None):
        self.existing = list(existing)
        self.events = events
        self.calls = []

    def _event(self, value):
        if self.events is not None:
            self.events.append(value)

    def find_exact_items(self, item_id):
        self.calls.append(("find", item_id))
        self._event("identity")
        return self.existing

    def ensure_ready(self, profile, deck_name):
        self.calls.append(("ready", profile.profile_id, deck_name))
        self._event("ready")

    def ensure_media_absent(self, filenames):
        self.calls.append(("media_preflight", tuple(filenames)))
        self._event("media_preflight")

    def store_media_file(self, filename, data):
        self.calls.append(("store", filename, data))
        self._event(f"store:{Path(filename).suffix}")
        return filename

    def add_note(self, profile, deck_name, fields):
        self.calls.append(("addNote", profile.profile_id, deck_name, fields))
        self._event("addNote")
        return 1234


class MediaFlowTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.legacy = Path(self.temp_dir.name) / "processadas.json"
        self.legacy.write_text("{}", encoding="utf-8")

    def call(self, item, profile_id, text, image, audio, anki):
        return process_item(
            item,
            profile_id,
            provider=text,
            image_provider=image,
            audio_provider=audio,
            anki=anki,
            deck_name="QA",
            legacy_path=self.legacy,
        )

    def test_english_generates_all_media_before_upload_and_uses_one_main_audio(self):
        events = []
        text = FakeTextProvider(english_content(), events)
        image = FakeImageProvider(events)
        audio = FakeAudioProvider(events)
        anki = FakeAnki(events=events)
        result = self.call("polish", "english_vocabulary", text, image, audio, anki)

        item_id = item_id_for("english_vocabulary", "polish")
        self.assertEqual(
            (
                f"aa2_{item_id}_image.jpg",
                f"aa2_{item_id}_image.png",
                f"aa2_{item_id}_main.mp3",
            ),
            [call for call in anki.calls if call[0] == "media_preflight"][0][1],
        )
        self.assertLess(events.index("image"), events.index("store:.jpg"))
        self.assertLess(events.index("audio"), events.index("store:.jpg"))
        fields = [call for call in anki.calls if call[0] == "addNote"][0][3]
        self.assertEqual(f"[sound:aa2_{item_id}_main.mp3]", fields["MainAudio"])
        self.assertEqual("", fields["ExampleAudio"])
        self.assertEqual(1, len([call for call in anki.calls if call[0] == "addNote"]))
        self.assertEqual(7, result["metrics"]["anthropic"]["input_tokens"])
        self.assertEqual(5, result["metrics"]["gemini"]["audio_tokens"])
        self.assertEqual(0.002, result["metrics"]["pollinations"]["estimated_cost_usd"])

    def test_spanish_generates_only_main_audio(self):
        text = FakeTextProvider(spanish_content())
        image = FakeImageProvider()
        audio = FakeAudioProvider()
        anki = FakeAnki()
        self.call("Quero pagar", "spanish_travel", text, image, audio, anki)
        self.assertEqual([], image.calls)
        self.assertEqual(
            [("Quisiera pedir la cuenta, por favor.", "es-US")],
            audio.calls,
        )
        stored = [call[1] for call in anki.calls if call[0] == "store"]
        self.assertEqual(1, len(stored))
        self.assertTrue(stored[0].endswith("_main.mp3"))

    def test_image_failure_stops_before_audio_or_anki_mutation(self):
        class FailedImageProvider(FakeImageProvider):
            def generate(self, prompt):
                self.calls.append(prompt)
                raise ImageProviderError("image failed")

        image = FailedImageProvider()
        audio = FakeAudioProvider()
        anki = FakeAnki()
        with self.assertRaises(ProcessError) as raised:
            self.call(
                "polish",
                "english_vocabulary",
                FakeTextProvider(english_content()),
                image,
                audio,
                anki,
            )
        self.assertEqual("image_provider", raised.exception.stage)
        self.assertEqual([], audio.calls)
        self.assertFalse(any(call[0] in {"store", "addNote"} for call in anki.calls))

    def test_audio_failure_stops_before_anki_mutation_for_both_profiles(self):
        class FailedAudioProvider(FakeAudioProvider):
            def generate(self, text, locale):
                self.calls.append((text, locale))
                raise AudioProviderError("audio failed")

        cases = (
            ("polish", "english_vocabulary", english_content(), FakeImageProvider()),
            ("Quero pagar", "spanish_travel", spanish_content(), None),
        )
        for item, profile_id, content, image in cases:
            with self.subTest(profile=profile_id):
                audio = FailedAudioProvider()
                anki = FakeAnki()
                with self.assertRaises(ProcessError) as raised:
                    self.call(
                        item,
                        profile_id,
                        FakeTextProvider(content),
                        image,
                        audio,
                        anki,
                    )
                self.assertEqual("audio_provider", raised.exception.stage)
                self.assertEqual(1, len(audio.calls))
                self.assertFalse(
                    any(call[0] in {"store", "addNote"} for call in anki.calls)
                )

    def test_v2_legacy_and_collision_stop_before_all_providers(self):
        def assert_unused(text, image, audio):
            self.assertEqual([], text.calls)
            self.assertEqual([], image.calls)
            self.assertEqual([], audio.calls)

        text = FakeTextProvider(spanish_content())
        image = FakeImageProvider()
        audio = FakeAudioProvider()
        result = self.call(
            "existing",
            "spanish_travel",
            text,
            image,
            audio,
            FakeAnki(existing=["existing"]),
        )
        self.assertEqual("skipped_v2", result["reason"])
        assert_unused(text, image, audio)

        self.legacy.write_text(json.dumps({"polish": {}}), encoding="utf-8")
        text = FakeTextProvider(english_content())
        image = FakeImageProvider()
        audio = FakeAudioProvider()
        result = self.call("polish", "english_vocabulary", text, image, audio, FakeAnki())
        self.assertEqual("skipped_legacy", result["reason"])
        assert_unused(text, image, audio)

        class CollisionAnki(FakeAnki):
            def ensure_media_absent(self, filenames):
                raise AnkiConnectError("retrieveMediaFile", "collision")

        self.legacy.write_text("{}", encoding="utf-8")
        text = FakeTextProvider(english_content())
        image = FakeImageProvider()
        audio = FakeAudioProvider()
        with self.assertRaises(ProcessError) as raised:
            self.call("polish", "english_vocabulary", text, image, audio, CollisionAnki())
        self.assertEqual("media", raised.exception.stage)
        assert_unused(text, image, audio)

    def test_add_note_failure_lists_every_uploaded_filename(self):
        class FailedAddAnki(FakeAnki):
            def add_note(self, profile, deck_name, fields):
                raise AnkiConnectError("addNote", "timeout", outcome_uncertain=True)

        with self.assertRaises(ProcessError) as raised:
            self.call(
                "polish",
                "english_vocabulary",
                FakeTextProvider(english_content()),
                FakeImageProvider(),
                FakeAudioProvider(),
                FailedAddAnki(),
            )
        item_id = item_id_for("english_vocabulary", "polish")
        self.assertTrue(raised.exception.outcome_uncertain)
        self.assertIn(f"aa2_{item_id}_image.jpg", str(raised.exception))
        self.assertIn(f"aa2_{item_id}_main.mp3", str(raised.exception))

    def test_uncertain_second_upload_reports_previous_and_current_media(self):
        class FailedAudioUploadAnki(FakeAnki):
            def store_media_file(self, filename, data):
                if filename.endswith("_main.mp3"):
                    raise AnkiConnectError(
                        "storeMediaFile",
                        "timeout",
                        outcome_uncertain=True,
                    )
                return super().store_media_file(filename, data)

        with self.assertRaises(ProcessError) as raised:
            self.call(
                "polish",
                "english_vocabulary",
                FakeTextProvider(english_content()),
                FakeImageProvider(),
                FakeAudioProvider(),
                FailedAudioUploadAnki(),
            )
        item_id = item_id_for("english_vocabulary", "polish")
        self.assertTrue(raised.exception.outcome_uncertain)
        self.assertIn(f"mídias enviadas=aa2_{item_id}_image.jpg", str(raised.exception))
        self.assertIn(f"mídia atual=aa2_{item_id}_main.mp3", str(raised.exception))


class EstimateAndConfirmationTests(unittest.TestCase):
    def test_plan_storage_estimate_is_simple_and_profile_specific(self):
        self.assertEqual(
            {"items": 2, "min_bytes": 2 * 88 * 1024, "max_bytes": 2 * 364 * 1024},
            estimate_storage("english_vocabulary", 2),
        )
        self.assertEqual(
            {"items": 2, "min_bytes": 2 * 32 * 1024, "max_bytes": 2 * 192 * 1024},
            estimate_storage("spanish_travel", 2),
        )

    def test_unconfirmed_json_batch_returns_before_settings_or_provider_construction(self):
        stdout = io.StringIO()
        request = json.dumps({"profile": "spanish_travel", "items": ["one", "two"]})
        with (
            patch.object(main_module, "ClaudeProvider") as text_constructor,
            patch.object(main_module, "GeminiAudioProvider") as audio_constructor,
            patch.object(main_module, "PollinationsImageProvider") as image_constructor,
            patch.object(main_module, "_load_settings") as settings_loader,
            patch.object(main_module.sys, "stdin", io.StringIO(request)),
            redirect_stdout(stdout),
        ):
            exit_code = main_module.main(["--json", "--settings", "/missing/settings.json"])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("needs_confirmation", payload["status"])
        self.assertEqual({"status", "estimate", "created", "skipped", "error"}, set(payload))
        self.assertEqual(2, payload["estimate"]["items"])
        settings_loader.assert_not_called()
        text_constructor.assert_not_called()
        audio_constructor.assert_not_called()
        image_constructor.assert_not_called()

    def test_confirmed_json_batch_runs_and_spanish_never_constructs_image_provider(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
                json.dumps(
                    {
                        "anki_url": "http://localhost:8765",
                        "profiles": {
                            "spanish_travel": {
                                "deck_name": "QA",
                                "anthropic_model": "claude-sonnet-4-6",
                            }
                        },
                    }
                ),
                encoding="utf-8",
            )
            text = FakeTextProvider(spanish_content())
            audio = FakeAudioProvider()
            anki = FakeAnki()
            stdout = io.StringIO()
            request = json.dumps(
                {
                    "profile": "spanish_travel",
                    "items": ["one", "two"],
                    "confirmed": True,
                }
            )
            with (
                patch.dict(
                    main_module.os.environ,
                    {
                        "ANTHROPIC_API_KEY": "anthropic-secret",
                        "GEMINI_API_KEY": "gemini-secret",
                    },
                    clear=True,
                ),
                patch.object(main_module, "ClaudeProvider", return_value=text),
                patch.object(main_module, "GeminiAudioProvider", return_value=audio),
                patch.object(main_module, "PollinationsImageProvider") as image_constructor,
                patch.object(main_module, "AnkiConnector", return_value=anki),
                patch.object(main_module.sys, "stdin", io.StringIO(request)),
                redirect_stdout(stdout),
            ):
                exit_code = main_module.main(["--json", "--settings", str(settings)])
        payload = json.loads(stdout.getvalue())
        self.assertEqual(0, exit_code)
        self.assertEqual("ok", payload["status"])
        self.assertEqual(2, len(payload["created"]))
        self.assertEqual(2, len(text.calls))
        self.assertEqual(2, len(audio.calls))
        image_constructor.assert_not_called()

    def test_configured_run_rejects_missing_keys_before_constructing_clients(self):
        with tempfile.TemporaryDirectory() as tmp:
            settings = Path(tmp) / "settings.json"
            settings.write_text(
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
            with (
                patch.dict(main_module.os.environ, {}, clear=True),
                patch.object(main_module, "ClaudeProvider") as text_constructor,
                patch.object(main_module, "GeminiAudioProvider") as audio_constructor,
                patch.object(main_module, "AnkiConnector") as anki_constructor,
            ):
                result = main_module._run_configured(
                    "spanish_travel",
                    ["Quero pagar"],
                    settings,
                )
        self.assertEqual("error", result["status"])
        self.assertEqual("settings", result["error"]["stage"])
        text_constructor.assert_not_called()
        audio_constructor.assert_not_called()
        anki_constructor.assert_not_called()

    def test_cli_decline_is_a_simple_non_persistent_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            items = Path(tmp) / "items.txt"
            items.write_text("one\ntwo\n", encoding="utf-8")
            stdout = io.StringIO()
            stderr = io.StringIO()
            with (
                patch.object(main_module, "ClaudeProvider") as text_constructor,
                patch.object(main_module.sys, "stdin", io.StringIO("n\n")),
                redirect_stdout(stdout),
                redirect_stderr(stderr),
            ):
                exit_code = main_module.main(
                    [
                        "--profile",
                        "spanish_travel",
                        "--file",
                        str(items),
                        "--settings",
                        "/missing/settings.json",
                    ]
                )
        self.assertEqual(0, exit_code)
        self.assertEqual("needs_confirmation", json.loads(stdout.getvalue())["status"])
        self.assertIn("Continuar", stderr.getvalue())
        text_constructor.assert_not_called()


class ScopeGuardTests(unittest.TestCase):
    def test_media_path_has_no_openai_aws_fallback_or_retry_framework(self):
        source = "\n".join(
            (ROOT / path).read_text(encoding="utf-8").casefold()
            for path in (
                "main.py",
                "modules/audio_provider.py",
                "modules/image_provider.py",
            )
        )
        for forbidden in ("openai", "boto3", "amazonaws", "fallback", "max_retries"):
            self.assertNotIn(forbidden, source)

    def test_versioned_settings_contain_no_secrets(self):
        settings = (ROOT / "config" / "settings.example.json").read_text(encoding="utf-8")
        for secret_name in ("ANTHROPIC_API_KEY", "GEMINI_API_KEY", "POLLINATIONS_API_KEY"):
            self.assertNotIn(secret_name, settings)


if __name__ == "__main__":
    unittest.main()
