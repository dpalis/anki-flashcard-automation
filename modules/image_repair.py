"""Replace one identified local image in a supported existing note, reversibly."""
from __future__ import annotations

import hashlib
import html
from html.parser import HTMLParser
from pathlib import Path
import re
import subprocess
import tempfile
from urllib.parse import quote, unquote

from .anki_connector import AnkiConnectError, AnkiConnector
from .media_repair import MEDIA_ROOT, apply_media, digest, media_bytes, note_snapshot, read_file
from .profiles import LANGUAGE_PROFILES

MAX_IMAGE_BYTES = 5 * 1024 * 1024
_HEX = re.compile(r"[0-9a-f]{64}\Z")
_ATTRIBUTE = re.compile(r'''\s+([^\s/=<>"']+)(?:\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'=<>`]+)))?''')


def _filename(value: str) -> str:
    if (not isinstance(value, str) or not value or value in {".", ".."}
            or any(c in value for c in '/\\:\x00\r\n?#') or len(value.encode()) > 255):
        raise ValueError("Nome de mídia local inválido")
    return value


class _Images(HTMLParser):
    def __init__(self, source: str) -> None:
        super().__init__(convert_charrefs=True)
        self.source = source
        self.images: list[tuple[str, int, int]] = []
        self.feed(source)

    def handle_starttag(self, tag: str, attrs: list) -> None:
        if tag.lower() != "img":
            return
        raw = self.get_starttag_text()
        if sum(k == "src" for k, _ in attrs) != 1 or any(k == "srcset" for k, _ in attrs):
            raise ValueError("Imagem exige um src local entre aspas, sem srcset")
        position = len("<img")
        src = None
        while not re.fullmatch(r"\s*/?>", raw[position:]):
            match = _ATTRIBUTE.match(raw, position)
            if match is None:
                raise ValueError("Atributos da imagem não podem ser identificados com segurança")
            if match.group(1).lower() == "src":
                group = 2 if match.group(2) is not None else 3
                if match.group(group) is None or src is not None:
                    raise ValueError("Imagem exige um src local entre aspas, sem srcset")
                src = (match.group(group), match.start(group), match.end(group))
            position = match.end()
        if src is None:
            raise ValueError("Imagem exige um src local entre aspas, sem srcset")
        line, column = self.getpos()
        offset = sum(len(s) + 1 for s in self.source.split("\n")[:line - 1]) + column
        value = unquote(html.unescape(src[0]))
        self.images.append((value, offset + src[1], offset + src[2]))


def _replace(source: str, old: str, new: str, *, single: bool = False) -> str:
    matches = [(start, end) for name, start, end in _Images(source).images if name == old]
    if single and len(matches) != 1:
        raise ValueError("O campo deve conter exatamente uma imagem com o nome identificado")
    for start, end in reversed(matches):
        source = source[:start] + html.escape(quote(new, safe=""), quote=True) + source[end:]
    return source


def _decode_image(data: bytes) -> str:
    if not 0 < len(data) <= MAX_IMAGE_BYTES:
        raise ValueError("Imagem deve ter até 5 MiB")
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        extension = "png"
    elif data.startswith(b"\xff\xd8\xff") and data.endswith(b"\xff\xd9"):
        extension = "jpg"
    else:
        raise ValueError("Imagem deve ser PNG ou JPEG")
    # sips decodifica pixels via ImageIO; a assinatura do arquivo não basta.
    with tempfile.TemporaryDirectory(prefix="anki-image-decode-") as directory:
        source, output = Path(directory) / f"source.{extension}", Path(directory) / "decoded.png"
        source.write_bytes(data)
        try:
            result = subprocess.run(["/usr/bin/sips", "-s", "format", "png", str(source), "--out", str(output)],
                                    capture_output=True, timeout=15, check=False)
        except (OSError, subprocess.TimeoutExpired) as exc:
            raise ValueError("Não foi possível decodificar a imagem localmente") from exc
        if result.returncode != 0 or not output.is_file() or output.stat().st_size == 0:
            raise ValueError("Imagem corrompida ou não decodificável")
    return extension


def _supported(state: dict, field: str) -> None:
    profiles = [p for p in LANGUAGE_PROFILES if p.note_type == state["model"]]
    if profiles:
        if (field != "Image" or set(state["fields"]) != set(profiles[0].fields)
                or not _HEX.fullmatch(state["fields"]["ItemId"]) or len(state["cards"]) != 2):
            raise ValueError("Imagem V2 exige campo Image e o contrato existente de dois cards")
    elif state["model"] == "Basic":
        if field not in {"Front", "Back"} or set(state["fields"]) != {"Front", "Back"}:
            raise ValueError("Basic exige Front/Back existentes")
    else:
        raise ValueError("Modelo sem suporte para troca de imagem: " + state["model"])


def _rendered(anki: AnkiConnector, state: dict) -> dict:
    ids = [card["cardId"] for card in state["cards"]]
    cards = anki._invoke("cardsInfo", cards=ids)
    if not isinstance(cards, list) or len(cards) != len(ids) or {c["cardId"] for c in cards} != set(ids):
        raise ValueError("Render dos cards incompleto")
    result = {}
    for card in cards:
        if any(not isinstance(card.get(side), str) for side in ("question", "answer")):
            raise ValueError("Render da frente/verso indisponível")
        result[str(card["cardId"])] = {side: card[side] for side in ("question", "answer")}
    return result


def repair_image(request: dict, *, anki: AnkiConnector, media_root: Path = MEDIA_ROOT) -> dict:
    """Preview/apply one approved image replacement or restore the preserved image.

    The caller owns approval and visual review. verified covers bytes, note state,
    history and Anki's rendered HTML; it does not claim a screenshot of the app.
    """
    required = {"confirmed"}
    optional = {"note_id", "card_id", "field", "old_filename", "image_sha256", "image_path", "restore_filename", "expected_state"}
    if not isinstance(request, dict) or required - set(request) or set(request) - required - optional:
        raise ValueError("Campos inválidos no pedido de imagem")
    request = dict(request)
    if (type(request["confirmed"]) is not bool or bool(request.get("note_id")) == bool(request.get("card_id"))
            or any(type(request[key]) is not int or request[key] <= 0 for key in ("note_id", "card_id") if key in request)):
        raise ValueError("Informe um note_id ou card_id válido, exclusivamente")
    card_id = request.pop("card_id", None)
    if request["confirmed"] and (card_id is not None or {"field", "old_filename", "image_sha256", "expected_state"} - set(request)):
        raise ValueError("Aplicação exige o alvo canônico explícito e o estado da prévia")
    if card_id is not None:
        cards = anki._invoke("cardsInfo", cards=[card_id])
        if (not isinstance(cards, list) or len(cards) != 1 or cards[0].get("cardId") != card_id
                or type(cards[0].get("note")) is not int or cards[0]["note"] <= 0):
            raise ValueError("Card não encontrado ou note não identificada")
        request["note_id"] = cards[0]["note"]
    initial = note_snapshot(anki, request["note_id"])
    supported_fields = ("Front", "Back") if initial["model"] == "Basic" else ("Image",)
    _supported(initial, request.get("field", supported_fields[0]))
    candidates = [{"field": field, "old_filename": name}
                  for field in supported_fields if request.get("field", field) == field
                  for name, _, _ in _Images(initial["fields"][field]).images
                  if not _url_is_remote(name) and request.get("old_filename", name) == name]
    has_source = bool(request.get("image_path")) or bool(request.get("restore_filename"))
    if bool(request.get("image_path")) and bool(request.get("restore_filename")):
        raise ValueError("Informe image_path ou restore_filename, exclusivamente")
    if has_source and (not isinstance(request.get("image_sha256"), str) or not _HEX.fullmatch(request["image_sha256"])):
        raise ValueError("Hash da imagem obrigatório")
    if not has_source and request.get("image_sha256"):
        raise ValueError("Hash sem imagem candidata")
    if request.get("old_filename") and len(candidates) != 1:
        raise ValueError("A imagem identificada está ausente ou ambígua")
    if len(candidates) != 1 or not has_source:
        if request["confirmed"]:
            raise ValueError("Aplicação exige imagem e seleção únicas")
        return {"status": "preview", "note_id": request["note_id"], "card_id": card_id,
                "model": initial["model"], "candidates": candidates,
                "selection_required": len(candidates) != 1, "replacement_required": not has_source}
    request.update(candidates[0])
    old = _filename(request["old_filename"])
    _supported(initial, request["field"])
    if any(name == old for field, value in initial["fields"].items() if field != request["field"]
           for name, _, _ in _Images(value).images):
        raise ValueError("A mesma imagem aparece em outro campo; selecione uma referência não ambígua")
    names = {old}
    for value in initial["fields"].values():
        names.update(name for name, _, _ in _Images(value).images if not _url_is_remote(name))
        names.update(re.findall(r"\[sound:([^\]]+)\]", value))
    names = {_filename(name) for name in names}

    def snapshot() -> dict:
        state = note_snapshot(anki, request["note_id"])
        _supported(state, request["field"])
        media = {name: media_bytes(anki, name) for name in sorted(names)}
        return {**state, "media_sha256": {name: hashlib.sha256(data).hexdigest() if data is not None else None for name, data in media.items()},
                "templates": anki._invoke("modelTemplates", modelName=state["model"]),
                "styling": anki._invoke("modelStyling", modelName=state["model"])}

    before = snapshot()
    if {key: before[key] for key in initial} != initial:
        raise ValueError("A note mudou durante a leitura")
    previous_data = media_bytes(anki, old)
    if previous_data is None or hashlib.sha256(previous_data).hexdigest() != before["media_sha256"][old]:
        raise ValueError("Imagem anterior indisponível ou alterada; recuperação não garantida")
    _decode_image(previous_data)
    if request.get("image_path"):
        data = read_file(request["image_path"], request["image_sha256"], media_root, MAX_IMAGE_BYTES)
        extension = _decode_image(data)
        filename = f"aa_image_{digest({'note_id': request['note_id'], 'hash': request['image_sha256']})}.{extension}"
    else:
        filename = _filename(request["restore_filename"])
        data = media_bytes(anki, filename)
        if data is None or hashlib.sha256(data).hexdigest() != request["image_sha256"]:
            raise ValueError("Imagem de recuperação ausente ou com hash divergente")
        _decode_image(data)
    if filename == old:
        raise ValueError("A imagem pedida já é a imagem atual; nenhuma escrita necessária")
    if filename in names:
        raise ValueError("A imagem candidata já é referenciada na note; recuperação ficaria ambígua")
    changes = {request["field"]: _replace(before["fields"][request["field"]], old, filename, single=True)}
    rendered_before = _rendered(anki, before)
    rendered_expected = {card: {side: _replace(value, old, filename) for side, value in sides.items()}
                         for card, sides in rendered_before.items()}
    if rendered_before == rendered_expected:
        raise ValueError("Imagem identificada não aparece na frente/verso renderizado pelo Anki")
    expected_state = digest({"before": before, "changes": changes, "image_sha256": request["image_sha256"], "rendered": rendered_before})
    recovery = {"note_id": request["note_id"], "field": request["field"], "old_filename": filename,
                "restore_filename": old, "image_sha256": before["media_sha256"][old]}
    preview = {"status": "preview", "note_id": request["note_id"], "field": request["field"], "old_filename": old,
               "before": before, "changes": changes, "filename": filename, "image_sha256": request["image_sha256"],
               "expected_state": expected_state, "recovery": recovery, "rendered_before": rendered_before}
    if card_id is not None:
        preview["card_id"] = card_id
    preview["apply_request"] = {**{key: value for key, value in request.items() if key not in {"confirmed", "expected_state"}},
                                "expected_state": expected_state}
    if not request["confirmed"]:
        return preview
    if request.get("expected_state") != expected_state:
        raise ValueError("O estado ou o pedido mudou desde a prévia; nenhuma escrita executada")
    rendered_after = {}

    def verify_display() -> None:
        rendered_after.update(_rendered(anki, before))
        if rendered_after != rendered_expected:
            raise ValueError("A imagem ou o restante da frente/verso renderizado diverge do esperado")

    after = apply_media(anki, before=before, changes=changes, filename=filename, data=data,
                        snapshot=snapshot, verify_display=verify_display)
    return {**preview, "status": "ok", "verified": True, "after": after,
            "rendered_reference_verified": True, "display_evidence": "AnkiConnect cardsInfo HTML + decoded image bytes",
            "rendered_after": rendered_after}


def _url_is_remote(value: str) -> bool:
    return value.startswith(("http://", "https://", "data:", "//"))


def run_image_repair_request(request: dict, settings: dict) -> dict:
    """Run image repair without generation, credentials or deck changes."""
    try:
        return repair_image(request, anki=AnkiConnector(settings.get("anki_url", "http://127.0.0.1:8765")))
    except (ValueError, KeyError, TypeError, OSError, AnkiConnectError) as exc:
        return {"status": "error", "error": {"message": str(exc), "outcome_uncertain": isinstance(exc, AnkiConnectError) and exc.outcome_uncertain}}
