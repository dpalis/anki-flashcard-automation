"""Minimal AnkiConnect client for new V2 notes only."""

from __future__ import annotations

import base64
import re
from pathlib import Path
from typing import Any

import requests

from .profiles import ENGLISH_VOCABULARY, SPANISH_TRAVEL, Profile


ITEM_ID_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
V2_PROFILES = (ENGLISH_VOCABULARY, SPANISH_TRAVEL)
MUTATING_ACTIONS = frozenset({"createModel", "storeMediaFile", "addNote"})


class AnkiConnectError(Exception):
    def __init__(self, action: str, message: str, outcome_uncertain: bool = False) -> None:
        super().__init__(message)
        self.action = action
        self.outcome_uncertain = outcome_uncertain


class AnkiConnector:
    def __init__(
        self,
        anki_url: str = "http://localhost:8765",
        *,
        session: Any | None = None,
        timeout: float = 10,
    ) -> None:
        self.anki_url = anki_url
        self.session = session or requests.Session()
        self.timeout = timeout

    def _invoke(self, action: str, **params: Any) -> Any:
        uncertain = action in MUTATING_ACTIONS
        payload = {"action": action, "version": 6, "params": params}
        try:
            response = self.session.post(self.anki_url, json=payload, timeout=self.timeout)
            response.raise_for_status()
            envelope = response.json()
        except (requests.RequestException, ValueError) as exc:
            raise AnkiConnectError(
                action,
                f"Falha de transporte ou resposta inv\u00e1lida em {action}: {exc}",
                outcome_uncertain=uncertain,
            ) from exc

        if not isinstance(envelope, dict) or set(envelope) != {"result", "error"}:
            raise AnkiConnectError(
                action,
                f"Envelope inv\u00e1lido do AnkiConnect em {action}",
                outcome_uncertain=uncertain,
            )
        if envelope["error"] is not None:
            raise AnkiConnectError(action, str(envelope["error"]), outcome_uncertain=False)
        return envelope["result"]

    def find_exact_items(self, item_id: str) -> list[str]:
        """Return notes whose stored ItemId exactly matches the requested ID.

        Args:
            item_id: Deterministic hexadecimal V2 item identifier.

        Returns:
            Original inputs from matching notes.

        Raises:
            AnkiConnectError: If the request or returned identity fields are invalid.
        """
        if not ITEM_ID_PATTERN.fullmatch(item_id):
            raise AnkiConnectError("findNotes", "ItemId inv\u00e1lido")
        note_ids = self._invoke("findNotes", query=f"ItemId:{item_id}")
        if not isinstance(note_ids, list):
            raise AnkiConnectError("findNotes", "findNotes n\u00e3o devolveu uma lista")
        if not note_ids:
            return []

        notes = self._invoke("notesInfo", notes=note_ids)
        if not isinstance(notes, list):
            raise AnkiConnectError("notesInfo", "notesInfo n\u00e3o devolveu uma lista")

        exact = []
        for note in notes:
            try:
                fields = note["fields"]
                stored_id = fields["ItemId"]["value"]
                stored_input = fields["Input"]["value"]
            except (KeyError, TypeError) as exc:
                raise AnkiConnectError("notesInfo", "Note V2 sem fields de identidade v\u00e1lidos") from exc
            if stored_id == item_id:
                exact.append(stored_input)
        return exact

    def ensure_ready(self, profile: Profile, deck_name: str) -> None:
        """Validate the deck and create-or-validate the fixed V2 note type.

        Args:
            profile: One of the two fixed V2 profiles.
            deck_name: Existing disposable QA deck.

        Raises:
            AnkiConnectError: If the deck is missing or the note type contract drifts.
        """
        self._require_v2_profile(profile)
        decks = self._invoke("deckNames")
        if not isinstance(decks, list) or deck_name not in decks:
            raise AnkiConnectError("deckNames", f"O deck configurado n\u00e3o existe: {deck_name}")

        models = self._invoke("modelNames")
        if not isinstance(models, list):
            raise AnkiConnectError("modelNames", "modelNames n\u00e3o devolveu uma lista")
        if profile.note_type not in models:
            self._invoke(
                "createModel",
                modelName=profile.note_type,
                inOrderFields=list(profile.fields),
                css="",
                isCloze=False,
                cardTemplates=list(profile.card_templates),
            )
            return

        fields = self._invoke("modelFieldNames", modelName=profile.note_type)
        templates = self._invoke("modelTemplates", modelName=profile.note_type)
        if fields != list(profile.fields) or templates != profile.templates:
            raise AnkiConnectError(
                "model_contract",
                f"O note type existente diverge do contrato local: {profile.note_type}",
            )

    def prepare_qa_image(self, item_id: str, image_path: str | Path) -> tuple[str, str]:
        """Validate the QA fixture and reject its deterministic filename if occupied.

        Args:
            item_id: Deterministic hexadecimal V2 item identifier.
            image_path: Local PNG or JPEG fixture path.

        Returns:
            The deterministic filename and base64-encoded fixture bytes.

        Raises:
            AnkiConnectError: If the fixture is invalid or the filename is occupied.
        """
        if not ITEM_ID_PATTERN.fullmatch(item_id):
            raise AnkiConnectError("retrieveMediaFile", "ItemId inv\u00e1lido")
        path = Path(image_path)
        try:
            data = path.read_bytes()
        except OSError as exc:
            raise AnkiConnectError(
                "retrieveMediaFile",
                f"N\u00e3o foi poss\u00edvel ler a fixture: {path}",
            ) from exc

        suffix = path.suffix.lower()
        if suffix == ".png" and data.startswith(b"\x89PNG\r\n\x1a\n") and len(data) > 8:
            extension = "png"
        elif suffix in {".jpg", ".jpeg"} and data.startswith(b"\xff\xd8") and data.endswith(b"\xff\xd9"):
            extension = "jpg"
        else:
            raise AnkiConnectError(
                "retrieveMediaFile",
                "A fixture de QA n\u00e3o \u00e9 PNG ou JPEG v\u00e1lido",
            )

        filename = f"aa2_{item_id}_image.{extension}"
        existing = self._invoke("retrieveMediaFile", filename=filename)
        if existing is not False:
            if not isinstance(existing, str):
                raise AnkiConnectError(
                    "retrieveMediaFile",
                    "O AnkiConnect devolveu um resultado de m\u00eddia inv\u00e1lido",
                )
            raise AnkiConnectError(
                "retrieveMediaFile",
                f"M\u00eddia V2 j\u00e1 existe sem note correspondente: {filename}",
            )
        return filename, base64.b64encode(data).decode("ascii")

    def store_qa_image(self, filename: str, encoded_data: str) -> str:
        """Upload a QA image that already passed the read-only preflight.

        Args:
            filename: Deterministic V2 media filename.
            encoded_data: Base64-encoded fixture bytes from prepare_qa_image.

        Returns:
            The filename confirmed by AnkiConnect.

        Raises:
            AnkiConnectError: If AnkiConnect does not confirm the upload.
        """
        stored = self._invoke(
            "storeMediaFile",
            filename=filename,
            data=encoded_data,
        )
        if stored != filename:
            raise AnkiConnectError(
                "storeMediaFile",
                "O AnkiConnect n\u00e3o confirmou o filename enviado",
                outcome_uncertain=True,
            )
        return filename

    def add_note(
        self,
        profile: Profile,
        deck_name: str,
        fields: dict[str, str],
    ) -> int:
        """Create one V2 note, which yields the profile's two card templates.

        Args:
            profile: One of the two fixed V2 profiles.
            deck_name: Existing target deck.
            fields: Ordered field mapping for the profile note type.

        Returns:
            Positive Anki note identifier.

        Raises:
            AnkiConnectError: If the payload or AnkiConnect result is invalid.
        """
        self._require_v2_profile(profile)
        if tuple(fields) != profile.fields:
            raise AnkiConnectError("addNote", "Fields n\u00e3o correspondem ao note type V2")
        note = {
            "deckName": deck_name,
            "modelName": profile.note_type,
            "fields": fields,
            "tags": list(profile.tags),
            "options": {"allowDuplicate": False},
        }
        note_id = self._invoke("addNote", note=note)
        if type(note_id) is not int or note_id <= 0:
            raise AnkiConnectError(
                "addNote",
                "O AnkiConnect n\u00e3o devolveu um note_id v\u00e1lido",
                outcome_uncertain=True,
            )
        return note_id

    @staticmethod
    def _require_v2_profile(profile: Profile) -> None:
        if profile not in V2_PROFILES:
            raise AnkiConnectError("profile", "Somente note types V2 podem ser modificados")
