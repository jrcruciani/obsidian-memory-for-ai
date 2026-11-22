from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
KF_CLI = REPO_ROOT / "tools" / "kf.py"
V41_FIXTURE = REPO_ROOT / "tests" / "fixtures" / "v4.1-minimal-vault"


class V5MigrationTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.src = Path(self._tmp.name) / "v41_src"
        self.dst = Path(self._tmp.name) / "v50_dst"
        shutil.copytree(V41_FIXTURE, self.src)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_kf(self, *args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, KF_TODAY="2026-10-15", KF_NOW="2026-10-15T16:00:00Z")
        return subprocess.run(
            [sys.executable, str(KF_CLI), *args],
            cwd=cwd or self.dst,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_migrates_v41_vault_losslessly_and_passes_strict_v5_lint(self) -> None:
        # Set strata/publication-channel current start to 2026-01-01 and inject a prior fact with legacy inclusive `valid_to: 2025-12-31`
        cur_strata = self.src / "memory/facts/strata/publication-channel.md"
        cur_strata.write_text(
            cur_strata.read_text(encoding="utf-8").replace("valid_from: null", "valid_from: '2026-01-01'"),
            encoding="utf-8",
        )
        legacy_hist_dir = self.src / "memory/facts/strata/publication-channel"
        legacy_hist_dir.mkdir(parents=True, exist_ok=True)
        (legacy_hist_dir / "2025-01-01.md").write_text(
            "---\n"
            "type: fact\n"
            "id: fact-strata-pub-old\n"
            "entity: strata\n"
            "predicate: publication-channel\n"
            "value: Internal PDF\n"
            "valid_from: '2025-01-01'\n"
            "valid_to: '2025-12-31'\n"
            "recorded_at: '2025-01-01T08:00:00Z'\n"
            "confidence: medium\n"
            "sources: ['sources/README.md']\n"
            "---\n",
            encoding="utf-8",
        )

        mig = self.run_kf(
            "migrate",
            "--source", str(self.src),
            "--target", str(self.dst),
            "--yes",
            "--json",
            cwd=REPO_ROOT,
            check=True,
        )
        data = json.loads(mig.stdout)["data"]
        self.assertGreaterEqual(data["migrated_counts"]["facts"], 8)
        self.assertTrue((self.dst / "factory/receipts" / f"{data['receipt_id']}.md").is_file())
        self.assertTrue((self.dst / "sources/v4-audit-archive").is_dir())

        # Verify raw sources copied byte-for-byte
        self.assertEqual(
            (self.src / "sources/2026-09-01-equipment-note.md").read_bytes(),
            (self.dst / "sources/2026-09-01-equipment-note.md").read_bytes(),
        )

        # Verify qualitative confidence was NOT fabricated into a float, and a signal was emitted
        base_fm_text = (self.dst / "knowledge/facts/elena-voss/base.md").read_text(encoding="utf-8")
        self.assertIn("confidence: null", base_fm_text)
        sigs = self.run_kf("query", "signals", "--status", "open", check=True).stdout
        self.assertIn("legacy", sigs.lower())

        # Verify inclusive valid_to: 2025-12-31 became exclusive valid_until: 2026-01-01
        old_strata = (self.dst / "knowledge/facts/strata/publication-channel/2025-01-01.md").read_text(encoding="utf-8")
        self.assertIn("2026-01-01", old_strata)

        # Verify temporal queries and alias resolution work on migrated vault
        cur_role = self.run_kf("query", "facts", "--entity", "elena-voss", "--predicate", "role", check=True).stdout
        self.assertIn("Lead conservator and pigment researcher", cur_role)
        hist_role = self.run_kf("query", "facts", "--entity", "elena-voss", "--predicate", "role", "--as-of", "2026-07-01", check=True).stdout
        self.assertIn("Art conservator and pigment researcher", hist_role)
        resolved = self.run_kf("query", "resolve", "Gemäldegalerie", check=True).stdout.strip()
        self.assertEqual(resolved, "gemaeldegalerie")

        # Migrated vault passes strict v5.0 lint with zero errors and zero warnings!
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
