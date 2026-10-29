"""Image replacement changes one src, preserves study state, and can be undone."""
import base64
import copy
import hashlib
from pathlib import Path
import tempfile
import unittest
from typing import Any
from urllib.parse import unquote

from modules.anki_connector import AnkiConnector, AnkiConnectError
from modules.image_repair import MAX_IMAGE_BYTES, repair_image
from test_audio_repair import AnkiState, Response


FIXTURE = Path(__file__).parent / "fixtures" / "qa-image.png"


class ImageState(AnkiState):
    def __init__(self, basic: bool = False) -> None:
        super().__init__()
        self.broken_display = False
        self.change_old_media = False
        self.css = ".card { color: black; }"
        self.image_html = '<div>Texto preservado <img class="concept" src="old.png" alt="old.png"> fim.</div>'
        if basic:
            self.note.update(modelName="Basic", cards=[21])
            self.note["fields"] = {"Front": {"value": "Palavra"}, "Back": {"value": self.image_html + "[sound:old.mp3]"}}
            self.cards = self.cards[:1]
            self.reviews = {"21": self.reviews["21"]}
        else:
            self.note["fields"]["Image"]["value"] = self.image_html
        self.media["old.png"] = FIXTURE.read_bytes()

    def post(self, url: str, *, json: dict[str, Any], timeout: float) -> Response:
        action = json["action"]
        if action == "modelTemplates":
            self.calls.append(action)
            return Response({"Card": {"Front": "{{Front}}", "Back": "{{Back}}"}})
        if action == "modelStyling":
            self.calls.append(action)
            return Response({"css": self.css})
        result = super().post(url, json=json, timeout=timeout)
        if action == "storeMediaFile" and self.change_old_media:
            self.media["old.png"] = b"concurrent media edit"
        if action == "cardsInfo":
            result.result = [card for card in result.result if card["cardId"] in json["params"]["cards"]]
            fields = self.note["fields"]
            question = fields["Front"]["value"] if self.note["modelName"] == "Basic" else "<b>Palavra</b>"
            display = fields["Back" if self.note["modelName"] == "Basic" else "Image"]["value"]
            if self.broken_display and "updateNoteFields" in self.calls:
                display = "<p>Missing image</p>"
            for card in result.result:
                card.update(question=question, answer=display)
        return result


class ImageRepairTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name).resolve()
        self.path = self.root / "replacement.jpg"
        self.path.write_bytes((FIXTURE.parent / "japanese-station-signs.jpg").read_bytes())
        self.state = ImageState()
        self.client = AnkiConnector(session=self.state)
        self.request = {"note_id": 12, "field": "Image", "old_filename": "old.png",
                        "image_path": str(self.path), "image_sha256": hashlib.sha256(self.path.read_bytes()).hexdigest(),
                        "confirmed": False}

    def run_request(self) -> dict[str, Any]:
        return repair_image(self.request, anki=self.client, media_root=self.root)

    def prepare(self) -> dict[str, Any]:
        result = self.run_request()
        self.request.update(confirmed=True, expected_state=result["expected_state"])
        return result

    def test_preview_is_readonly_and_preserves_surrounding_html(self) -> None:
        result = self.run_request()
        expected = self.state.image_html.replace('src="old.png"', f'src="{result["filename"]}"')
        self.assertEqual(result["changes"], {"Image": expected})
        self.assertEqual(result["recovery"]["restore_filename"], "old.png")
        self.assertNotIn("storeMediaFile", self.state.calls)
        self.assertNotIn("updateNoteFields", self.state.calls)

    def test_journey_discovers_note_and_image_from_card_then_applies_explicit_target(self) -> None:
        self.request = {"card_id": 21, "confirmed": False}
        discovery = self.run_request()
        self.assertEqual(discovery["note_id"], 12)
        self.assertEqual(discovery["candidates"], [{"field": "Image", "old_filename": "old.png"}])
        self.request.update(image_path=str(self.path), image_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        preview = self.run_request()
        self.request = {**preview["apply_request"], "confirmed": True}
        self.assertNotIn("card_id", self.request)
        self.assertTrue(self.run_request()["verified"])

    def test_preserves_non_lf_separators_before_image(self) -> None:
        for separator in ("\r", "\v", "\u2028"):
            with self.subTest(separator=repr(separator)):
                original = f'A{separator}B\n<img src="old.png">'
                self.state.note["fields"]["Image"]["value"] = original
                preview = self.run_request()
                expected = f'A{separator}B\n<img src="{preview["filename"]}">'
                self.assertEqual(preview["changes"]["Image"], expected)

    def test_src_inside_another_attribute_is_never_a_replacement_target(self) -> None:
        for source in ('<img alt=\'src="old.png"\' src=old.png>',
                       '<img alt=\'src="old.png"\' src=other.png>'):
            with self.subTest(source=source):
                self.state.note["fields"]["Image"]["value"] = source
                with self.assertRaises(ValueError):
                    self.run_request()
                self.assertNotIn("updateNoteFields", self.state.calls)

    def test_quoted_src_replacement_preserves_attribute_values_containing_src(self) -> None:
        source = '<img alt=\'src="old.png"\' src="old.png">'
        self.state.note["fields"]["Image"]["value"] = source
        preview = self.run_request()
        self.assertEqual(preview["changes"]["Image"],
                         f'<img alt=\'src="old.png"\' src="{preview["filename"]}">')

    def test_ambiguous_discovery_returns_candidates_without_apply_token(self) -> None:
        self.state.note["fields"]["Image"]["value"] += '<img src="other.png">'
        self.request = {"card_id": 21, "confirmed": False}
        result = self.run_request()
        self.assertTrue(result["selection_required"])
        self.assertEqual(len(result["candidates"]), 2)
        self.assertNotIn("expected_state", result)
        self.assertNotIn("updateNoteFields", self.state.calls)

    def test_apply_preserves_identity_history_fields_and_all_original_media(self) -> None:
        before_cards = copy.deepcopy(self.state.cards)
        before_reviews = copy.deepcopy(self.state.reviews)
        before_fields = copy.deepcopy(self.state.note["fields"])
        before_media = copy.deepcopy(self.state.media)
        self.prepare()
        result = self.run_request()
        self.assertTrue(result["verified"])
        self.assertEqual(self.state.cards, before_cards)
        self.assertEqual(self.state.reviews, before_reviews)
        for field, value in before_fields.items():
            if field != "Image": self.assertEqual(self.state.note["fields"][field], value)
        for filename, data in before_media.items(): self.assertEqual(self.state.media[filename], data)
        self.assertEqual(self.state.media[result["filename"]], self.path.read_bytes())
        self.assertIn(result["filename"], result["rendered_after"]["21"]["answer"])
        self.assertEqual(self.state.calls.count("updateNoteFields"), 1)

    def test_basic_mixed_field_and_restore_use_same_guarded_operation(self) -> None:
        self.state = ImageState(basic=True)
        self.client = AnkiConnector(session=self.state)
        self.request["field"] = "Back"
        original = copy.deepcopy(self.state.note)
        preview = self.prepare()
        self.run_request()
        uploads = self.state.calls.count("storeMediaFile")
        self.request = {**preview["recovery"], "confirmed": False}
        self.prepare()
        result = self.run_request()
        self.assertTrue(result["verified"])
        self.assertEqual(self.state.note, original)
        self.assertEqual(self.state.calls.count("storeMediaFile"), uploads)

    def test_previous_image_must_be_recoverable_before_preview_or_upload(self) -> None:
        invalid_images = {
            "gif": base64.b64decode("R0lGODlhAQABAIAAAAAAAP///ywAAAAAAQABAAACAUwAOw=="),
            "oversized": b"\x89PNG\r\n\x1a\n" + b"\0" * MAX_IMAGE_BYTES,
            "corrupt": b"\x89PNG\r\n\x1a\nnot-an-image",
        }
        for kind, data in invalid_images.items():
            with self.subTest(kind=kind):
                self.state.media["old.png"] = data
                original = copy.deepcopy(self.state.note)
                with self.assertRaises(ValueError):
                    self.run_request()
                self.assertEqual(self.state.note, original)
                self.assertEqual(self.state.media["old.png"], data)
                self.assertNotIn("storeMediaFile", self.state.calls)
                self.assertNotIn("updateNoteFields", self.state.calls)

    def test_replacement_already_referenced_in_note_is_rejected_before_mutation(self) -> None:
        for field in ("Back", "Front"):
            with self.subTest(field=field):
                self.state = ImageState(basic=True)
                self.client = AnkiConnector(session=self.state)
                self.request["field"] = "Back"
                preview = self.run_request()
                filename = preview["filename"]
                self.state.media[filename] = self.path.read_bytes()
                self.state.note["fields"][field]["value"] += f'<img src="{filename}">'
                original = copy.deepcopy(self.state.note)
                with self.assertRaises(ValueError):
                    self.run_request()
                self.assertEqual(self.state.note, original)
                self.assertEqual(self.state.media[filename], self.path.read_bytes())
                self.assertNotIn("storeMediaFile", self.state.calls)
                self.assertNotIn("updateNoteFields", self.state.calls)

    def test_restoration_percent_filename_resolves_to_preserved_media(self) -> None:
        original_filename = "100%25.png"
        original_html = '<img src="100%2525.png">'
        self.state.note["fields"]["Image"]["value"] = original_html
        self.state.media[original_filename] = self.state.media.pop("old.png")
        self.request["old_filename"] = original_filename
        preview = self.prepare()
        self.run_request()
        self.request = {**preview["recovery"], "confirmed": False}
        self.prepare()
        result = self.run_request()
        self.assertTrue(result["verified"])
        restored_html = self.state.note["fields"]["Image"]["value"]
        self.assertEqual(restored_html, original_html)
        restored_src = restored_html.split('src="', 1)[1].split('"', 1)[0]
        self.assertEqual(unquote(restored_src), original_filename)
        self.assertEqual(self.state.media[unquote(restored_src)], FIXTURE.read_bytes())

    def test_basic_front_replacement_and_recovery_preserve_answer(self) -> None:
        self.state = ImageState(basic=True)
        self.client = AnkiConnector(session=self.state)
        original_image = self.path.read_bytes()
        self.state.media["old.jpg"] = original_image
        front = '<div>Pergunta <img src="old.jpg"> contexto.</div>'
        back = '<p>Resposta preservada.</p>[sound:old.mp3]'
        self.state.note["fields"] = {"Front": {"value": front}, "Back": {"value": back}}
        self.path = self.root / "replacement.png"
        self.path.write_bytes(FIXTURE.read_bytes())
        self.request.update(field="Front", old_filename="old.jpg", image_path=str(self.path),
                            image_sha256=hashlib.sha256(self.path.read_bytes()).hexdigest())
        original = copy.deepcopy(self.state.note)
        preview = self.prepare()
        self.assertEqual(preview["rendered_before"]["21"], {"question": front, "answer": back})
        result = self.run_request()
        self.assertTrue(result["verified"])
        self.assertEqual(result["rendered_after"]["21"],
                         {"question": front.replace("old.jpg", result["filename"]), "answer": back})
        self.request = {**preview["recovery"], "confirmed": False}
        self.prepare()
        restored = self.run_request()
        self.assertTrue(restored["verified"])
        self.assertEqual(restored["rendered_after"]["21"], {"question": front, "answer": back})
        self.assertEqual(self.state.note, original)
        self.assertEqual(self.state.media["old.jpg"], original_image)

    def test_conflict_in_note_schedule_history_template_or_media_blocks_writes(self) -> None:
        mutations = [lambda: self.state.note["tags"].append("edited"),
                     lambda: self.state.cards[0].update(due=99),
                     lambda: self.state.reviews["21"].append({"id": 90}),
                     lambda: setattr(self.state, "css", ".card {display:none}"),
                     lambda: self.state.media.update({"old.png": b"modified"})]
        for mutate in mutations:
            with self.subTest(mutation=mutate):
                self.setUp()
                self.prepare()
                mutate()
                with self.assertRaises(ValueError): self.run_request()
                self.assertNotIn("storeMediaFile", self.state.calls)

    def test_concurrent_edit_during_upload_is_not_overwritten(self) -> None:
        for attr in ("change_after_store", "change_old_media"):
            with self.subTest(attr=attr):
                self.setUp()
                self.prepare()
                setattr(self.state, attr, True)
                with self.assertRaises(AnkiConnectError) as ctx: self.run_request()
                self.assertTrue(ctx.exception.outcome_uncertain)
                self.assertNotIn("updateNoteFields", self.state.calls)

    def test_failure_or_broken_display_is_uncertain_and_never_retried(self) -> None:
        for attr, value in (("fail", "updateNoteFields"), ("broken_display", True), ("corrupt_media", True)):
            with self.subTest(attr=attr):
                self.setUp()
                self.prepare()
                setattr(self.state, attr, value)
                with self.assertRaises(AnkiConnectError) as ctx: self.run_request()
                self.assertTrue(ctx.exception.outcome_uncertain)
                self.assertLessEqual(self.state.calls.count("updateNoteFields"), 1)
                self.assertEqual(self.state.media["old.png"], FIXTURE.read_bytes())

    def test_rejects_ambiguous_image_and_unsupported_model(self) -> None:
        self.state.note["fields"]["Image"]["value"] += '<img src="old.png">'
        with self.assertRaises(ValueError): self.run_request()
        self.state.note["modelName"] = "Unknown"
        with self.assertRaises(ValueError): self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)

    def test_rejects_bad_hash_corrupt_image_and_path_escape(self) -> None:
        self.request["image_sha256"] = "0" * 64
        with self.assertRaises(ValueError): self.run_request()
        self.path.write_bytes(b"\xff\xd8\xffbroken\xff\xd9")
        self.request["image_sha256"] = hashlib.sha256(self.path.read_bytes()).hexdigest()
        with self.assertRaises(ValueError): self.run_request()
        self.request["image_path"] = str(FIXTURE.resolve())
        with self.assertRaises(ValueError): self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)

    def test_collision_never_overwrites_and_identical_media_is_reused(self) -> None:
        preview = self.prepare()
        self.state.media[preview["filename"]] = b"collision"
        with self.assertRaises(ValueError): self.run_request()
        self.assertNotIn("storeMediaFile", self.state.calls)
        self.state.media[preview["filename"]] = self.path.read_bytes()
        self.assertTrue(self.run_request()["verified"])
        self.assertNotIn("storeMediaFile", self.state.calls)
