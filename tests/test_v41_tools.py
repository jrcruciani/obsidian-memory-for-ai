"""Offline acceptance and regression tests for the additive v4.1 vault."""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import yaml


REPO = Path(__file__).resolve().parents[1]
EXAMPLE = REPO / "examples/v4.1-minimal-vault"
ADMIN = "agent-human-00000001"
AGENT = "agent-local-1234abcd"
ROLE = "memory/facts/elena-voss/role.md"
BASE = "memory/facts/elena-voss/base.md"
EVIDENCE = "memory/events/2026-07-15/role-confirmation.md"


class V41Test(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.vault = Path(self.tmp.name) / "vault"
        shutil.copytree(EXAMPLE, self.vault, ignore=shutil.ignore_patterns(".venv", "__pycache__", "_staging"))
        self.env = dict(os.environ, MEMORY_TODAY="2026-09-21")
        self.env["PATH"] = f"{Path(sys.executable).parent}{os.pathsep}{self.env.get('PATH', '')}"

    def run_tool(self, tool: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        command = ["sh", "tools/query.sh"] if tool == "query" else [sys.executable, f"tools/{tool}.py"]
        result = subprocess.run([*command, *args], cwd=self.vault, env=self.env, text=True, capture_output=True)
        if ok:
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        else:
            self.assertNotEqual(result.returncode, 0, result.stdout + result.stderr)
        return result

    def code(self, source: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        result = subprocess.run([sys.executable, "-c", "import sys; sys.path.insert(0, 'tools'); " + source],
                                cwd=self.vault, env=self.env, text=True, capture_output=True)
        self.assertEqual(result.returncode == 0, ok, result.stdout + result.stderr)
        return result

    def data(self, relative: str) -> dict:
        return yaml.safe_load((self.vault / relative).read_text(encoding="utf-8").split("---", 2)[1])

    def edit(self, relative: str, **fields) -> None:
        path = self.vault / relative
        _, fm, body = path.read_text(encoding="utf-8").split("---", 2)
        data = yaml.safe_load(fm)
        data.update(fields)
        path.write_text("---\n" + yaml.safe_dump(data, sort_keys=False) + "---" + body, encoding="utf-8")

    def begin(self, key: str = "test-change", agent: str = AGENT) -> str:
        result = self.run_tool("transact", "begin", "--idempotency-key", key, "--agent", agent)
        return result.stdout.strip().split(": ", 1)[1]

    def add(self, txn: str, *args: str, ok: bool = True) -> subprocess.CompletedProcess[str]:
        return self.run_tool("transact", "add", "--txn-id", txn, *args, ok=ok)

    def supersede(self, value: str, date: str, key: str) -> str:
        txn = self.begin(key)
        self.add(txn, "--op", "supersede_fact", "--entity", "elena-voss", "--predicate", "role",
                 "--value", value, "--valid-from", date)
        self.run_tool("transact", "commit", "--txn-id", txn, "--yes")
        return txn

    def proposal(self, *args: str) -> str:
        result = self.run_tool("propose", "create", "--title", "Test fact", "--namespace", "facts",
                               "--proposer", AGENT, "--op", "create_fact", "--entity", "elena-voss",
                               "--predicate", "tool", "--value", "Offline notebook", *args)
        return result.stdout.strip().split(": ", 1)[1]

    def approve(self, prop: str) -> None:
        self.run_tool("review", "approve", "--proposal-id", prop, "--reviewer", ADMIN)

    def test_clean_reference(self):
        self.run_tool("lint")

    def test_v40_unchanged_vault_with_new_tools(self):
        legacy = REPO / "examples/v4-minimal-vault/memory"
        shutil.rmtree(self.vault / "memory")
        shutil.copytree(legacy, self.vault / "memory")
        self.run_tool("lint")

    def test_v40_lint_ignores_new_rules(self):
        marker = self.vault / "memory/schema/version.yaml"
        marker.write_text('spec_version: "4.0"\nschema_status: stable\n')
        shutil.rmtree(self.vault / "memory/facts/elena-voss/role")
        self.edit(BASE, trust="not-a-trust", pinned="not-a-bool", confidence="high")
        self.edit(ROLE, confidence="high")
        self.run_tool("lint")

    def test_supersede_twice_and_as_of(self):
        self.supersede("Research director", "2026-08-01", "second-role")
        self.supersede("Independent researcher", "2026-09-01", "third-role")
        for date, expected in (("2026-07-20", "Lead conservator"), ("2026-08-20", "Research director"),
                               ("2026-09-20", "Independent researcher")):
            text = self.run_tool("query", "facts", "--entity", "elena-voss", "--predicate", "role", "--as-of", date).stdout
            self.assertIn(expected, text)
            self.assertEqual(len(text.strip().splitlines()), 1)
        self.assertEqual(len(list((self.vault / "memory/facts/elena-voss/role").glob("*.md"))), 3)
        self.run_tool("lint")

    def test_as_of_exact_boundary_is_new_value(self):
        text = self.run_tool("query", "facts", "--entity", "elena-voss", "--predicate", "role", "--as-of", "2026-07-15").stdout
        self.assertIn("Lead conservator", text)
        self.assertNotIn("Art conservator", text)

    def test_history_order(self):
        self.supersede("Research director", "2026-08-01", "order")
        text = self.run_tool("query", "facts", "--entity", "elena-voss", "--predicate", "role", "--history").stdout
        self.assertLess(text.index("Art conservator"), text.index("Lead conservator"))
        self.assertLess(text.index("Lead conservator"), text.index("Research director"))

    def test_duplicate_current_fails(self):
        copy = self.vault / "memory/facts/elena-voss/base--duplicate.md"
        shutil.copyfile(self.vault / BASE, copy)
        self.edit(str(copy.relative_to(self.vault)), id="fact-duplicate")
        self.assertIn("exactly one current", self.run_tool("lint", ok=False).stdout)

    def test_inverted_interval_fails(self):
        self.edit(ROLE, valid_from="2026-12-01", valid_until="2026-01-01")
        self.run_tool("lint", ok=False)

    def test_missing_supersedes_fails(self):
        self.edit(ROLE, supersedes="memory/facts/elena-voss/role/missing.md")
        self.assertIn("supersedes path", self.run_tool("lint", ok=False).stdout)

    def test_one_day_boundary_is_warning(self):
        previous = self.data(ROLE)["supersedes"]
        self.edit(previous, valid_until="2026-07-16")
        self.assertIn("WARN", self.run_tool("lint").stdout)

    def test_large_boundary_gap_fails(self):
        self.edit(self.data(ROLE)["supersedes"], valid_until="2026-07-10")
        self.run_tool("lint", ok=False)

    def test_history_name_collision_suffix(self):
        self.supersede("Same-day appointment", "2026-07-15", "same-day-one")
        self.supersede("Later same-day appointment", "2026-07-15", "same-day-two")
        self.assertTrue((self.vault / "memory/facts/elena-voss/role/2026-07-15-2.md").exists())
        self.run_tool("lint")

    def test_idempotent_supersession(self):
        self.supersede("Research director", "2026-08-01", "once")
        before = (self.vault / ROLE).read_bytes()
        self.assertIn("Idempotent skip", self.run_tool("transact", "begin", "--idempotency-key", "once", "--agent", AGENT).stdout)
        self.assertEqual((self.vault / ROLE).read_bytes(), before)

    def test_changed_precondition_refused(self):
        txn = self.begin()
        self.add(txn, "--op", "supersede_fact", "--entity", "elena-voss", "--predicate", "role",
                 "--value", "Director", "--valid-from", "2026-08-01")
        self.edit(ROLE, value="Owner edited this")
        self.run_tool("transact", "commit", "--txn-id", txn, "--yes", ok=False)
        self.assertEqual(self.data(ROLE)["value"], "Owner edited this")

    def test_multi_op_failure_leaves_no_partial_history(self):
        txn = self.begin()
        self.add(txn, "--op", "supersede_fact", "--entity", "elena-voss", "--predicate", "role",
                 "--value", "Director", "--valid-from", "2026-08-01")
        self.add(txn, "--op", "create_fact", "--entity", "ghost", "--predicate", "tool", "--value", "x")
        self.run_tool("transact", "commit", "--txn-id", txn, "--yes", ok=False)
        self.assertIn("Lead conservator", self.data(ROLE)["value"])
        self.assertFalse((self.vault / "memory/facts/ghost/tool.md").exists())

    def test_recovery_restores_preimage(self):
        original = (self.vault / BASE).read_bytes()
        self.code("from pathlib import Path; import transact; "
                  "r=Path.cwd(); m=transact.begin(r,'crash-test','agent-local-1234abcd'); "
                  "original=transact.write_journal; "
                  "transact.write_journal=lambda *a,**k: (_ for _ in ()).throw(SystemExit(99)); "
                  "transact.publish(r,m,{'memory/facts/elena-voss/base.md':'interrupted write\\n'})", ok=False)
        self.assertNotEqual((self.vault / BASE).read_bytes(), original)
        self.run_tool("transact", "recover", "--yes")
        self.assertEqual((self.vault / BASE).read_bytes(), original)

    def test_update_cannot_overwrite_history(self):
        txn = self.begin()
        self.add(txn, "--op", "update_fact", "--entity", "elena-voss", "--predicate", "role", "--value", "Overwrite", ok=False)

    def test_lineage_why(self):
        text = self.run_tool("query", "facts", "--why", "elena-voss", "role").stdout
        self.assertIn(EVIDENCE, text)
        self.assertIn("Elena confirmed", text)
        self.assertIn("2026-07-15", text)

    def test_confidence_bounds(self):
        for bad in (-0.1, 1.1, float("nan"), True, "guessed"):
            with self.subTest(bad=bad):
                self.edit(BASE, confidence=bad)
                self.run_tool("lint", ok=False)

    def test_lineage_warnings(self):
        self.edit(BASE, assertion="inferred", trust="external", confidence=None, derived_from=[])
        text = self.run_tool("lint").stdout
        self.assertIn("inferred fact", text)
        self.assertIn("external fact", text)

    def test_missing_evidence_fails(self):
        self.edit(BASE, derived_from=["sources/missing.md"])
        self.run_tool("lint", ok=False)

    def test_external_direct_commit_refused(self):
        txn = self.begin()
        self.add(txn, "--op", "create_fact", "--entity", "elena-voss", "--predicate", "tool",
                 "--value", "Notebook", "--trust", "external", "--confidence", "0.8")
        result = self.run_tool("transact", "commit", "--txn-id", txn, "--yes", ok=False)
        self.assertIn("propose.py", result.stderr)

    def test_proposer_cannot_assert_owner(self):
        txn = self.begin()
        self.add(txn, "--op", "create_fact", "--entity", "elena-voss", "--predicate", "tool",
                 "--value", "Notebook", "--trust", "owner", ok=False)

    def test_proposal_apply_enforces_trust_cap(self):
        prop = self.proposal("--trust", "owner")
        self.approve(prop)
        self.assertIn("cannot assert trust", self.run_tool("propose", "apply", "--proposal-id", prop, "--yes", ok=False).stderr)

    def test_reviewed_external_fact_allowed(self):
        prop = self.proposal("--trust", "external", "--confidence", "0.8", "--derived-from", EVIDENCE)
        self.approve(prop)
        self.run_tool("propose", "apply", "--proposal-id", prop, "--yes")
        self.assertEqual(self.data("memory/facts/elena-voss/tool.md")["trust"], "external")
        self.run_tool("lint")

    def test_tampered_approved_proposal_refused(self):
        prop = self.proposal("--trust", "external")
        self.approve(prop)
        relative = f"memory/_proposals/{prop}.md"
        ops = self.data(relative)["ops"]
        ops[0]["value"] = "Tampered"
        self.edit(relative, ops=ops)
        self.run_tool("propose", "apply", "--proposal-id", prop, "--yes", ok=False)

    def test_forged_approval_list_refused(self):
        prop = self.proposal()
        self.edit(f"memory/_proposals/{prop}.md", status="approved", approvals=[ADMIN])
        self.run_tool("propose", "apply", "--proposal-id", prop, "--yes", ok=False)

    def test_numeric_confidence_filter(self):
        self.edit(BASE, confidence=0.75, trust="external")
        text = self.run_tool("query", "facts", "--trust", "external", "--min-confidence", "0.7").stdout
        self.assertIn("Berlin", text)
        self.assertNotIn("role =", text)

    def test_index_history_and_determinism(self):
        self.run_tool("rebuild_indexes")
        path = self.vault / "memory/_indexes/lexical.md"
        first = path.read_bytes()
        self.assertIn(b"## History", first)
        self.run_tool("rebuild_indexes")
        self.assertEqual(first, path.read_bytes())

    def test_entity_timeline(self):
        self.run_tool("rebuild_views")
        text = (self.vault / "memory/_views/by-entity/elena-voss.md").read_text()
        self.assertIn("## Timeline", text)
        self.assertIn("Art conservator", text)

    def test_sources_and_events_remain_immutable(self):
        before = {p.relative_to(self.vault): p.read_bytes() for folder in ("sources", "memory/events")
                  for p in (self.vault / folder).rglob("*.md")}
        self.supersede("Director", "2026-08-01", "immutable")
        for relative, content in before.items():
            self.assertEqual((self.vault / relative).read_bytes(), content)

    def test_create_event_cannot_replace_existing(self):
        txn = self.begin()
        self.add(txn, "--op", "create_event", "--event-id", "role-confirmation",
                 "--occurred-at", "2026-07-15T10:00:00Z", "--summary", "Replacement", ok=False)

    def test_event_and_fact_in_one_transaction(self):
        txn = self.begin()
        self.add(txn, "--op", "create_event", "--event-id", "test-session",
                 "--occurred-at", "2026-09-21T10:00:00Z", "--summary", "Notebook selected",
                 "--entities", "elena-voss")
        self.add(txn, "--op", "create_fact", "--entity", "elena-voss", "--predicate", "tool",
                 "--value", "Notebook", "--derived-from", "memory/events/2026-09-21/test-session.md",
                 "--assertion", "observed", "--confidence", "1")
        self.run_tool("transact", "commit", "--txn-id", txn, "--yes")
        self.run_tool("lint")

    def test_resolve_case_and_accents(self):
        for name in ("ELENA", "Voss", "ÉLÉNA VOSS", "elena-voss"):
            self.assertEqual(self.run_tool("query", "resolve", name).stdout.strip(), "elena-voss")

    def test_resolve_unknown_exit_two(self):
        self.assertEqual(self.run_tool("query", "resolve", "Missing", ok=False).returncode, 2)

    def test_alias_collision_error(self):
        data = self.data("memory/entities.md")["entities"]
        data[1]["aliases"] = ["ÉLÉNA"]
        self.edit("memory/entities.md", entities=data)
        self.assertIn("alias collision", self.run_tool("lint", ok=False).stdout)

    def test_alias_collides_with_id(self):
        data = self.data("memory/entities.md")["entities"]
        data[1]["aliases"] = ["ELENA-VOSS"]
        self.edit("memory/entities.md", entities=data)
        self.run_tool("lint", ok=False)

    def test_ambiguous_resolve_lists_candidates(self):
        data = self.data("memory/entities.md")["entities"]
        data[1]["aliases"] = ["Elena"]
        self.edit("memory/entities.md", entities=data)
        result = self.run_tool("query", "resolve", "elena", ok=False)
        self.assertEqual(result.returncode, 2)
        self.assertEqual(result.stdout.splitlines(), ["concordance", "elena-voss"])

    def test_alias_search_same_top_hit(self):
        a = self.run_tool("query", "search", "elena").stdout
        b = self.run_tool("query", "search", "Voss").stdout
        self.assertEqual(a, b)
        self.assertTrue(a.startswith("elena-voss/base"))

    def test_search_ranking_entity_value_body(self):
        self.edit("memory/facts/concordance/collaborator.md", value="Voss")
        path = self.vault / "memory/facts/strata/publication-channel.md"
        path.write_text(path.read_text() + "\nVoss is mentioned only in this body.\n")
        text = self.run_tool("query", "search", "Voss").stdout
        self.assertLess(text.index("elena-voss/base"), text.index("concordance/collaborator"))
        self.assertLess(text.index("concordance/collaborator"), text.index("strata/publication-channel"))

    def test_search_missing_stale_corrupt_parity(self):
        self.run_tool("rebuild_indexes")
        expected = self.run_tool("query", "search", "elena").stdout
        path = self.vault / "memory/_indexes/lexical.md"
        for content in ("# Stale index\n", "\ufffd corrupt\n"):
            path.write_text(content)
            result = self.run_tool("query", "search", "elena")
            self.assertEqual(result.stdout, expected)
            self.assertIn("WARNING", result.stderr)
        path.unlink()
        self.assertEqual(self.run_tool("query", "search", "elena").stdout, expected)

    def test_empty_search_parity(self):
        expected = self.run_tool("query", "search", "not-in-the-vault").stdout
        shutil.rmtree(self.vault / "memory/_indexes")
        self.assertEqual(expected, self.run_tool("query", "search", "not-in-the-vault").stdout)

    def test_graph_stale_and_missing_parity(self):
        self.run_tool("rebuild_indexes")
        expected = self.run_tool("query", "graph", "entity", "concordance").stdout
        path = self.vault / "memory/_indexes/graph.md"
        path.write_text("# Bogus graph\n")
        self.assertEqual(expected, self.run_tool("query", "graph", "entity", "concordance").stdout)
        path.unlink()
        self.assertEqual(expected, self.run_tool("query", "graph", "entity", "concordance").stdout)

    def test_aliases_in_index(self):
        self.run_tool("rebuild_indexes")
        text = (self.vault / "memory/_indexes/lexical.md").read_text()
        self.assertIn("## Aliases", text)
        self.assertIn("Voss", text)

    def test_bootstrap_under_budget_with_accurate_footer(self):
        self.run_tool("rebuild_views")
        text = (self.vault / "memory/_views/bootstrap.md").read_text()
        match = re.search(r"bootstrap: (\d+) items, (\d+)/(\d+) chars", text)
        self.assertIsNotNone(match)
        self.assertEqual(len(text), int(match[2]))
        self.assertLessEqual(len(text), int(match[3]))
        self.assertIn("generated 2026-09-21", text)

    def test_bootstrap_pinned_first(self):
        text = self.run_tool("query", "bootstrap").stdout
        self.assertLess(text.index("## Pinned facts"), text.index("## Recent decisions"))
        self.assertIn("Lead conservator", text)

    def test_bootstrap_regeneration_and_fallback(self):
        self.run_tool("rebuild_views")
        expected = self.run_tool("query", "bootstrap").stdout
        path = self.vault / "memory/_views/bootstrap.md"
        self.assertEqual(path.read_text(), expected)
        path.unlink()
        self.assertEqual(expected, self.run_tool("query", "bootstrap").stdout)
        self.run_tool("rebuild_views")
        self.assertEqual(expected, path.read_text())

    def test_bootstrap_exact_budget(self):
        self.code("from pathlib import Path; import bootstrap, yaml; "
                  "r=Path.cwd(); options=dict(bootstrap.DEFAULTS); "
                  "line=bootstrap.candidates(r,options)['pinned_facts'][0][2]; "
                  "item=[('pinned_facts',line)]; budget=len(bootstrap.render(item,999,bootstrap.today())); "
                  "assert budget==len(bootstrap.render(item,budget,bootstrap.today())); "
                  "(r/'memory/schema/bootstrap.yaml').write_text(yaml.safe_dump({'budget_chars':budget,'sections':['pinned_facts']})); "
                  "text=bootstrap.build_bootstrap(r); assert len(text)==budget; assert '1 items' in text")

    def test_bootstrap_item_over_budget_stops(self):
        self.code("from pathlib import Path; import bootstrap, yaml; "
                  "r=Path.cwd(); line=bootstrap.candidates(r,bootstrap.DEFAULTS)['pinned_facts'][0][2]; "
                  "budget=len(bootstrap.render([('pinned_facts',line)],999,bootstrap.today()))-1; "
                  "(r/'memory/schema/bootstrap.yaml').write_text(yaml.safe_dump({'budget_chars':budget,'sections':['pinned_facts',{'recent_events':10}]})); "
                  "text=bootstrap.build_bootstrap(r); assert len(text)<=budget; assert '0 items' in text")

    def test_bootstrap_missing_config_defaults(self):
        (self.vault / "memory/schema/bootstrap.yaml").unlink()
        self.assertIn("/6000 chars", self.run_tool("query", "bootstrap").stdout)

    def test_bootstrap_impossible_budget_fails(self):
        (self.vault / "memory/schema/bootstrap.yaml").write_text("budget_chars: 1\n")
        self.run_tool("query", "bootstrap", ok=False)

    def test_bootstrap_date_math_and_active_entities(self):
        self.env["MEMORY_TODAY"] = "2026-07-16"
        text = self.run_tool("query", "bootstrap").stdout
        self.assertIn("## Active entities", text)
        self.assertIn("generated 2026-07-16", text)

    def test_stale_review_after_report_and_strict(self):
        self.edit(BASE, review_after="2026-09-20")
        self.assertIn(BASE, self.run_tool("lint", "--stale").stdout)
        self.run_tool("lint", "--stale", "--strict", ok=False)

    def test_stale_last_confirmed_and_configurable_age(self):
        marker = self.vault / "memory/schema/version.yaml"
        marker.write_text(marker.read_text().replace("365", "30"))
        self.edit(BASE, last_confirmed="2026-09-20")
        text = self.run_tool("lint", "--stale").stdout
        self.assertNotIn(BASE, text)
        self.assertIn("role.md", text)

    def test_stale_created_fallback_boundary(self):
        self.edit(BASE, created_at="2025-09-21T00:00:00Z")
        self.assertNotIn(BASE, self.run_tool("lint", "--stale").stdout)
        self.edit(BASE, created_at="2025-09-20T00:00:00Z")
        self.assertIn(BASE, self.run_tool("lint", "--stale").stdout)

    def test_stale_does_not_report_history(self):
        self.env["MEMORY_TODAY"] = "2030-01-01"
        self.assertNotIn("role/2026-03-15.md", self.run_tool("lint", "--stale").stdout)

    def consolidation_drafts(self) -> list[Path]:
        return [path for path in (self.vault / "memory/_proposals").glob("*.md")
                if self.data(str(path.relative_to(self.vault))).get("proposer_id") == "agent-consolidate-00000001"]

    def assert_one_draft(self, title: str) -> None:
        before = {p.relative_to(self.vault): p.read_bytes() for p in (self.vault / "memory").rglob("*.md")
                  if "_proposals" not in p.parts}
        self.run_tool("consolidate")
        drafts = self.consolidation_drafts()
        self.assertEqual(len(drafts), 1)
        data = self.data(str(drafts[0].relative_to(self.vault)))
        self.assertEqual(data["status"], "draft")
        self.assertEqual(data["namespace"], "facts")
        self.assertEqual(data["ops"], [])
        self.assertIn(title, data["title"])
        first = drafts[0].read_bytes()
        self.run_tool("consolidate")
        self.assertEqual(len(self.consolidation_drafts()), 1)
        self.assertEqual(first, drafts[0].read_bytes())
        for path, content in before.items():
            self.assertEqual((self.vault / path).read_bytes(), content)

    def test_consolidate_clean_vault(self):
        self.assertIn("No consolidation issues", self.run_tool("consolidate").stdout)
        self.assertEqual(self.consolidation_drafts(), [])

    def test_consolidate_duplicate_current(self):
        path = self.vault / "memory/facts/elena-voss/base--duplicate.md"
        shutil.copyfile(self.vault / BASE, path)
        self.edit(str(path.relative_to(self.vault)), id="fact-duplicate", value="Paris")
        self.assert_one_draft("Multiple current facts")

    def test_consolidate_newer_assertion(self):
        self.edit(BASE, derived_from=[EVIDENCE])
        # A new fixture event is append-only; it carries a conflicting base claim.
        relative = "memory/events/2026-09-01/base-claim.md"
        path = self.vault / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("---\ntype: event\nid: event-base-claim\nsummary: New base claim\n"
                        "occurred_at: 2026-09-01T00:00:00Z\n"
                        "asserts:\n  - entity: elena-voss\n    predicate: base\n    value: Paris\n---\n")
        self.edit(BASE, derived_from=[relative])
        self.assert_one_draft("Newer evidence contradicts")

    def test_consolidate_expired_current_slot(self):
        self.edit(BASE, valid_until="2026-08-01")
        self.assert_one_draft("Expired fact")

    def test_consolidate_dangling_evidence(self):
        self.edit(BASE, derived_from=["sources/missing.md"])
        self.assert_one_draft("Dangling references")

    def test_consolidate_dangling_wikilink(self):
        path = self.vault / BASE
        path.write_text(path.read_text() + "\n[[unknown-note]]\n")
        self.assert_one_draft("Dangling references")

    def test_consolidate_dry_run_no_writes(self):
        self.edit(BASE, derived_from=["sources/missing.md"])
        self.assertIn("Dangling", self.run_tool("consolidate", "--dry-run").stdout)
        self.assertEqual(self.consolidation_drafts(), [])

    def test_diagnostic_draft_cannot_be_reviewed_or_applied(self):
        self.edit(BASE, derived_from=["sources/missing.md"])
        self.run_tool("consolidate")
        prop = self.data(str(self.consolidation_drafts()[0].relative_to(self.vault)))["proposal_id"]
        self.run_tool("review", "approve", "--proposal-id", prop, "--reviewer", ADMIN, ok=False)
        self.run_tool("propose", "apply", "--proposal-id", prop, "--yes", ok=False)

    def test_malformed_event_asserts_fails_lint(self):
        self.edit(EVIDENCE, asserts=[{"entity": "elena-voss"}])
        self.assertIn("asserts items require", self.run_tool("lint", ok=False).stdout)

    def test_event_asserts_unknown_entity_fails_lint(self):
        self.edit(EVIDENCE, asserts=[{"entity": "ghost", "predicate": "role", "value": "x"}])
        self.run_tool("lint", ok=False)

    def test_compact_cannot_bypass_external_review(self):
        folder = self.vault / "memory/_inbox/agent-local-1234abcd"
        folder.mkdir(parents=True)
        data = {"type": "operation", "operation_id": "op-external-test", "op": "create_fact",
                "agent_id": AGENT, "created_at": "2026-09-21T10:00:00Z", "status": "proposed",
                "reason": "Fixture", "target_path": "memory/facts/elena-voss/tool.md",
                "payload": {"type": "fact", "entity": "elena-voss", "predicate": "tool",
                            "value": "Untrusted notebook", "trust": "external", "recorded_at": "2026-09-21T10:00:00Z"}}
        (folder / "external.md").write_text("---\n" + yaml.safe_dump(data) + "---\n")
        self.assertIn("propose.py", self.run_tool("compact", "--yes", ok=False).stderr)
        self.assertFalse((self.vault / "memory/facts/elena-voss/tool.md").exists())


if __name__ == "__main__":
    unittest.main()
