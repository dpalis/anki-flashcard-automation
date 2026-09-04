import ast
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "audit_legacy.py"


class LegacyAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp_dir = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp_dir.cleanup)
        self.base = Path(self.temp_dir.name)
        self.index = self.base / "processadas.json"
        self.images = self.base / "images"
        self.report = self.base / "reports" / "legacy-audit.json"

    def run_audit(self):
        return subprocess.run(
            [
                sys.executable,
                str(SCRIPT),
                "--index",
                str(self.index),
                "--images",
                str(self.images),
                "--report",
                str(self.report),
            ],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            check=False,
        )

    def write_index(self, value):
        self.index.write_text(
            json.dumps(value, ensure_ascii=False),
            encoding="utf-8",
        )

    def test_reports_aggregates_highlights_and_filename_discrepancies(self):
        self.write_index(
            {
                "Bout": {"timestamp": "2026-01-01", "card_ids": [10, 11, 12]},
                "Yarn": {"timestamp": "2026-01-02", "card_ids": [12, 13]},
                "Hello, World!": {"timestamp": "2026-01-03", "card_ids": [14]},
            }
        )
        self.images.mkdir()
        (self.images / "bout.jpg").write_bytes(b"bout")
        (self.images / "yarn.jpg").write_bytes(b"yarn-image")
        (self.images / "injunction.jpg").write_bytes(b"orphan")
        images_before = {
            image.name: image.read_bytes() for image in self.images.iterdir()
        }

        result = self.run_audit()

        self.assertEqual(0, result.returncode, result.stderr)
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual("complete", report["status"])
        self.assertEqual([], report["errors"])
        self.assertEqual(3, report["index"]["entry_count"])
        self.assertEqual(6, report["index"]["reference_count"])
        self.assertEqual(5, report["index"]["unique_id_count"])
        self.assertEqual(1, report["index"]["shared_id_count"])
        self.assertTrue(report["index"]["unchanged"])
        self.assertEqual(
            {"bout": {"reference_count": 3}, "yarn": {"reference_count": 2}},
            report["highlights"],
        )
        self.assertEqual(3, report["images"]["jpg_count"])
        self.assertEqual(20, report["images"]["total_bytes"])
        self.assertEqual(["injunction.jpg"], report["images"]["unmatched_jpgs"])
        self.assertEqual(["hello_world.jpg"], report["images"]["missing_jpgs"])
        self.assertEqual(
            images_before,
            {image.name: image.read_bytes() for image in self.images.iterdir()},
        )

    def test_invalid_json_is_partial_and_preserves_source_bytes(self):
        original = b"{invalid json\n"
        self.index.write_bytes(original)
        self.images.mkdir()

        result = self.run_audit()

        self.assertEqual(1, result.returncode)
        self.assertEqual(original, self.index.read_bytes())
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual("partial", report["status"])
        self.assertTrue(report["index"]["unchanged"])
        self.assertEqual(
            report["index"]["sha256_before"],
            report["index"]["sha256_after"],
        )
        self.assertTrue(any(error.startswith("index:") for error in report["errors"]))

    def test_missing_images_is_partial_and_does_not_create_source_directory(self):
        self.write_index(
            {"bout": {"timestamp": "2026-01-01", "card_ids": [10, 11]}}
        )

        result = self.run_audit()

        self.assertEqual(1, result.returncode)
        self.assertFalse(self.images.exists())
        report = json.loads(self.report.read_text(encoding="utf-8"))
        self.assertEqual("partial", report["status"])
        self.assertTrue(report["index"]["unchanged"])
        self.assertTrue(any(error.startswith("images:") for error in report["errors"]))

    def test_report_cannot_overwrite_legacy_sources(self):
        original = b'{"bout":{"timestamp":"2026-01-01","card_ids":[10,11]}}'
        self.index.write_bytes(original)
        self.images.mkdir()

        for report_path in (self.index, self.images / "legacy-audit.json"):
            with self.subTest(report_path=report_path):
                self.report = report_path
                result = self.run_audit()
                self.assertEqual(1, result.returncode)
                self.assertIn("fora das fontes legadas", result.stderr)
                self.assertEqual(original, self.index.read_bytes())
                self.assertFalse((self.images / "legacy-audit.json").exists())

    def test_report_does_not_create_or_overwrite_an_input_path(self):
        missing_index = self.base / "missing-processadas.json"
        self.index = missing_index
        self.report = missing_index / "legacy-audit.json"

        nested_result = self.run_audit()

        self.assertEqual(1, nested_result.returncode)
        self.assertIn("fora das fontes legadas", nested_result.stderr)
        self.assertFalse(missing_index.exists())

        legacy_input = self.base / "palavras.txt"
        original = b"legacy words\n"
        legacy_input.write_bytes(original)
        self.index = self.base / "processadas.json"
        self.write_index(
            {"bout": {"timestamp": "2026-01-01", "card_ids": [10, 11]}}
        )
        self.report = legacy_input

        overwrite_result = self.run_audit()

        self.assertEqual(1, overwrite_result.returncode)
        self.assertEqual(original, legacy_input.read_bytes())

    def test_script_has_no_anki_or_third_party_imports(self):
        tree = ast.parse(SCRIPT.read_text(encoding="utf-8"))
        imports = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                imports.extend(alias.name for alias in node.names)
            elif isinstance(node, ast.ImportFrom):
                imports.append(node.module or "")

        self.assertFalse(any("anki" in name.lower() for name in imports))
        self.assertTrue(
            set(imports).issubset(
                {"argparse", "collections", "hashlib", "json", "pathlib", "sys"}
            )
        )


if __name__ == "__main__":
    unittest.main()
