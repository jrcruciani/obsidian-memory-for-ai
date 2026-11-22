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


class V5FactoryPipelineTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"
        self.run_kf("init", str(self.vault), cwd=REPO_ROOT, check=True)
        # Seed base entity and initial fact via owner
        ops = [
            {"op": "upsert_entity", "entity_id": "elena-voss", "kind": "person", "display": "Elena Voss", "aliases": ["Voss"]},
            {"op": "upsert_entity", "entity_id": "concordance", "kind": "project", "display": "Concordance", "aliases": []},
            {
                "op": "create_fact",
                "entity": "elena-voss",
                "predicate": "base",
                "value": "Berlin, Germany",
                "valid_from": "2026-01-10",
                "observed_at": "2026-01-10T10:00:00Z",
                "last_confirmed": "2026-01-10",
                "confidence": 0.9,
                "assertion": "stated",
                "trust": "owner",
            },
        ]
        seed_file = Path(self._tmp.name) / "seed.json"
        seed_file.write_text(json.dumps(ops), encoding="utf-8")
        b = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b["transaction_id"], "--ops-file", str(seed_file), check=True)
        self.run_kf("transact", "commit", "--txn-id", b["transaction_id"], "--yes", "--rebuild", check=True)

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_kf(self, *args: str, cwd: Path | None = None, check: bool = False) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, KF_TODAY="2026-10-15", KF_NOW="2026-10-15T14:00:00Z")
        return subprocess.run(
            [sys.executable, str(KF_CLI), *args],
            cwd=cwd or self.vault,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    def test_executor_captures_idempotent_signals_and_events(self) -> None:
        s1 = json.loads(
            self.run_kf(
                "capture", "signal",
                "--emitted-by", "agent-executor-00000004",
                "--kind", "gap",
                "--severity", "high",
                "--target-namespace", "skills",
                "--summary", "Missing skill for azurite moisture screening",
                "--entities", "concordance",
                "--idempotency-key", "gap-azurite-moisture",
                "--json",
                check=True,
            ).stdout
        )["data"]
        s2 = json.loads(
            self.run_kf(
                "capture", "signal",
                "--emitted-by", "agent-executor-00000004",
                "--kind", "gap",
                "--severity", "high",
                "--target-namespace", "skills",
                "--summary", "Missing skill for azurite moisture screening",
                "--entities", "concordance",
                "--idempotency-key", "gap-azurite-moisture",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertEqual(s1["id"], s2["id"])

        ev = json.loads(
            self.run_kf(
                "capture", "event",
                "--recorded-by", "agent-executor-00000004",
                "--event-id", "evt-field-dispatch",
                "--occurred-at", "2026-10-12T11:00:00Z",
                "--summary", "Elena relocated lab bench to Venice for Q4.",
                "--entities", "elena-voss",
                "--asserts", '[{"entity": "elena-voss", "predicate": "base", "value": "Venice, Italy"}, {"entity": "elena-voss", "predicate": "language", "value": "Italian"}]',
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertTrue((self.vault / ev["path"]).is_file())

    def test_curator_scan_emits_signals_never_empty_proposals_and_supports_dismiss(self) -> None:
        self.run_kf(
            "capture", "event",
            "--recorded-by", "agent-executor-00000004",
            "--event-id", "evt-venice-claim",
            "--occurred-at", "2026-10-12T11:00:00Z",
            "--summary", "Field report mentions Venice base and Italian language.",
            "--entities", "elena-voss",
            "--asserts", '[{"entity": "elena-voss", "predicate": "base", "value": "Venice, Italy"}, {"entity": "elena-voss", "predicate": "language", "value": "Italian"}]',
            check=True,
        )
        scan = json.loads(
            self.run_kf(
                "curate", "scan",
                "--emit-signals",
                "--emitted-by", "agent-curator-00000003",
                "--json",
                check=True,
            ).stdout
        )["data"]
        kinds = {d["kind"] for d in scan["detections"]}
        self.assertIn("stale", kinds)
        self.assertIn("contradiction", kinds)
        self.assertIn("uncurated_claim", kinds)
        # Proposals directory remains untouched (zero fake diagnostic proposals!)
        self.assertEqual(list((self.vault / "factory/proposals").glob("*.md")), [])
        self.assertGreaterEqual(len(scan["emitted_signals"]), 3)

        # Executor cannot dismiss signals; Curator can
        sig_id = scan["emitted_signals"][0]["id"]
        bad = self.run_kf("curate", "dismiss-signal", "--signal-id", sig_id, "--curator", "agent-executor-00000004", "--reason", "not authorized", "--yes")
        self.assertNotEqual(bad.returncode, 0)

        ok = json.loads(
            self.run_kf("curate", "dismiss-signal", "--signal-id", sig_id, "--curator", "agent-curator-00000003", "--reason", "Berlin remains permanent base; Venice is temporary.", "--yes", "--rebuild", "--json", check=True).stdout
        )["data"]
        self.assertEqual(ok["status"], "dismissed")
        self.assertEqual(self.run_kf("lint", "--strict").returncode, 0)

    def test_end_to_end_capture_curate_review_publish_resolves_signal_and_enforces_governance(self) -> None:
        sig = json.loads(
            self.run_kf(
                "capture", "signal",
                "--emitted-by", "agent-executor-00000004",
                "--kind", "gap",
                "--severity", "high",
                "--target-namespace", "skills",
                "--summary", "Need standardized azurite humidity check skill",
                "--entities", "concordance",
                "--json",
                check=True,
            ).stdout
        )["data"]

        skill_op = [{
            "op": "create_skill",
            "slug": "azurite-humidity-check",
            "title": "Azurite Panel Humidity Screening",
            "domain": "conservation",
            "triggers": ["azurite scan", "panel humidity"],
            "verification": ["Confirm RH between 45% and 55% before XRF exposure"],
            "entities": ["concordance"],
            "derived_from": [sig["path"]],
            "trust": "agent",
            "confidence": 0.9,
            "body": "## Procedure\n\n1. Measure surface & ambient RH.\n2. Abort scan if RH > 55%.",
        }]
        ops_path = Path(self._tmp.name) / "skill_op.json"
        ops_path.write_text(json.dumps(skill_op), encoding="utf-8")

        # Executor cannot propose in skills namespace
        denied_prop = self.run_kf(
            "propose", "create",
            "--title", "Add azurite humidity skill",
            "--namespace", "skills",
            "--proposer", "agent-executor-00000004",
            "--ops-file", str(ops_path),
        )
        self.assertNotEqual(denied_prop.returncode, 0)

        # Curator cannot claim trust=owner
        owner_spoof = [dict(skill_op[0], trust="owner")]
        spoof_path = Path(self._tmp.name) / "spoof.json"
        spoof_path.write_text(json.dumps(owner_spoof), encoding="utf-8")
        spoof_res = self.run_kf(
            "propose", "create",
            "--title", "Spoof owner trust",
            "--namespace", "skills",
            "--proposer", "agent-curator-00000003",
            "--ops-file", str(spoof_path),
        )
        self.assertNotEqual(spoof_res.returncode, 0)
        self.assertIn("trust", spoof_res.stdout + spoof_res.stderr)

        # Curator creates legitimate proposal linked to signal
        prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Add azurite humidity screening skill",
                "--namespace", "skills",
                "--proposer", "agent-curator-00000003",
                "--rationale", "Addresses executor gap during panel scan.",
                "--resolves-signals", sig["id"],
                "--ops-file", str(ops_path),
                "--json",
                check=True,
            ).stdout
        )["data"]
        prop_id = prop["id"]

        # Self-approval rejected
        self_rev = self.run_kf("review", "approve", "--proposal-id", prop_id, "--reviewer", "agent-curator-00000003")
        self.assertNotEqual(self_rev.returncode, 0)
        self.assertIn("self-approval", self_rev.stdout + self_rev.stderr)

        # Executor cannot review
        exec_rev = self.run_kf("review", "approve", "--proposal-id", prop_id, "--reviewer", "agent-executor-00000004")
        self.assertNotEqual(exec_rev.returncode, 0)

        # Independent reviewer approves
        rev = json.loads(
            self.run_kf(
                "review", "approve",
                "--proposal-id", prop_id,
                "--reviewer", "agent-reviewer-00000002",
                "--comment", "Verified RH thresholds against conservation standard.",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertEqual(rev["verdict"], "approved")

        # Tampering check: if we alter title in proposal file without re-review, publish refuses!
        prop_file = self.vault / "factory/proposals" / f"{prop_id}.md"
        original_text = prop_file.read_text(encoding="utf-8")
        prop_file.write_text(original_text.replace("Add azurite humidity screening skill", "Tampered skill title"), encoding="utf-8")
        tampered_pub = self.run_kf("publish", "--proposal-id", prop_id, "--publisher", "agent-reviewer-00000002", "--yes")
        self.assertNotEqual(tampered_pub.returncode, 0)
        self.assertIn("content_hash", tampered_pub.stdout + tampered_pub.stderr)
        prop_file.write_text(original_text, encoding="utf-8")

        # Legitimate publish succeeds, writes skill, resolves signal, emits receipt, rebuilds cleanly
        pub = json.loads(
            self.run_kf(
                "publish",
                "--proposal-id", prop_id,
                "--publisher", "agent-reviewer-00000002",
                "--yes",
                "--rebuild",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertEqual(pub["status"], "committed")
        self.assertTrue((self.vault / "knowledge/skills/azurite-humidity-check.md").is_file())

        # Signal is now resolved and linked to receipt
        sig_text = (self.vault / sig["path"]).read_text(encoding="utf-8")
        self.assertIn("status: resolved", sig_text)
        self.assertIn(pub["receipt_id"], sig_text)

        lint = self.run_kf("lint", "--strict")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)


if __name__ == "__main__":
    unittest.main()
