from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
KF_CLI = REPO_ROOT / "tools" / "kf.py"


class V5TransactionsAndTypesTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        self.run_kf("init", str(self.vault), cwd=REPO_ROOT, check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_kf(self, *args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, KF_TODAY="2026-10-15", KF_NOW="2026-10-15T12:00:00Z")
        return subprocess.run(
            [sys.executable, str(KF_CLI), *args],
            cwd=cwd or self.vault,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_executor_and_curator_cannot_run_direct_transactions(self) -> None:
        for actor in ("agent-executor-00000004", "agent-curator-00000003"):
            res = self.run_kf("transact", "begin", "--idempotency-key", f"key-{actor}", "--actor", actor)
            self.assertNotEqual(res.returncode, 0)
            self.assertIn("direct_transact", res.stdout + res.stderr)

    def test_owner_cannot_direct_transact_external_trust_fact(self) -> None:
        ops_file = self.vault / "_ops_ext.json"
        ops_file.write_text(json.dumps([
            {"op": "upsert_entity", "entity_id": "concordance", "kind": "project", "display": "Concordance", "aliases": []},
            {
                "op": "create_fact",
                "entity": "concordance",
                "predicate": "tool",
                "value": "Unverified XRF",
                "trust": "external",
                "confidence": 0.6,
                "assertion": "stated",
            },
        ]), encoding="utf-8")
        begin = self.run_kf("transact", "begin", "--idempotency-key", "ext-test", "--actor", "agent-owner-00000001", "--json", check=True)
        txn_id = json.loads(begin.stdout)["data"]["transaction_id"]
        add = self.run_kf("transact", "add", "--txn-id", txn_id, "--ops-file", str(ops_file))
        ops_file.unlink()
        if add.returncode == 0:
            commit = self.run_kf("transact", "commit", "--txn-id", txn_id, "--yes")
            self.assertNotEqual(commit.returncode, 0)
            self.assertIn("external", commit.stdout + commit.stderr)
        else:
            self.assertIn("external", add.stdout + add.stderr)

    def test_full_canonical_types_lifecycle_and_supersession(self) -> None:
        # 1. Seed entities, event, initial fact, skill, guidance, decision via owner transaction
        ops_seed = [
            {
                "op": "upsert_entity",
                "entity_id": "elena-voss",
                "kind": "person",
                "display": "Elena Voss",
                "aliases": ["Voss", "Éléna Voss"],
            },
            {
                "op": "upsert_entity",
                "entity_id": "concordance",
                "kind": "project",
                "display": "Concordance Pigment Atlas",
                "aliases": ["Concordance"],
            },
            {
                "op": "create_event",
                "event_id": "evt-kickoff",
                "occurred_at": "2026-03-15T09:00:00Z",
                "summary": "Elena joined Concordance as pigment researcher.",
                "entities": ["elena-voss", "concordance"],
                "sources": ["sources/README.md"],
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "role",
                "value": "Pigment researcher",
                "valid_from": "2026-03-15",
                "confidence": 0.9,
                "assertion": "stated",
                "trust": "owner",
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "pinned": True,
            },
            {
                "op": "create_skill",
                "slug": "xrf-calibration",
                "title": "XRF Spectrum Calibration",
                "domain": "conservation",
                "triggers": ["calibrate xrf", "pigment scan"],
                "inputs": ["raw spectrum file"],
                "outputs": ["calibrated spectrum summary"],
                "verification": ["Confirm copper K-alpha peak within +/- 0.02 keV"],
                "entities": ["concordance"],
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "trust": "owner",
                "confidence": 0.95,
                "pinned": True,
                "body": "## Procedure\n\n1. Warm tube for 120s.\n2. Check copper reference.",
            },
            {
                "op": "create_guidance",
                "slug": "metric-units-only",
                "title": "ISO Metric Units in Conservation Logs",
                "domain": "conservation",
                "scope": "executor",
                "priority": "critical",
                "policy_rule": "Express all pigment dimensions, wavelengths, and masses in SI metric units.",
                "anti_patterns": ["Using inches or Fahrenheit in lab summaries"],
                "entities": ["concordance"],
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "trust": "owner",
                "pinned": True,
                "body": "## Rationale\n\nCross-lab reproducibility requires SI units.",
            },
            {
                "op": "create_decision",
                "decision_id": "DEC-001-si-units",
                "title": "Mandate SI Metric Units Across Concordance",
                "decided_at": "2026-03-15",
                "domain": "conservation",
                "summary": "All measurements in Concordance records use SI units.",
                "entities": ["concordance"],
                "derived_from": ["knowledge/events/2026-03-15/evt-kickoff.md"],
                "consequences": ["Legacy imperial notes require explicit conversion annotations"],
                "pinned": True,
                "body": "## Context\n\nPartner labs operate in Berlin and Venice.",
            },
        ]
        seed_path = Path(self._tmp.name) / "seed.json"
        seed_path.write_text(json.dumps(ops_seed), encoding="utf-8")

        b1 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-001", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b1["transaction_id"], "--ops-file", str(seed_path), check=True)
        c1 = json.loads(self.run_kf("transact", "commit", "--txn-id", b1["transaction_id"], "--yes", "--rebuild", "--json", check=True).stdout)["data"]
        self.assertEqual(c1["status"], "committed")
        self.assertTrue((self.vault / "factory/receipts" / f"{c1['receipt_id']}.md").is_file())

        # Idempotent replay with same key does not create a second receipt
        replay = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-001", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.assertEqual(replay["status"], "committed")

        # 2. Supersede fact, skill, guidance, decision + retract another fact
        ops_evolve = [
            {
                "op": "create_event",
                "event_id": "evt-promotion",
                "occurred_at": "2026-07-15T10:00:00Z",
                "summary": "Elena appointed Lead Conservator.",
                "entities": ["elena-voss"],
            },
            {
                "op": "supersede_fact",
                "entity": "elena-voss",
                "predicate": "role",
                "value": "Lead conservator",
                "valid_from": "2026-07-15",
                "confidence": 0.98,
                "assertion": "stated",
                "trust": "owner",
                "derived_from": ["knowledge/events/2026-07-15/evt-promotion.md"],
                "pinned": True,
            },
            {
                "op": "supersede_skill",
                "slug": "xrf-calibration",
                "title": "XRF Spectrum Calibration v2",
                "domain": "conservation",
                "triggers": ["calibrate xrf", "pigment scan", "panel xrf"],
                "verification": ["Confirm Cu K-alpha within +/- 0.01 keV", "Log ambient RH%"],
                "trust": "owner",
                "confidence": 0.99,
                "body": "## Procedure v2\n\n1. Warm tube 120s.\n2. Record ambient RH%.\n3. Verify Cu reference.",
            },
            {
                "op": "supersede_guidance",
                "slug": "metric-units-only",
                "title": "SI Metric Units & Uncertainty Bounds",
                "domain": "conservation",
                "scope": "executor",
                "priority": "critical",
                "policy_rule": "Express all measurements in SI units with explicit +/- uncertainty.",
                "anti_patterns": ["Imperial units", "Point estimates without instrument tolerance"],
                "trust": "owner",
            },
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "language",
                "value": "French",
                "confidence": 0.5,
                "assertion": "inferred",
                "trust": "owner",
                "derived_from": ["knowledge/events/2026-07-15/evt-promotion.md"],
            },
        ]
        evolve_path = Path(self._tmp.name) / "evolve.json"
        evolve_path.write_text(json.dumps(ops_evolve), encoding="utf-8")
        b2 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "evolve-002", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b2["transaction_id"], "--ops-file", str(evolve_path), check=True)
        self.run_kf("transact", "commit", "--txn-id", b2["transaction_id"], "--yes", "--rebuild", check=True)

        self.assertTrue((self.vault / "knowledge/facts/elena-voss/role/2026-03-15.md").is_file())
        self.assertTrue((self.vault / "knowledge/skills/xrf-calibration/2026-10-15.md").is_file())
        self.assertTrue((self.vault / "knowledge/guidance/metric-units-only/2026-10-15.md").is_file())

        # Retract the mistaken inferred language fact
        b3 = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "retract-003", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf(
            "transact", "add", "--txn-id", b3["transaction_id"],
            "--op", "retract_fact",
            "--entity", "elena-voss",
            "--predicate", "language",
            "--reason", "Owner withdrew unverified language inference.",
            check=True,
        )
        self.run_kf("transact", "commit", "--txn-id", b3["transaction_id"], "--yes", "--rebuild", check=True)

        # Entire vault passes strict lint!
        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)

    def test_rollback_and_crash_recovery(self) -> None:
        b = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "pending-txn", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        txn_id = b["transaction_id"]
        self.assertTrue((self.vault / "factory/_staging" / txn_id).is_dir())
        rec = self.run_kf("transact", "recover", "--yes", "--json", check=True)
        payload = json.loads(rec.stdout)["data"]
        self.assertIn(txn_id, payload["recovered"])
        self.assertFalse((self.vault / "factory/_staging" / txn_id).exists())


if __name__ == "__main__":
    unittest.main()
