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

    def test_migrates_v4_decisions_superseded_rejected_proposed_and_non_dec_ids(self) -> None:
        dec_dir = self.src / "memory/decisions"
        dec_dir.mkdir(parents=True, exist_ok=True)

        # 1. Standalone superseded v4 decision (no active DEC-002 head) + DEC-003 superseding it cross-family
        (dec_dir / "DEC-002-legacy-channel.md").write_text(
            "---\n"
            "type: decision\n"
            "id: DEC-002\n"
            "title: Publish Concordance Bulletins via Static FTP\n"
            "status: superseded\n"
            "decided_at: '2025-11-01'\n"
            "entities: [concordance]\n"
            "sources: ['sources/README.md']\n"
            "---\n\nLegacy FTP workflow.\n",
            encoding="utf-8",
        )
        (dec_dir / "DEC-003-git-channel.md").write_text(
            "---\n"
            "type: decision\n"
            "id: DEC-003\n"
            "title: Publish Concordance Bulletins via Signed Git Tags\n"
            "status: accepted\n"
            "decided_at: '2026-04-10'\n"
            "entities: [concordance]\n"
            "supersedes: memory/decisions/DEC-002-legacy-channel.md\n"
            "sources: ['sources/README.md']\n"
            "---\n\nReplaces [[DEC-002-legacy-channel]].\n",
            encoding="utf-8",
        )

        # 2. Same-family superseded subfile with non-DEC id + accepted head
        sub_dir = dec_dir / "DEC-004"
        sub_dir.mkdir(parents=True, exist_ok=True)
        (sub_dir / "2026-01-15.md").write_text(
            "---\n"
            "type: decision\n"
            "id: legacy-sub-id\n"
            "title: Initial XRF Warmup 60s\n"
            "status: superseded\n"
            "decided_at: '2026-01-15'\n"
            "entities: [concordance]\n"
            "---\n\nInitial warmup rule.\n",
            encoding="utf-8",
        )
        (dec_dir / "DEC-004.md").write_text(
            "---\n"
            "type: decision\n"
            "id: DEC-004\n"
            "title: Extend XRF Warmup to 120s\n"
            "status: accepted\n"
            "decided_at: '2026-06-20'\n"
            "entities: [concordance]\n"
            "---\n\nExtended warmup rule.\n",
            encoding="utf-8",
        )

        # 3. Rejected v4 decision -> retracted canonical decision (excluded from active queries)
        (dec_dir / "DEC-005-rejected-sqlite.md").write_text(
            "---\n"
            "type: decision\n"
            "id: DEC-005\n"
            "title: Store Canonical Facts in SQLite\n"
            "status: rejected\n"
            "decided_at: '2026-05-20'\n"
            "entities: [strata]\n"
            "---\n\nRejected because binary databases obscure Git diffs.\n",
            encoding="utf-8",
        )

        # 4. Proposed (unaccepted) v4 decision -> archived to sources/v4-audit-archive/decisions/ + curation signal
        (dec_dir / "DEC-006-draft-laser.md").write_text(
            "---\n"
            "type: decision\n"
            "id: DEC-006\n"
            "title: Draft Proposal for 1064nm Laser Trial\n"
            "status: proposed\n"
            "decided_at: '2026-08-01'\n"
            "entities: [concordance]\n"
            "---\n\nUnapproved draft.\n",
            encoding="utf-8",
        )

        # 5. Non-DEC-NNN IDs (slug ADR id + short dec-7 id)
        (dec_dir / "adr-si-units.md").write_text(
            "---\n"
            "type: decision\n"
            "id: adr-si-units\n"
            "title: Use SI Metric Units in Spectral Tables\n"
            "status: accepted\n"
            "decided_at: '2026-03-01'\n"
            "entities: [concordance]\n"
            "---\n\nAll spectral tables use SI units.\n",
            encoding="utf-8",
        )
        (dec_dir / "short-dec.md").write_text(
            "---\n"
            "type: decision\n"
            "id: dec-7\n"
            "title: Short Number Legacy Decision\n"
            "status: accepted\n"
            "decided_at: '2026-03-05'\n"
            "entities: [strata]\n"
            "---\n\nCoerced to DEC-007.\n",
            encoding="utf-8",
        )

        # Reference both non-DEC and proposed decisions from a fact and a note
        ref_fact = self.src / "memory/facts/concordance/status-summary.md"
        ref_fact.parent.mkdir(parents=True, exist_ok=True)
        ref_fact.write_text(
            "---\n"
            "type: fact\n"
            "id: fact-concordance-status\n"
            "entity: concordance\n"
            "predicate: status-summary\n"
            "value: Active SI conservation protocol\n"
            "recorded_at: '2026-08-15T10:00:00Z'\n"
            "confidence: 0.95\n"
            "derived_from:\n"
            "  - memory/decisions/adr-si-units.md\n"
            "  - memory/decisions/DEC-006-draft-laser.md\n"
            "---\n\nSee [[adr-si-units]], [[DEC-005-rejected-sqlite]], and [[DEC-006-draft-laser]].\n",
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
        mig_data = json.loads(mig.stdout)["data"]
        self.assertGreaterEqual(len(mig_data["emitted_signals"]), 2)

        # Proposed decision is archived, NOT promoted into knowledge/decisions/
        self.assertFalse((self.dst / "knowledge/decisions/DEC-006.md").exists())
        self.assertTrue((self.dst / "sources/v4-audit-archive/decisions/DEC-006-draft-laser.md").is_file())

        # Standalone superseded DEC-002 became deprecated head; DEC-005 rejected became retracted head
        dec2_text = (self.dst / "knowledge/decisions/DEC-002.md").read_text(encoding="utf-8")
        self.assertIn("status: deprecated", dec2_text)
        dec5_text = (self.dst / "knowledge/decisions/DEC-005.md").read_text(encoding="utf-8")
        self.assertIn("status: retracted", dec5_text)

        # Same-family DEC-004 has valid superseded history and DEC-004 head
        self.assertTrue((self.dst / "knowledge/decisions/DEC-004.md").is_file())
        self.assertTrue((self.dst / "knowledge/decisions/DEC-004/2026-01-15.md").is_file())

        # Non-DEC IDs were normalized to valid DEC-NNN... IDs
        self.assertTrue((self.dst / "knowledge/decisions/DEC-007.md").is_file())
        adr_matches = list((self.dst / "knowledge/decisions").glob("DEC-*-adr-si-units.md"))
        self.assertEqual(len(adr_matches), 1)

        # Active decisions query excludes deprecated, retracted (rejected), and proposed decisions
        accepted_out = self.run_kf("query", "decisions", check=True).stdout
        self.assertIn("DEC-003", accepted_out)
        self.assertIn("DEC-004", accepted_out)
        self.assertIn("DEC-007", accepted_out)
        self.assertIn("adr-si-units", accepted_out)
        self.assertNotIn("DEC-002", accepted_out)
        self.assertNotIn("DEC-005", accepted_out)
        self.assertNotIn("DEC-006", accepted_out)

        # Entire migrated vault passes strict lint with 0 errors and 0 warnings
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
