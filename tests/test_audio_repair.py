"""A media replacement preserves the existing notes, cards and review history."""
import base64
import copy
import hashlib
import tempfile
import unittest
from pathlib import Path

import requests

from modules.anki_connector import AnkiConnector, AnkiConnectError
from modules.audio_repair import repair_note
from modules.profiles import ARABIC_TRAVEL


class Response:
    def __init__(self, result):
        self.result = result
    def raise_for_status(self):
        pass
    def json(self):
        return {"result": self.result, "error": None}


class AnkiState:
    def __init__(self):
        self.fields = dict(zip(ARABIC_TRAVEL.fields, ["a" * 64, "Salam", "Salām", "IPA", "image", "[sound:old.mp3]"]))
        self.note = {"noteId": 12, "modelName": ARABIC_TRAVEL.note_type, "fields": {k: {"value": v} for k,v in self.fields.items()}, "cards": [21, 22], "tags": ["arabic"]}
        self.cards = [{"cardId": i, "note": 12, "deckName": "Arabic", "ord": n, "queue": 2, "due": 77, "reps": 9, "lapses": 1, "interval": 5} for n,i in enumerate([21,22])]
        self.reviews = {str(i): [{"id": 34, "ease": 3, "ivl": 5}] for i in [21,22]}
        self.media = {"old.mp3": b"old-audio"}
        self.calls = []
        self.fail = None
        self.corrupt_media = False
        self.change_after_store = False
        self.media_name_limit = None
    def post(self, url, *, json, timeout):
        action, p = json["action"], json["params"]
        self.calls.append(action)
        if self.fail == action:
            raise requests.Timeout("test timeout")
        if action == "notesInfo": result = [self.note]
        elif action == "cardsInfo": result = self.cards
        elif action == "getReviewsOfCards": result = self.reviews
        elif action == "retrieveMediaFile":
            content = self.media.get(p["filename"])
            result = base64.b64encode(content).decode() if content is not None else False
        elif action == "storeMediaFile":
            filename = p["filename"]
            if self.media_name_limit and len(filename.encode()) > self.media_name_limit:
                suffix = Path(filename).suffix
                filename = Path(filename).stem[:self.media_name_limit - len(suffix)] + suffix
            self.media[filename] = b"corrupt" if self.corrupt_media else base64.b64decode(p["data"])
            if self.change_after_store: self.note["fields"]["Target"]["value"] = "concurrent edit"
            result = filename
        elif action == "updateNoteFields":
            for k,v in p["note"]["fields"].items(): self.note["fields"][k]["value"] = v
            result = None
        else: raise AssertionError(action)
        return Response(copy.deepcopy(result))


class RepairTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name).resolve()
        self.audio = self.root / "human.wav"
        self.audio.write_bytes(b"RIFF" + b"\0"*4 + b"WAVE" + b"recorded-audio")
        self.state = AnkiState()
        self.client = AnkiConnector(session=self.state)
        self.request = {"profile": "arabic_travel", "note_id": 12, "audio_path": str(self.audio), "audio_sha256": hashlib.sha256(self.audio.read_bytes()).hexdigest(), "source_url": "https://example.edu/audio", "transcript": "السلام عليكم", "fields": {}, "confirmed": False}
    def run_request(self):
        return repair_note(self.request, anki=self.client, deck_name="Arabic", media_root=self.root)
    def prepare(self):
        result = self.run_request()
        self.request.update(confirmed=True, expected_state=result["expected_state"])
        return result
    def test_preview_is_read_only_and_exposes_exact_changes(self):
        result = self.run_request()
        self.assertEqual(result["status"], "preview")
        self.assertEqual(result["before"]["fields"], self.state.fields)
        self.assertIn("MainAudio", result["changes"])
        self.assertNotIn("storeMediaFile", self.state.calls)
        self.assertNotIn("updateNoteFields", self.state.calls)
    def test_apply_preserves_history_identity_and_original_media(self):
        before_cards, before_reviews = copy.deepcopy(self.state.cards), copy.deepcopy(self.state.reviews)
        self.request["fields"] = {"Target": "As-salāmu ʿalaykum", "ContentHtml": "aligned pronunciation"}
        self.prepare()
        result = self.run_request()
        self.assertEqual(result["status"], "ok")
        self.assertTrue(result["verified"])
        self.assertEqual(result["note_id"], 12)
        self.assertEqual(self.state.cards, before_cards)
        self.assertEqual(self.state.reviews, before_reviews)
        self.assertEqual(self.state.media["old.mp3"], b"old-audio")
        self.assertEqual(self.state.media[result["filename"]], self.audio.read_bytes())
        self.assertEqual(self.state.note["fields"]["Image"]["value"], "image")
        self.assertEqual(self.state.note["fields"]["Target"]["value"], self.request["fields"]["Target"])
        self.assertEqual(self.state.calls.count("updateNoteFields"), 1)
    def test_conflict_blocks_every_write(self):
        self.prepare()
        self.state.note["fields"]["Target"]["value"] = "changed"
        with self.assertRaisesRegex(ValueError, "mudou"): self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)
    def test_apply_with_anki_media_filename_truncation(self):
        self.state.media_name_limit = 119
        preview = self.prepare()
        result = self.run_request()
        self.assertTrue(result["verified"])
        self.assertLessEqual(len(preview["filename"].encode()), 119)
        self.assertEqual(self.state.media[preview["filename"]], self.audio.read_bytes())
        self.assertEqual(self.state.note["fields"]["MainAudio"]["value"], f"[sound:{preview['filename']}]")
    def test_concurrent_edit_during_upload_is_not_overwritten(self):
        self.prepare()
        self.state.change_after_store = True
        with self.assertRaises(AnkiConnectError) as ctx: self.run_request()
        self.assertTrue(ctx.exception.outcome_uncertain)
        self.assertNotIn("updateNoteFields", self.state.calls)
        self.assertEqual(self.state.note["fields"]["Target"]["value"], "concurrent edit")
    def test_media_hash_mismatch_never_writes(self):
        self.request["audio_sha256"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "hash"): self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)
    def test_upload_bytes_are_verified_before_note_change(self):
        self.prepare()
        self.state.corrupt_media = True
        with self.assertRaises(AnkiConnectError) as ctx: self.run_request()
        self.assertTrue(ctx.exception.outcome_uncertain)
        self.assertNotIn("updateNoteFields", self.state.calls)
    def test_update_timeout_is_uncertain_without_retry(self):
        self.prepare()
        self.state.fail = "updateNoteFields"
        with self.assertRaises(AnkiConnectError) as ctx: self.run_request()
        self.assertTrue(ctx.exception.outcome_uncertain)
        self.assertEqual(self.state.calls.count("updateNoteFields"), 1)
    def test_reject_legacy_note_wrong_deck_and_identity_changes(self):
        for mutation in ("model", "deck", "item"):
            with self.subTest(mutation=mutation):
                self.setUp()
                if mutation == "model": self.state.note["modelName"] = "Basic"
                if mutation == "deck": self.state.cards[0]["deckName"] = "Other"
                if mutation == "item": self.request["fields"] = {"ItemId": "b"*64}
                with self.assertRaises(ValueError): self.run_request()
                self.assertNotIn("storeMediaFile", self.state.calls)
    def test_path_escape_and_symlink_are_rejected(self):
        with tempfile.TemporaryDirectory() as other:
            p = Path(other) / "audio.wav"; p.write_bytes(self.audio.read_bytes())
            for path in (p, self.root / "link.wav"):
                if path.name == "link.wav": path.symlink_to(self.audio)
                self.request["audio_path"] = str(path)
                with self.assertRaises(ValueError): self.run_request()
    def test_existing_identical_media_reused_without_overwrite(self):
        preview = self.prepare()
        self.state.media[preview["filename"]] = self.audio.read_bytes()
        self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)
    def test_existing_different_media_never_overwritten(self):
        preview = self.prepare()
        self.state.media[preview["filename"]] = b"collision"
        with self.assertRaises(ValueError): self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)
        self.assertNotIn("updateNoteFields", self.state.calls)
