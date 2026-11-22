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


class V5CoreAndLintTests(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.vault = Path(self._tmp.name) / "vault"

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def run_kf(self, *args: str, cwd: Path | None = None, check: bool = False, extra_env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
        env = dict(os.environ, KF_TODAY="2026-10-15")
        if extra_env:
            env.update(extra_env)
        return subprocess.run(
            [sys.executable, str(KF_CLI), *args],
            cwd=cwd or self.vault,
            env=env,
            capture_output=True,
            text=True,
            check=check,
        )

    def init_vault(self) -> None:
        res = self.run_kf("init", str(self.vault), cwd=REPO_ROOT, check=True)
        self.assertIn("Initialized Knowledge Factory v5.0 vault", res.stdout)

    def test_yaml_io_roundtrips_with_and_without_pyyaml(self) -> None:
        sys.path.insert(0, str(REPO_ROOT / "tools"))
        try:
            from kflib import yaml_io
        finally:
            sys.path.pop(0)

        sample = {
            "type": "proposal",
            "id": "prop-sample-001",
            "confidence": 0.85,
            "pinned": True,
            "supersedes": None,
            "tags": ["pigment", "xrf:calibrated", "yes"],
            "ops": [
                {
                    "op": "create_fact",
                    "entity": "elena-voss",
                    "predicate": "role",
                    "value": "Lead conservator: Venice panel",
                    "derived_from": ["sources/note.md"],
                    "body": "## Trigger\n\n1. Step one.\n2. Step two.",
                }
            ],
        }
        dumped_fallback = yaml_io.dump_yaml(sample, force_fallback=True)
        loaded_fallback = yaml_io.load_yaml(dumped_fallback, force_fallback=True)
        self.assertEqual(loaded_fallback, sample)

        dumped_default = yaml_io.dump_yaml(sample)
        loaded_default = yaml_io.load_yaml(dumped_default)
        self.assertEqual(loaded_default, sample)

        # Cross-compatibility: fallback parser MUST parse PyYAML indentless sequences and wrapped plain scalars
        pyyaml_style = (
            "type: guidance\n"
            "policy_rule: Report all spectroscopic energies (keV), distances (mm), and relative\n"
            "  humidity (%RH) in SI/metric units with tolerance.\n"
            "entities:\n"
            "- concordance\n"
            "- elena-voss\n"
            "ops:\n"
            "- op: create_fact\n"
            "  entity: concordance\n"
        )
        cross = yaml_io.load_yaml(pyyaml_style, force_fallback=True)
        self.assertEqual(cross["entities"], ["concordance", "elena-voss"])
        self.assertIn("humidity (%RH)", cross["policy_rule"])
        self.assertEqual(cross["ops"][0]["entity"], "concordance")

    def test_init_creates_four_plane_vault_and_passes_strict_lint(self) -> None:
        self.init_vault()
        for rel in (
            "AGENTS.md",
            "CLAUDE.md",
            "sources/README.md",
            "knowledge/entities.md",
            "factory/schema/manifest.yaml",
            "factory/schema/predicates.yaml",
            "factory/schema/policy.yaml",
            "factory/schema/bootstrap.yaml",
            "factory/schema/fact.schema.yaml",
            "factory/schema/skill.schema.yaml",
            "factory/schema/guidance.schema.yaml",
            "factory/schema/signal.schema.yaml",
            "factory/schema/proposal.schema.yaml",
            "factory/schema/review.schema.yaml",
            "factory/schema/decision.schema.yaml",
            "factory/schema/receipt.schema.yaml",
            "factory/schema/event.schema.yaml",
            "_generated/views/bootstrap.md",
            "_generated/indexes/lexical.md",
            "_generated/indexes/graph.md",
        ):
            self.assertTrue((self.vault / rel).exists(), f"missing {rel}")

        lint = self.run_kf("lint", "--strict", "--json")
        self.assertEqual(lint.returncode, 0, lint.stdout + lint.stderr)
        payload = json.loads(lint.stdout)
        self.assertTrue(payload["ok"])
        self.assertEqual(payload["protocol_version"], "5.0")
        self.assertEqual(payload["data"]["error_count"], 0)

    def test_lint_rejects_wrong_spec_version(self) -> None:
        self.init_vault()
        manifest = self.vault / "factory/schema/manifest.yaml"
        manifest.write_text('spec_version: "4.1"\nprotocol: "knowledge-factory"\n', encoding="utf-8")
        lint = self.run_kf("lint")
        self.assertNotEqual(lint.returncode, 0)
        self.assertIn("spec_version must be '5.0'", lint.stdout + lint.stderr)

    def test_lint_rejects_unknown_entity_and_legacy_string_confidence(self) -> None:
        self.init_vault()
        fact_path = self.vault / "knowledge/facts/ghost-entity/role.md"
        fact_path.parent.mkdir(parents=True, exist_ok=True)
        fact_path.write_text(
            "---\n"
            "type: fact\n"
            "id: fact-ghost-role\n"
            "entity: ghost-entity\n"
            "predicate: role\n"
            "value: Researcher\n"
            "status: active\n"
            "observed_at: '2026-10-01T10:00:00Z'\n"
            "confidence: high\n"
            "assertion: stated\n"
            "trust: owner\n"
            "last_confirmed: '2026-10-01'\n"
            "---\n",
            encoding="utf-8",
        )
        lint = self.run_kf("lint")
        self.assertNotEqual(lint.returncode, 0)
        out = lint.stdout + lint.stderr
        self.assertIn("unknown entity 'ghost-entity'", out)
        self.assertIn("confidence", out)

    def test_lint_rejects_accent_folded_alias_collision(self) -> None:
        self.init_vault()
        entities = self.vault / "knowledge/entities.md"
        entities.write_text(
            "---\n"
            "type: entity-registry\n"
            "id: entity-registry\n"
            "entities:\n"
            "  - id: elena-voss\n"
            "    kind: person\n"
            "    display: Elena Voss\n"
            "    aliases: [Éléna]\n"
            "  - id: elena-novak\n"
            "    kind: person\n"
            "    display: Elena Novak\n"
            "    aliases: [elena]\n"
            "---\n\n# Canonical Entities\n",
            encoding="utf-8",
        )
        lint = self.run_kf("lint")
        self.assertNotEqual(lint.returncode, 0)
        self.assertIn("alias collision", lint.stdout + lint.stderr)

    def test_lint_rejects_invalid_interval_and_broken_wikilink(self) -> None:
        self.init_vault()
        entities = self.vault / "knowledge/entities.md"
        entities.write_text(
            "---\n"
            "type: entity-registry\n"
            "id: entity-registry\n"
            "entities:\n"
            "  - id: elena-voss\n"
            "    kind: person\n"
            "    display: Elena Voss\n"
            "    aliases: []\n"
            "---\n\n# Canonical Entities\n",
            encoding="utf-8",
        )
        fact_path = self.vault / "knowledge/facts/elena-voss/role.md"
        fact_path.parent.mkdir(parents=True, exist_ok=True)
        fact_path.write_text(
            "---\n"
            "type: fact\n"
            "id: fact-elena-role\n"
            "entity: elena-voss\n"
            "predicate: role\n"
            "value: Researcher\n"
            "status: active\n"
            "valid_from: '2026-10-10'\n"
            "valid_until: '2026-10-05'\n"
            "observed_at: '2026-10-10T10:00:00Z'\n"
            "confidence: 0.9\n"
            "assertion: stated\n"
            "trust: owner\n"
            "last_confirmed: '2026-10-10'\n"
            "---\n\nSee [[nonexistent-target-note]] for details.\n",
            encoding="utf-8",
        )
        lint = self.run_kf("lint")
        self.assertNotEqual(lint.returncode, 0)
        out = lint.stdout + lint.stderr
        self.assertIn("valid_from", out)
        self.assertIn("unresolved wikilink", out)


if __name__ == "__main__":
    unittest.main()
