import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest


SCRIPT = Path(__file__).resolve().parents[1] / "ios_page_meta.py"


class PageMetadataMergeTests(unittest.TestCase):
    def test_single_page_files_produce_same_metadata_and_reject_stale_input(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            shards = root / "semantics"
            shards.mkdir()
            pages = [
                {
                    "page_id": f"page_{i:04d}_{name}",
                    "view_name": name,
                    "file_path": name + ".swift",
                    "purpose": "View purpose",
                    "complexity": "simple",
                    "confidence": "high",
                    "ui_structure": {},
                    "state_management": {},
                    "interactions": [],
                    "conversion_strategy": {},
                    "ios_source_anchors": {},
                }
                for i, name in enumerate(("Home", "Detail"), 1)
            ]
            envelope = {"schema_version": 1, "target_input_sha256": "a" * 64,
                        "review": {"method": "source review"}}
            facts = [{key: p[key] for key in ("view_name", "file_path")} for p in pages]
            inventory = root / "inventory.json"
            inventory.write_text(json.dumps({**envelope, "pages": facts}))
            legacy = root / "legacy.json"
            legacy.write_text(json.dumps({**envelope, "pages": pages}))
            for page in reversed(pages):
                path = shards / (page["page_id"] + ".json")
                path.write_text(json.dumps({**envelope, "pages": [page]}))
            command = [sys.executable, "-B", str(SCRIPT), "--inventory", str(inventory)]
            old, new = root / "old", root / "new"
            merged = root / "merged.json"
            subprocess.run([*command, "--semantics", str(legacy), "--output-root", str(old)], check=True,
                           capture_output=True)
            subprocess.run([*command, "--semantics-dir", str(shards), "--output-root", str(new),
                            "--merged-semantics-out", str(merged)], check=True, capture_output=True)
            self.assertEqual(json.loads(merged.read_bytes()), json.loads(legacy.read_bytes()))
            for p in pages:
                meta = Path(p["page_id"]) / "meta.json"
                self.assertEqual((old / meta).read_bytes(), (new / meta).read_bytes())

            path = shards / (pages[-1]["page_id"] + ".json")
            path.write_text(json.dumps({**envelope, "target_input_sha256": "b" * 64, "pages": pages[-1:]}))
            broken = root / "broken"
            bad = subprocess.run([*command, "--semantics-dir", str(shards), "--output-root", str(broken),
                                  "--merged-semantics-out", str(merged)], capture_output=True)
            self.assertEqual(bad.returncode, 2)
            self.assertIn(b"must bind the current source input", bad.stderr)
            self.assertFalse(broken.exists())
            self.assertEqual(json.loads(merged.read_bytes()), json.loads(legacy.read_bytes()))
