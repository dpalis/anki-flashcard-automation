"""Replace reviewed V2 audio without recreating notes or touching study history.

This module verifies persistence, not pronunciation. Source and transcript are
provenance supplied by the reviewer; they are never a claim of phonetic approval.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
from pathlib import Path
import re
import stat
from typing import Any
from urllib.parse import urlsplit

from .anki_connector import AnkiConnectError, AnkiConnector
from .profiles import get_profile

MEDIA_ROOT = Path("/Users/dpalis/Coding/Galadriel/outputs")
MAX_AUDIO_BYTES = 2 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _digest(value: Any) -> str:
    return hashlib.sha256(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _audio(path_text: str, expected_hash: str, root: Path) -> tuple[bytes, str]:
    path = Path(path_text)
    if not path.is_absolute() or path.is_symlink():
        raise ValueError("Áudio deve ser arquivo regular absoluto, sem symlink")
    resolved = path.resolve(strict=True)
    if not resolved.is_relative_to(root.resolve()) or resolved != path:
        raise ValueError("Áudio deve estar sob outputs, sem symlinks ou atalhos")
    with os.fdopen(os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), "rb") as handle:
        info = os.fstat(handle.fileno())
        if not stat.S_ISREG(info.st_mode) or not 0 < info.st_size <= MAX_AUDIO_BYTES:
            raise ValueError("Áudio deve ser arquivo regular de até 2 MiB")
        data = handle.read(MAX_AUDIO_BYTES + 1)
    if hashlib.sha256(data).hexdigest() != expected_hash:
        raise ValueError("O hash do áudio diverge do arquivo aprovado")
    suffix = path.suffix.lower()
    if suffix == ".wav" and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data, "wav"
    if suffix == ".mp3" and (data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 255 and data[1] & 224 == 224)):
        return data, "mp3"
    raise ValueError("Arquivo não corresponde a MP3 ou WAV")


def _snapshot(anki: AnkiConnector, note_id: int, profile_id: str, deck: str) -> dict:
    profile = get_profile(profile_id)
    notes = anki._invoke("notesInfo", notes=[note_id])
    if not isinstance(notes, list) or len(notes) != 1:
        raise ValueError("Note não encontrada")
    note = notes[0]
    fields = {k: v["value"] for k, v in note["fields"].items()}
    ids = note["cards"]
    if (note["noteId"] != note_id or note["modelName"] != profile.note_type
            or set(fields) != set(profile.fields) or not _HEX.fullmatch(fields["ItemId"])
            or len(ids) != 2 or len(set(ids)) != 2
            or any(type(i) is not int or i <= 0 for i in ids)):
        raise ValueError("A note não corresponde ao perfil V2 e seus dois cards")
    cards = anki._invoke("cardsInfo", cards=ids)
    if (not isinstance(cards, list) or len(cards) != 2 or {c["cardId"] for c in cards} != set(ids)
            or any(c["note"] != note_id or c["deckName"] != deck for c in cards)):
        raise ValueError("Cards fora da note ou do deck configurado")
    # Rendered text changes with the note. nextReviews is time-dependent; mod is
    # bookkeeping. Scheduling fields and identities remain in this comparison.
    excluded = {"fields", "question", "answer", "nextReviews", "mod"}
    study = sorted(({k:v for k,v in c.items() if k not in excluded} for c in cards), key=lambda c:c["cardId"])
    reviews = anki._invoke("getReviewsOfCards", cards=ids)
    if not isinstance(reviews, dict) or set(reviews) != {str(i) for i in ids}:
        raise ValueError("Histórico dos dois cards não pôde ser conferido")
    return {"note_id": note_id, "model": profile.note_type, "fields": fields,
            "tags": sorted(note["tags"]), "cards": study, "reviews": reviews}


def _media(anki: AnkiConnector, filename: str) -> bytes | None:
    raw = anki._invoke("retrieveMediaFile", filename=filename)
    if raw is False:
        return None
    if not isinstance(raw, str):
        raise ValueError("Resposta de mídia inválida")
    return base64.b64decode(raw, validate=True)


def repair_note(request: dict, *, anki: AnkiConnector, deck_name: str,
                media_root: Path = MEDIA_ROOT) -> dict:
    """Preview or apply one approved audio replacement, with conflict checks.

    ``confirmed`` selects apply; it is not evidence of user or phonetic approval.
    The caller owns those approvals. Apply requires the state digest from preview.
    """
    allowed = {"profile", "note_id", "audio_path", "audio_sha256", "source_url", "transcript", "fields", "confirmed", "expected_state"}
    required = allowed - {"fields", "expected_state"}
    if not isinstance(request, dict) or set(request) - allowed or required - set(request):
        raise ValueError("Campos inválidos no pedido de reparo")
    for key in ("profile", "audio_path", "audio_sha256", "source_url", "transcript"):
        if not isinstance(request[key], str) or not request[key].strip():
            raise ValueError(f"Campo textual obrigatório: {key}")
    if type(request["note_id"]) is not int or request["note_id"] <= 0 or type(request["confirmed"]) is not bool:
        raise ValueError("note_id ou confirmed inválido")
    if not _HEX.fullmatch(request["audio_sha256"]):
        raise ValueError("hash de áudio inválido")
    url = urlsplit(request["source_url"])
    if url.scheme != "https" or not url.netloc:
        raise ValueError("Fonte deve ser uma URL HTTPS identificada")
    patches = request.get("fields", {})
    if (not isinstance(patches, dict) or set(patches) - {"Target", "ContentHtml"}
            or any(not isinstance(v, str) or not v.strip() or len(v) > 16000 for v in patches.values())):
        raise ValueError("Somente Target e ContentHtml podem acompanhar o áudio")
    data, extension = _audio(request["audio_path"], request["audio_sha256"], media_root)
    before = _snapshot(anki, request["note_id"], request["profile"], deck_name)
    filename = f"aa2_{before['fields']['ItemId']}_audio_{request['audio_sha256']}.{extension}"
    changes = {**patches, "MainAudio": f"[sound:{filename}]"}
    evidence = {"source_url": request["source_url"], "transcript": request["transcript"], "audio_sha256": request["audio_sha256"]}
    expected = _digest({"before": before, "changes": changes, **evidence})
    preview = {"status": "preview", "note_id": request["note_id"], "before": before,
               "changes": changes, "filename": filename, "expected_state": expected, **evidence}
    if not request["confirmed"]:
        return preview
    if request.get("expected_state") != expected:
        raise ValueError("O estado ou o pedido mudou desde a prévia; nenhuma escrita executada")
    existing = _media(anki, filename)
    if existing is not None and existing != data:
        raise ValueError("Colisão de mídia; arquivo existente não será sobrescrito")
    mutated = False
    try:
        if existing is None:
            mutated = True
            stored = anki._invoke("storeMediaFile", filename=filename, data=base64.b64encode(data).decode("ascii"))
            if stored != filename:
                raise ValueError("Nome de mídia persistido diverge do pedido")
        if _media(anki, filename) != data:
            raise ValueError("Bytes de mídia persistidos divergem do arquivo aprovado")
        if _snapshot(anki, request["note_id"], request["profile"], deck_name) != before:
            raise ValueError("A note ou o histórico mudou durante o envio de mídia")
        mutated = True
        anki._invoke("updateNoteFields", note={"id": request["note_id"], "fields": changes})
        after = _snapshot(anki, request["note_id"], request["profile"], deck_name)
        expected_after = {**before, "fields": {**before["fields"], **changes}}
        if after != expected_after or _media(anki, filename) != data:
            raise ValueError("Releitura diverge do conteúdo, mídia ou histórico esperado")
    except (AnkiConnectError, ValueError, KeyError, TypeError) as exc:
        if mutated:
            raise AnkiConnectError("repairNote", f"Reparo não confirmado: {exc}. Conferir antes de repetir; mídia antiga preservada.", outcome_uncertain=True) from exc
        raise
    return {**preview, "status": "ok", "verified": True, "after": after}


def run_repair_request(request: dict, settings: dict) -> dict:
    """Run the repair CLI contract with no generation credentials or provider calls."""
    try:
        profile_id = request["profile"]
        get_profile(profile_id)
        deck = settings["profiles"][profile_id]["deck_name"]
        if not isinstance(deck, str) or not deck:
            raise ValueError("Deck não configurado")
        return repair_note(request, anki=AnkiConnector(settings.get("anki_url", "http://127.0.0.1:8765")), deck_name=deck)
    except (ValueError, KeyError, TypeError, OSError, AnkiConnectError) as exc:
        return {"status": "error", "error": {"message": str(exc), "outcome_uncertain": isinstance(exc, AnkiConnectError) and exc.outcome_uncertain}}
