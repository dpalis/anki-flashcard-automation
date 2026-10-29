"""Replace reviewed V2 audio without recreating notes or touching study history.

This module verifies persistence, not pronunciation. Source and transcript are
provenance supplied by the reviewer; they are never a claim of phonetic approval.
"""
from __future__ import annotations

from pathlib import Path
import re
from urllib.parse import urlsplit

from .anki_connector import AnkiConnectError, AnkiConnector
from .profiles import get_profile
from .media_repair import MEDIA_ROOT, apply_media, digest as _digest, note_snapshot, read_file

MAX_AUDIO_BYTES = 2 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")


def _audio(path_text: str, expected_hash: str, root: Path) -> tuple[bytes, str]:
    path = Path(path_text)
    data = read_file(path_text, expected_hash, root, MAX_AUDIO_BYTES)
    suffix = path.suffix.lower()
    if suffix == ".wav" and data[:4] == b"RIFF" and data[8:12] == b"WAVE":
        return data, "wav"
    if suffix == ".mp3" and (data[:3] == b"ID3" or (len(data) >= 2 and data[0] == 255 and data[1] & 224 == 224)):
        return data, "mp3"
    raise ValueError("Arquivo não corresponde a MP3 ou WAV")


def _snapshot(anki: AnkiConnector, note_id: int, profile_id: str, deck: str) -> dict:
    profile = get_profile(profile_id)
    state = note_snapshot(anki, note_id)
    fields = state["fields"]
    if (state["model"] != profile.note_type or set(fields) != set(profile.fields)
            or not _HEX.fullmatch(fields["ItemId"]) or len(state["cards"]) != 2):
        raise ValueError("A note não corresponde ao perfil V2 e seus dois cards")
    if any(card["deckName"] != deck for card in state["cards"]):
        raise ValueError("Cards fora da note ou do deck configurado")
    return state


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
    # Anki truncates long media names. Bind both full hashes into one digest so
    # the requested filename survives storage unchanged (78 ASCII bytes).
    media_id = _digest({"item_id": before["fields"]["ItemId"], "audio_sha256": request["audio_sha256"]})
    filename = f"aa2_audio_{media_id}.{extension}"
    changes = {**patches, "MainAudio": f"[sound:{filename}]"}
    evidence = {"source_url": request["source_url"], "transcript": request["transcript"], "audio_sha256": request["audio_sha256"]}
    expected = _digest({"before": before, "changes": changes, **evidence})
    preview = {"status": "preview", "note_id": request["note_id"], "before": before,
               "changes": changes, "filename": filename, "expected_state": expected, **evidence}
    if not request["confirmed"]:
        return preview
    if request.get("expected_state") != expected:
        raise ValueError("O estado ou o pedido mudou desde a prévia; nenhuma escrita executada")
    after = apply_media(anki, before=before, changes=changes, filename=filename, data=data,
                        snapshot=lambda: _snapshot(anki, request["note_id"], request["profile"], deck_name))
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
