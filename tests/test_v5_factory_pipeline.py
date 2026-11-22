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

    def test_publish_persists_staging_preimages_and_recovers_with_hash_verification(self) -> None:
        import importlib
        from unittest.mock import patch as mock_patch

        # Create & approve a proposal that supersedes base fact AND resolves a signal (multi-file publish)
        sig = json.loads(
            self.run_kf(
                "capture", "signal",
                "--emitted-by", "agent-executor-00000004",
                "--kind", "observation",
                "--severity", "medium",
                "--target-namespace", "facts",
                "--summary", "Elena moved bench to Venice",
                "--entities", "elena-voss",
                "--json",
                check=True,
            ).stdout
        )["data"]
        ops = [{
            "op": "supersede_fact",
            "entity": "elena-voss",
            "predicate": "base",
            "value": "Venice, Italy",
            "valid_from": "2026-10-12",
            "confidence": 0.95,
            "assertion": "stated",
            "trust": "agent",
            "derived_from": [sig["path"]],
        }]
        ops_path = Path(self._tmp.name) / "pub_crash_ops.json"
        ops_path.write_text(json.dumps(ops), encoding="utf-8")
        prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Supersede Elena base to Venice",
                "--namespace", "facts",
                "--proposer", "agent-curator-00000003",
                "--resolves-signals", sig["id"],
                "--ops-file", str(ops_path),
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.run_kf("review", "approve", "--proposal-id", prop["id"], "--reviewer", "agent-reviewer-00000002", "--comment", "OK", check=True)
        self.run_kf("rebuild", check=True)

        # Snapshot pre-publish bytes of canonical & factory files
        fact_head = self.vault / "knowledge/facts/elena-voss/base.md"
        fact_hist = self.vault / "knowledge/facts/elena-voss/base/2026-01-10.md"
        prop_file = self.vault / prop["path"]
        sig_file = self.vault / sig["path"]
        before_fact_bytes = fact_head.read_bytes()
        before_prop_bytes = prop_file.read_bytes()
        before_sig_bytes = sig_file.read_bytes()

        # Simulate hard process crash (BaseException bypassing except Exception, like SIGKILL) mid-publish
        # after staging is persisted and after 2 live files are written!
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        try:
            governance = importlib.import_module("kflib.governance")
            transact = importlib.import_module("kflib.transact")
            real_atomic_write = transact.atomic_write_text
            live_writes_count = 0

            def crashing_write(path: Path, content: str) -> None:
                nonlocal live_writes_count
                real_atomic_write(path, content)
                if path.resolve().is_relative_to(self.vault.resolve()) and "_staging" not in path.parts:
                    live_writes_count += 1
                    if live_writes_count == 2:
                        raise KeyboardInterrupt("simulated hard crash mid-publish")

            old_env = os.environ.get("KF_TODAY"), os.environ.get("KF_NOW")
            os.environ["KF_TODAY"] = "2026-10-15"
            os.environ["KF_NOW"] = "2026-10-15T14:30:00Z"
            try:
                with mock_patch.object(transact, "atomic_write_text", side_effect=crashing_write):
                    with self.assertRaises(KeyboardInterrupt):
                        governance.publish_proposal(
                            self.vault,
                            proposal_id=prop["id"],
                            publisher_id="agent-reviewer-00000002",
                            yes=True,
                            rebuild=False,
                        )
            finally:
                if old_env[0] is None:
                    os.environ.pop("KF_TODAY", None)
                else:
                    os.environ["KF_TODAY"] = old_env[0]
                if old_env[1] is None:
                    os.environ.pop("KF_NOW", None)
                else:
                    os.environ["KF_NOW"] = old_env[1]
        finally:
            sys.path.pop(0)

        # Verify staging directory & preimages manifest WERE persisted on disk during publish!
        staging_dirs = list((self.vault / "factory/_staging").glob("txn-*"))
        self.assertEqual(len(staging_dirs), 1, "publish must persist a txn-* staging directory on disk")
        manifest_path = staging_dirs[0] / "preimages/manifest.json"
        self.assertTrue(manifest_path.is_file(), "publish must persist preimages/manifest.json before writing live files")

        # 1. External edit guard: if a touched file is modified post-crash (matching neither before_hash nor after_hash), recover refuses!
        tampered_fact = fact_head.read_bytes() + b"\n<!-- external concurrent edit -->\n"
        real_fact_mid_crash = fact_head.read_bytes()
        fact_head.write_bytes(tampered_fact)
        refused_ext = self.run_kf("transact", "recover", "--yes")
        self.assertNotEqual(refused_ext.returncode, 0)
        self.assertIn("hash", (refused_ext.stdout + refused_ext.stderr).lower())
        fact_head.write_bytes(real_fact_mid_crash)

        # 2. Corrupted preimage guard: if manifest before_text doesn't match before_hash, recover refuses!
        raw_manifest = manifest_path.read_text(encoding="utf-8")
        corrupt_data = json.loads(raw_manifest)
        first_key = next(k for k, v in corrupt_data.items() if isinstance(v, dict) and v.get("before_text") is not None)
        corrupt_data[first_key]["before_text"] += "\ncorrupted"
        manifest_path.write_text(json.dumps(corrupt_data), encoding="utf-8")
        refused_corrupt = self.run_kf("transact", "recover", "--yes")
        self.assertNotEqual(refused_corrupt.returncode, 0)
        self.assertIn("hash", (refused_corrupt.stdout + refused_corrupt.stderr).lower())
        manifest_path.write_text(raw_manifest, encoding="utf-8")

        # 3. Clean recovery restores exact preimages, deletes newly created history file, clears staging, and passes strict lint!
        rec = json.loads(self.run_kf("transact", "recover", "--yes", "--json", check=True).stdout)["data"]
        self.assertEqual(len(rec["recovered"]), 1)
        self.assertEqual(fact_head.read_bytes(), before_fact_bytes)
        self.assertFalse(fact_hist.exists())
        self.assertEqual(prop_file.read_bytes(), before_prop_bytes)
        self.assertEqual(sig_file.read_bytes(), before_sig_bytes)
        self.assertEqual(self.run_kf("lint", "--strict").returncode, 0)

    def test_propose_title_isolation_and_precondition_hash_across_skill_guidance_decision(self) -> None:
        # Seed a skill, guidance, and decision via owner transaction
        seed_ops = [
            {
                "op": "create_skill",
                "slug": "raman-scan",
                "title": "Original Raman Skill Title",
                "domain": "conservation",
                "triggers": ["raman scan"],
                "verification": ["Check 520 cm-1 silicon band"],
                "trust": "owner",
                "confidence": 0.9,
            },
            {
                "op": "create_guidance",
                "slug": "laser-power-cap",
                "title": "Original Laser Guidance Title",
                "domain": "conservation",
                "scope": "executor",
                "priority": "high",
                "policy_rule": "Keep laser power <= 5 mW on pigments.",
                "trust": "owner",
            },
            {
                "op": "create_decision",
                "decision_id": "DEC-009",
                "title": "Original Decision Title",
                "decided_at": "2026-06-01",
                "domain": "conservation",
                "summary": "Cap Raman excitation power.",
            },
        ]
        seed_path = Path(self._tmp.name) / "seed_sgd.json"
        seed_path.write_text(json.dumps(seed_ops), encoding="utf-8")
        b = json.loads(self.run_kf("transact", "begin", "--idempotency-key", "seed-sgd", "--actor", "agent-owner-00000001", "--json", check=True).stdout)["data"]
        self.run_kf("transact", "add", "--txn-id", b["transaction_id"], "--ops-file", str(seed_path), check=True)
        self.run_kf("transact", "commit", "--txn-id", b["transaction_id"], "--yes", check=True)

        # 1. CLI `propose create --title` must NOT leak into op["title"] on fact or supersede_skill!
        fact_prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Proposal Level Title Only",
                "--namespace", "facts",
                "--proposer", "agent-curator-00000003",
                "--op", "create_fact",
                "--entity", "elena-voss",
                "--predicate", "language",
                "--value", "German",
                "--confidence", "0.9",
                "--assertion", "stated",
                "--trust", "agent",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertNotIn("title", fact_prop["ops"][0], "propose --title leaked into op['title']")

        sk_prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Proposal Wrapper Title For Skill Update",
                "--namespace", "skills",
                "--proposer", "agent-curator-00000003",
                "--op", "supersede_skill",
                "--slug", "raman-scan",
                "--triggers", "raman scan", "silicon calibration",
                "--trust", "agent",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertNotIn("title", sk_prop["ops"][0], "propose --title leaked into supersede_skill op['title']")
        self.assertIn("precondition_hash", sk_prop["ops"][0], "supersede_skill proposal op missing precondition_hash")

        gd_prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Update laser guidance rule",
                "--namespace", "guidance",
                "--proposer", "agent-curator-00000003",
                "--op", "supersede_guidance",
                "--slug", "laser-power-cap",
                "--policy-rule", "Keep laser power <= 2 mW on organic lakes.",
                "--trust", "agent",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertIn("precondition_hash", gd_prop["ops"][0], "supersede_guidance proposal op missing precondition_hash")

        dec_prop = json.loads(
            self.run_kf(
                "propose", "create",
                "--title", "Supersede DEC-009 power ceiling",
                "--namespace", "decisions",
                "--proposer", "agent-curator-00000003",
                "--op", "supersede_decision",
                "--decision-id", "DEC-009",
                "--summary", "Lower cap to 2 mW.",
                "--json",
                check=True,
            ).stdout
        )["data"]
        self.assertIn("precondition_hash", dec_prop["ops"][0], "supersede_decision proposal op missing precondition_hash")

        # Approve all three proposals
        for p_item in (sk_prop, gd_prop, dec_prop):
            self.run_kf("review", "approve", "--proposal-id", p_item["id"], "--reviewer", "agent-reviewer-00000002", "--comment", "Approved", check=True)

        # Mutate each target on disk -> publish MUST fail with precondition_hash mismatch!
        for target_rel, p_item in (
            ("knowledge/skills/raman-scan.md", sk_prop),
            ("knowledge/guidance/laser-power-cap.md", gd_prop),
            ("knowledge/decisions/DEC-009.md", dec_prop),
        ):
            tpath = self.vault / target_rel
            orig = tpath.read_text(encoding="utf-8")
            tpath.write_text(orig + "\n<!-- concurrent change -->\n", encoding="utf-8")
            stale_pub = self.run_kf("publish", "--proposal-id", p_item["id"], "--publisher", "agent-reviewer-00000002", "--yes")
            self.assertNotEqual(stale_pub.returncode, 0)
            self.assertIn("precondition_hash mismatch", stale_pub.stdout + stale_pub.stderr)
            tpath.write_text(orig, encoding="utf-8")

        # Restored skill publishes cleanly and preserves its original title ("Original Raman Skill Title")!
        self.run_kf("publish", "--proposal-id", sk_prop["id"], "--publisher", "agent-reviewer-00000002", "--yes", check=True)
        published_skill = (self.vault / "knowledge/skills/raman-scan.md").read_text(encoding="utf-8")
        self.assertIn("Original Raman Skill Title", published_skill)
        self.assertNotIn("Proposal Wrapper Title For Skill Update", published_skill)


if __name__ == "__main__":
    unittest.main()
