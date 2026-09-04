#!/usr/bin/env python3
"""Audita o índice legado da V1 sem alterar seus dados."""

import argparse
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys


def sanitize_filename(value):
    safe = value.lower().strip().replace(" ", "_")
    return "".join(character for character in safe if character.isalnum() or character in "_-")


def empty_report(index_path, images_path):
    return {
        "status": "partial",
        "index": {
            "path": str(index_path),
            "sha256_before": None,
            "sha256_after": None,
            "unchanged": None,
            "entry_count": None,
            "reference_count": None,
            "unique_id_count": None,
            "shared_id_count": None,
        },
        "highlights": {},
        "images": {
            "path": str(images_path),
            "jpg_count": None,
            "total_bytes": None,
            "unmatched_jpgs": [],
            "missing_jpgs": [],
        },
        "errors": [],
    }


def read_index(index_path, report):
    try:
        raw_index = index_path.read_bytes()
    except FileNotFoundError:
        report["errors"].append("index: arquivo não encontrado")
        return None
    except OSError as error:
        report["errors"].append("index: não foi possível ler ({})".format(error))
        return None

    report["index"]["sha256_before"] = hashlib.sha256(raw_index).hexdigest()

    try:
        index = json.loads(raw_index.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        report["errors"].append("index: JSON inválido")
        return None

    if not isinstance(index, dict):
        report["errors"].append("index: raiz deve ser um objeto JSON")
        return None

    references = Counter()
    highlights = Counter()
    expected_images = set()

    for entry, metadata in index.items():
        if not isinstance(entry, str) or not isinstance(metadata, dict):
            report["errors"].append("index: entrada com formato inválido")
            return None

        timestamp = metadata.get("timestamp")
        card_ids = metadata.get("card_ids")
        valid_ids = isinstance(card_ids, list) and all(
            isinstance(card_id, int) and not isinstance(card_id, bool)
            for card_id in card_ids
        )
        if not isinstance(timestamp, str) or not valid_ids:
            report["errors"].append("index: metadados com formato inválido")
            return None

        references.update(card_ids)
        normalized_entry = entry.lower().strip()
        if normalized_entry in {"bout", "yarn"}:
            highlights[normalized_entry] += len(card_ids)

        safe_name = sanitize_filename(entry)
        if safe_name:
            expected_images.add(safe_name + ".jpg")

    report["index"].update(
        {
            "entry_count": len(index),
            "reference_count": sum(references.values()),
            "unique_id_count": len(references),
            "shared_id_count": sum(1 for count in references.values() if count > 1),
        }
    )
    report["highlights"] = {
        entry: {"reference_count": highlights[entry]}
        for entry in ("bout", "yarn")
        if entry in highlights
    }
    return expected_images


def audit_images(images_path, expected_images, report):
    try:
        entries = list(images_path.iterdir())
    except FileNotFoundError:
        report["errors"].append("images: diretório não encontrado")
        return
    except NotADirectoryError:
        report["errors"].append("images: caminho não é um diretório")
        return
    except OSError as error:
        report["errors"].append("images: não foi possível listar ({})".format(error))
        return

    jpgs = sorted(
        (entry for entry in entries if entry.suffix.lower() == ".jpg"),
        key=lambda entry: entry.name.lower(),
    )
    total_bytes = 0
    readable_jpgs = []
    for jpg in jpgs:
        try:
            total_bytes += len(jpg.read_bytes())
            readable_jpgs.append(jpg)
        except OSError:
            report["errors"].append("images: não foi possível ler {}".format(jpg.name))

    report["images"]["jpg_count"] = len(jpgs)
    report["images"]["total_bytes"] = total_bytes

    if expected_images is None:
        return

    actual_names = {jpg.name.lower() for jpg in readable_jpgs}
    report["images"]["unmatched_jpgs"] = sorted(
        jpg.name for jpg in readable_jpgs if jpg.name.lower() not in expected_images
    )
    report["images"]["missing_jpgs"] = sorted(expected_images - actual_names)


def verify_index_unchanged(index_path, report):
    before = report["index"]["sha256_before"]
    if before is None:
        return

    try:
        after = hashlib.sha256(index_path.read_bytes()).hexdigest()
    except OSError:
        report["errors"].append("index: não foi possível reler para verificar o hash")
        return

    report["index"]["sha256_after"] = after
    report["index"]["unchanged"] = before == after
    if before != after:
        report["errors"].append("index: conteúdo mudou durante a auditoria")


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--index", required=True, type=Path)
    parser.add_argument("--images", required=True, type=Path)
    parser.add_argument("--report", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv)
    report_path = args.report.resolve()
    index_path = args.index.resolve()
    images_path = args.images.resolve()
    if (
        report_path == index_path
        or report_path == images_path
        or index_path in report_path.parents
        or images_path in report_path.parents
    ):
        print("O relatório deve ficar fora das fontes legadas", file=sys.stderr)
        return 1

    report = empty_report(args.index, args.images)

    expected_images = read_index(args.index, report)
    audit_images(args.images, expected_images, report)
    verify_index_unchanged(args.index, report)
    report["status"] = "complete" if not report["errors"] else "partial"

    try:
        args.report.parent.mkdir(parents=True, exist_ok=True)
        with args.report.open("x", encoding="utf-8") as report_file:
            report_file.write(
                json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
            )
    except OSError as error:
        print("Não foi possível gravar o relatório: {}".format(error), file=sys.stderr)
        return 1

    return 0 if report["status"] == "complete" else 1


if __name__ == "__main__":
    sys.exit(main())
