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

    def test_migrates_standalone_entity_files_and_canonical_decision_id_paths(self) -> None:
        # 1. Add standalone entity files under memory/entities/*.md (not present in memory/entities.md)
        ent_dir = self.src / "memory/entities"
        ent_dir.mkdir(parents=True, exist_ok=True)
        (ent_dir / "raman-probe.md").write_text(
            "---\n"
            "type: entity\n"
            "id: raman-probe\n"
            "kind: tool\n"
            "display: Portable Raman Probe\n"
            "aliases: [Raman Probe, Raman-785]\n"
            "---\n\n# Portable Raman Probe\n",
            encoding="utf-8",
        )
        # Also augment an existing entity from memory/entities/*.md
        (ent_dir / "concordance.md").write_text(
            "---\n"
            "type: entity\n"
            "id: concordance\n"
            "kind: project\n"
            "display: Concordance\n"
            "aliases: [Concordance Atlas]\n"
            "---\n",
            encoding="utf-8",
        )
        # Reference the new standalone entity and the legacy decision filename from a fact
        raman_fact = self.src / "memory/facts/raman-probe/role.md"
        raman_fact.parent.mkdir(parents=True, exist_ok=True)
        raman_fact.write_text(
            "---\n"
            "type: fact\n"
            "id: fact-concordance-raman-tool\n"
            "entity: raman-probe\n"
            "predicate: role\n"
            "value: Supplemental spectroscopy unit\n"
            "recorded_at: '2026-08-10T10:00:00Z'\n"
            "confidence: 0.9\n"
            "derived_from:\n"
            "  - memory/decisions/DEC-001-v4-transaction-model.md\n"
            "---\n\nSee [[DEC-001-v4-transaction-model]] for governance context.\n",
            encoding="utf-8",
        )

        self.run_kf(
            "migrate",
            "--source", str(self.src),
            "--target", str(self.dst),
            "--yes",
            cwd=REPO_ROOT,
            check=True,
        )

        # Standalone entity from memory/entities/raman-probe.md must be migrated & resolvable
        resolved_raman = self.run_kf("query", "resolve", "Raman-785", check=True).stdout.strip()
        self.assertEqual(resolved_raman, "raman-probe")
        resolved_conc = self.run_kf("query", "resolve", "Concordance Atlas", check=True).stdout.strip()
        self.assertEqual(resolved_conc, "concordance")

        # Decision DEC-001 (from DEC-001-v4-transaction-model.md) MUST be written at canonical {id}.md
        self.assertTrue((self.dst / "knowledge/decisions/DEC-001.md").is_file())
        self.assertFalse((self.dst / "knowledge/decisions/DEC-001-v4-transaction-model.md").exists())

        # query why decision DEC-001 works because canonical path matches {id}.md!
        why_dec = self.run_kf("query", "why", "decision", "DEC-001", check=True).stdout
        self.assertIn("knowledge/decisions/DEC-001.md", why_dec)

        # Migrated vault passes strict lint (including rewritten derived_from and wikilinks)
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
