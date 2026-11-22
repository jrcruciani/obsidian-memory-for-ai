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

    def test_yaml_fallback_block_scalar_parity_with_pyyaml(self) -> None:
        import importlib

        sys.path.insert(0, str(REPO_ROOT / "tools"))
        try:
            yaml_io = importlib.import_module("kflib.yaml_io")
        finally:
            sys.path.pop(0)

        complex_yaml = (
            "type: proposal\n"
            "# Top-level YAML comment\n"
            "rationale: > # header comment\n"
            "  First wrapped sentence # not a comment.\n"
            "  continues on line two.\n"
            "\n"
            "  Second paragraph after blank line.\n"
            "\n"
            "    indented_example: true # preserved inside folded block\n"
            "\n"
            "  Closing folded line.\n"
            "strip_folded: >-\n"
            "  Compact folded\n"
            "  without trailing newline\n"
            "keep_folded: >+\n"
            "  Folded with trailing blanks\n"
            "\n"
            "\n"
            "literal_clip: |\n"
            "  # Heading 1\n"
            "\n"
            "  Paragraph with #hashtag and trailing spaces:   \n"
            "  ---\n"
            "  ## Subheading #2\n"
            "\n"
            "  ```yaml\n"
            "  key: value # comment inside fenced block\n"
            "  ```\n"
            "\n"
            "  \tTab-prefixed line inside block\n"
            "literal_strip: |-\n"
            "  # No trailing newline\n"
            "\n"
            "  Line two\n"
            "\n"
            "literal_keep: |+\n"
            "  # Keep trailing blank lines\n"
            "\n"
            "  Line two\n"
            "\n"
            "\n"
            "explicit_indent: |2\n"
            "    Two extra spaces preserved\n"
            "  Base block indent\n"
            "empty_literal: |\n"
            "\n"
            "ops:\n"
            "  - body: |\n"
            "      ## Procedure\n"
            "\n"
            "      1. Run XRF #1\n"
            "      ---\n"
            "      2. Log keV\n"
            "    op: create_skill\n"
            "  - |-\n"
            "    # Sequence literal item\n"
            "\n"
            "    With blank line and #hash\n"
        )
        expected = {
            "type": "proposal",
            "rationale": (
                "First wrapped sentence # not a comment. continues on line two.\n"
                "Second paragraph after blank line.\n\n"
                "  indented_example: true # preserved inside folded block\n\n"
                "Closing folded line.\n"
            ),
            "strip_folded": "Compact folded without trailing newline",
            "keep_folded": "Folded with trailing blanks\n\n\n",
            "literal_clip": (
                "# Heading 1\n\n"
                "Paragraph with #hashtag and trailing spaces:   \n"
                "---\n"
                "## Subheading #2\n\n"
                "```yaml\n"
                "key: value # comment inside fenced block\n"
                "```\n\n"
                "\tTab-prefixed line inside block\n"
            ),
            "literal_strip": "# No trailing newline\n\nLine two",
            "literal_keep": "# Keep trailing blank lines\n\nLine two\n\n\n",
            "explicit_indent": "  Two extra spaces preserved\nBase block indent\n",
            "empty_literal": "",
            "ops": [
                {
                    "body": "## Procedure\n\n1. Run XRF #1\n---\n2. Log keV\n",
                    "op": "create_skill",
                },
                "# Sequence literal item\n\nWith blank line and #hash",
            ],
        }
        if yaml_io.has_pyyaml():
            self.assertEqual(yaml_io.load_yaml(complex_yaml, force_fallback=False), expected)
        actual = yaml_io.load_yaml(complex_yaml, force_fallback=True)
        self.assertEqual(actual, expected)

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

    def test_lint_enforces_entity_kinds_and_skill_guidance_decision_invariants(self) -> None:
        self.init_vault()
        # 1. Invalid entity kind ('org' / 'widget') must fail lint
        (self.vault / "knowledge/entities.md").write_text(
            "---\n"
            "type: entity-registry\n"
            "id: entity-registry\n"
            "entities:\n"
            "  - id: bad-org\n"
            "    kind: widget\n"
            "    display: Bad Org\n"
            "    aliases: []\n"
            "---\n",
            encoding="utf-8",
        )
        res_kind = self.run_kf("lint")
        self.assertNotEqual(res_kind.returncode, 0)
        self.assertIn("invalid entity kind", res_kind.stdout + res_kind.stderr)

        # Fix entities to valid kind so we can test skill/guidance/decision invariants
        (self.vault / "knowledge/entities.md").write_text(
            "---\n"
            "type: entity-registry\n"
            "id: entity-registry\n"
            "entities:\n"
            "  - id: concordance\n"
            "    kind: project\n"
            "    display: Concordance\n"
            "    aliases: []\n"
            "---\n",
            encoding="utf-8",
        )

        # 2. Orphan superseded skill without active head + retracted guidance without reason + misplaced decision & broken supersedes
        sup_skill = self.vault / "knowledge/skills/xrf-scan/2026-09-01.md"
        sup_skill.parent.mkdir(parents=True, exist_ok=True)
        sup_skill.write_text(
            "---\n"
            "type: skill\n"
            "id: skill-xrf-scan-v1\n"
            "slug: xrf-scan\n"
            "title: XRF Scan\n"
            "status: superseded\n"
            "version: 1\n"
            "domain: conservation\n"
            "triggers: [xrf]\n"
            "verification: [check peak]\n"
            "trust: owner\n"
            "observed_at: '2026-09-01T10:00:00Z'\n"
            "last_confirmed: '2026-09-01'\n"
            "---\n",
            encoding="utf-8",
        )

        ret_guid = self.vault / "knowledge/guidance/bad-retract.md"
        ret_guid.write_text(
            "---\n"
            "type: guidance\n"
            "id: guid-bad-retract\n"
            "slug: bad-retract\n"
            "title: Bad Retract\n"
            "status: retracted\n"
            "domain: global\n"
            "scope: all\n"
            "priority: normal\n"
            "policy_rule: Outdated rule.\n"
            "trust: owner\n"
            "observed_at: '2026-09-01T10:00:00Z'\n"
            "last_confirmed: '2026-09-01'\n"
            "---\n",
            encoding="utf-8",
        )

        bad_dec = self.vault / "knowledge/decisions/DEC-010-wrong-filename.md"
        bad_dec.write_text(
            "---\n"
            "type: decision\n"
            "id: DEC-010\n"
            "title: Wrong Filename Decision\n"
            "status: accepted\n"
            "decided_at: '2026-09-01'\n"
            "decided_by: agent-owner-00000001\n"
            "domain: governance\n"
            "summary: Summary text.\n"
            "supersedes: knowledge/decisions/DEC-010/2026-01-01.md\n"
            "---\n",
            encoding="utf-8",
        )

        lint = self.run_kf("lint")
        self.assertNotEqual(lint.returncode, 0)
        combined = lint.stdout + lint.stderr
        self.assertIn("no active head", combined)
        self.assertIn("retracted guidance requires retracted_at and retraction_reason", combined)
        self.assertIn("knowledge/decisions/DEC-010.md", combined)
        self.assertIn("supersedes target does not exist", combined)


if __name__ == "__main__":
    unittest.main()
