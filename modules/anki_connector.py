"""Minimal AnkiConnect client for new V2 notes only."""

from __future__ import annotations

import base64
import re
from typing import Any, Iterable

import requests

from .profiles import ENGLISH_VOCABULARY, SPANISH_TRAVEL, Profile


ITEM_ID_PATTERN = re.compile(r"[0-9a-f]{64}\Z")
MEDIA_FILENAME_PATTERN = re.compile(
    r"aa2_[0-9a-f]{64}_(?:image\.(?:jpg|png)|main\.mp3)\Z"
)
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
                css=profile.css,
                isCloze=False,
                cardTemplates=list(profile.card_templates),
            )
            return

        fields = self._invoke("modelFieldNames", modelName=profile.note_type)
        templates = self._invoke("modelTemplates", modelName=profile.note_type)
        if (
            fields != list(profile.fields)
            or templates != profile.templates
            or tuple(templates) != tuple(profile.templates)
        ):
            raise AnkiConnectError(
                "model_contract",
                f"O note type existente diverge do contrato local: {profile.note_type}",
            )
        styling = self._invoke("modelStyling", modelName=profile.note_type)
        if styling != {"css": profile.css}:
            raise AnkiConnectError(
                "model_contract",
                f"O note type existente diverge do contrato local: {profile.note_type}",
            )

    def ensure_media_absent(self, filenames: Iterable[str]) -> None:
        """Reject every predictable V2 media collision before provider calls."""
        names = tuple(filenames)
        if not names or len(set(names)) != len(names):
            raise AnkiConnectError("retrieveMediaFile", "Lista de m\u00eddia V2 inv\u00e1lida")
        for filename in names:
            if not MEDIA_FILENAME_PATTERN.fullmatch(filename):
                raise AnkiConnectError("retrieveMediaFile", f"Filename V2 inv\u00e1lido: {filename}")
            existing = self._invoke("retrieveMediaFile", filename=filename)
            if existing is False:
                continue
            if not isinstance(existing, str):
                raise AnkiConnectError(
                    "retrieveMediaFile",
                    "O AnkiConnect devolveu um resultado de m\u00eddia inv\u00e1lido",
                )
            raise AnkiConnectError(
                "retrieveMediaFile",
                f"M\u00eddia V2 j\u00e1 existe sem note correspondente: {filename}",
            )

    def store_media_file(self, filename: str, data: bytes) -> str:
        """Upload one validated V2 media payload after collision preflight."""
        if not MEDIA_FILENAME_PATTERN.fullmatch(filename):
            raise AnkiConnectError("storeMediaFile", f"Filename V2 inv\u00e1lido: {filename}")
        if not isinstance(data, bytes) or not data:
            raise AnkiConnectError("storeMediaFile", "Bytes de m\u00eddia V2 inv\u00e1lidos")
        stored = self._invoke(
            "storeMediaFile",
            filename=filename,
            data=base64.b64encode(data).decode("ascii"),
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
