"""Shared persistence guards for scoped repairs of existing note media."""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import stat
from typing import Any, Callable

from .anki_connector import AnkiConnectError, AnkiConnector

MEDIA_ROOT = Path("/Users/dpalis/Coding/Galadriel/outputs")


def digest(value: Any) -> str:
    """Hash a complete preview deterministically."""
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def read_file(path_text: str, expected_hash: str, root: Path, limit: int) -> bytes:
    """Read one approved regular file under outputs without following symlinks."""
    path = Path(path_text)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("Mídia deve ser arquivo regular absoluto, sem symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or resolved != path:
        raise ValueError("Mídia deve estar sob outputs, sem symlinks ou atalhos")
    with os.fdopen(os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= limit:
            raise ValueError(f"Mídia deve ser arquivo regular de até {limit} bytes")
        data = handle.read(limit + 1)
    if not 0 < len(data) <= limit or hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("O hash da mídia diverge do arquivo aprovado")
    return data


def note_snapshot(anki: AnkiConnector, note_id: int) -> dict:
    """Read identity, fields and full study state of every existing note card."""
    notes = anki._invoke("notesInfo", notes=[note_id])
    if not isinstance(notes, list) or len(notes) != 1:
        raise ValueError("Note não encontrada")
    note = notes[0]
    fields = {k: v["value"] for k, v in note["fields"].items()}
    ids = note["cards"]
    if (note["noteId"] != note_id or not ids or len(set(ids)) != len(ids)
            or any(type(i) is not int or i <= 0 for i in ids)
            or any(not isinstance(v, str) for v in fields.values())):
        raise ValueError("Identidade ou campos da note inválidos")
    cards = anki._invoke("cardsInfo", cards=ids)
    if (not isinstance(cards, list) or len(cards) != len(ids)
            or {c["cardId"] for c in cards} != set(ids)
            or any(c["note"] != note_id for c in cards)):
        raise ValueError("Cards fora da note")
    excluded = {"fields", "question", "answer", "nextReviews", "mod"}
    study = sorted(({k: v for k, v in c.items() if k not in excluded} for c in cards), key=lambda c: c["cardId"])
    reviews = anki._invoke("getReviewsOfCards", cards=ids)
    if not isinstance(reviews, dict) or set(reviews) != {str(i) for i in ids}:
        raise ValueError("Histórico dos cards não pôde ser conferido")
    return {"note_id": note_id, "model": note["modelName"], "fields": fields,
            "tags": sorted(note["tags"]), "cards": study, "reviews": reviews}


def media_bytes(anki: AnkiConnector, filename: str) -> bytes | None:
    """Retrieve stored bytes independently of an upload response."""
    raw = anki._invoke("retrieveMediaFile", filename=filename)
    if raw is False:
        return None
    if not isinstance(raw, str):
        raise ValueError("Resposta de mídia inválida")
    return base64.b64decode(raw, validate=True)


def apply_media(anki: AnkiConnector, *, before: dict, changes: dict, filename: str,
                data: bytes, snapshot: Callable[[], dict],
                verify_display: Callable[[], None] = lambda: None) -> dict:
    """Store without overwrite, check conflicts, update once and verify independently."""
    existing = media_bytes(anki, filename)
    if existing is not None and existing != data:
        raise ValueError("Colisão de mídia; arquivo existente não será sobrescrito")
    mutated = False
    try:
        if existing is None:
            mutated = True
            stored = anki._invoke("storeMediaFile", filename=filename, data=base64.b64encode(data).decode("ascii"))
            if stored != filename:
                raise ValueError("Nome de mídia persistido diverge do pedido")
        if media_bytes(anki, filename) != data:
            raise ValueError("Bytes de mídia persistidos divergem do arquivo aprovado")
        if snapshot() != before:
            raise ValueError("A note, mídia ou histórico mudou durante o envio de mídia")
        mutated = True
        anki._invoke("updateNoteFields", note={"id": before["note_id"], "fields": changes})
        after = snapshot()
        expected_after = {**before, "fields": {**before["fields"], **changes}}
        if after != expected_after or media_bytes(anki, filename) != data:
            raise ValueError("Releitura diverge do conteúdo, mídia ou histórico esperado")
        verify_display()
    except (AnkiConnectError, ValueError, KeyError, TypeError) as exc:
        if mutated:
            raise AnkiConnectError("repairNote", f"Reparo não confirmado: {exc}. Conferir antes de repetir; mídia antiga preservada.", outcome_uncertain=True) from exc
        raise
    return after
