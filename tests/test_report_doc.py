"""Tests for AbsoLoop mission report Markdown + lite HTML viewer."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from tests._load import REPO, load_cli

import sys

sys.path.insert(0, str(REPO))
from absoloop_harness import report_doc  # noqa: E402


def _seed_mission(root: Path) -> None:
    abs_dir = root / ".absoloop"
    abs_dir.mkdir(parents=True)
    tmp = abs_dir / "tmp"
    tmp.mkdir(parents=True)
    (abs_dir / "runtime.json").write_text(json.dumps({
        "mission_id": "m-test",
        "loop_id": "loop-abc",
        "objective": "Make the parser stop crashing on empty input",
        "engine": "claude",
        "max_iterations": 5,
        "max_cost_usd": 10.0,
        "max_wall_seconds": 600,
        "delivery": {"mode": "local"},
    }, indent=2) + "\n", encoding="utf-8")
    (abs_dir / "state.json").write_text(json.dumps({
        "mission_id": "m-test",
        "status": "AWAITING_APPROVAL",
        "stop_reason": "builder done + critic PASS",
        "iteration": 2,
        "cost_usd": 1.25,
        "tokens_total": {"input": 1000, "output": 400, "total": 1400},
        "latest_agent_result": ".absoloop/tmp/iteration-0002-agent-result.json",
        "latest_critic_findings": ".absoloop/tmp/iteration-0002-critic.json",
    }, indent=2) + "\n", encoding="utf-8")
    (tmp / "iteration-0001-agent-result.json").write_text(json.dumps({
        "structured_output": {
            "done": False,
            "summary": (
                "Added empty-input guard in parser.py. "
                "Tests still failing on nested blanks."
            ),
            "changed_artifacts": ["parser.py", "tests/test_parser.py"],
            "commands_run": ["pytest tests/test_parser.py -q (2 failed)"],
            "risks": ["Nested blank tokens still crash."],
        },
    }), encoding="utf-8")
    (tmp / "iteration-0002-agent-result.json").write_text(json.dumps({
        "structured_output": {
            "done": True,
            "summary": "Hardened empty-input path; tests green.",
            "changed_artifacts": ["parser.py", "tests/test_parser.py"],
            "commands_run": ["pytest tests/test_parser.py -q (8 passed)"],
            "risks": ["No integration coverage for streaming input."],
        },
    }), encoding="utf-8")
    (tmp / "iteration-0002-critic.json").write_text(json.dumps({
        "structured_output": {
            "recommendation": "PASS",
            "blocking_findings": [],
            "summary": "Diff is tight; empty-input path is covered.",
        },
    }), encoding="utf-8")
    ledger = [
        {"type": "agent_run", "ts": 1700000000, "engine": "claude",
         "exit_code": 0, "cost_usd": 0.45, "cost_is_exact": True,
         "tokens": {"total": 500}, "wall_seconds": 20,
         "result": ".absoloop/tmp/iteration-0001-agent-result.json"},
        {"type": "iteration", "ts": 1700000020, "iteration": 1, "done": False},
        {"type": "agent_run", "ts": 1700000040, "engine": "claude",
         "exit_code": 0, "cost_usd": 0.8, "cost_is_exact": True,
         "tokens": {"total": 900}, "wall_seconds": 40,
         "result": ".absoloop/tmp/iteration-0002-agent-result.json"},
        {"type": "iteration", "ts": 1700000080, "iteration": 2, "done": True},
        {"type": "integrity_check", "ts": 1700000090, "exit_code": 0},
        {"type": "agent_run", "ts": 1700000100, "engine": "claude",
         "exit_code": 0, "cost_usd": 0.3, "cost_is_exact": True,
         "tokens": {"total": 400}, "wall_seconds": 15,
         "result": ".absoloop/tmp/iteration-0002-critic.json"},
        {"type": "mission_stop", "ts": 1700000120,
         "status": "AWAITING_APPROVAL", "reason": "builder done + critic PASS"},
    ]
    (abs_dir / "ledger.jsonl").write_text(
        "\n".join(json.dumps(e) for e in ledger) + "\n", encoding="utf-8")


class ReportDocTests(unittest.TestCase):
    def test_collect_and_render_markdown(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            report = report_doc.collect_report(root)
            self.assertIsNotNone(report)
            assert report is not None
            self.assertEqual(report.status, "AWAITING_APPROVAL")
            self.assertEqual(report.status_label, "Needs review")
            self.assertEqual(report.agent_runs, 3)
            self.assertTrue(report.integrity_ok)
            self.assertEqual(len(report.highlights), 3)
            roles = [h.role for h in report.highlights]
            self.assertEqual(roles, ["builder", "builder", "critic"])
            self.assertEqual(report.highlights[1].done, True)
            self.assertEqual(report.highlights[2].recommendation, "PASS")
            titles = [t.title for t in report.timeline]
            self.assertTrue(any("Builder" in t and "Iteration 1" in t for t in titles))
            self.assertTrue(any("Critic" in t and "PASS" in t for t in titles))
            # Noisy "Still in progress" iteration rows are collapsed away.
            self.assertFalse(any(t == "Iteration 1" for t in titles))
            md = report_doc.render_markdown(report)
            self.assertIn("# AbsoLoop Report", md)
            self.assertIn("At a glance", md)
            self.assertIn("Run arc", md)
            self.assertIn("## Builder highlights", md)
            self.assertIn("## Skills", md)
            self.assertIn("Make the parser stop crashing", md)
            self.assertIn("Hardened empty-input path", md)
            self.assertIn("Verified commands", md)
            self.assertIn("pytest tests/test_parser.py", md)
            self.assertIn("Verdict", md)
            self.assertIn("absoloop approve", md)

    def test_html_viewer_contains_infographic_pieces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            report = report_doc.collect_report(root)
            assert report is not None
            page = report_doc.render_html(report)
            self.assertIn("<!DOCTYPE html>", page)
            self.assertIn("report-mark", page)
            self.assertIn("R E P O R T", page)
            self.assertIn("Needs review", page)
            self.assertNotIn("status-pill", page)
            self.assertNotIn("mission report", page.lower())
            self.assertIn("Run arc", page)
            self.assertIn("Builder highlights", page)
            self.assertIn("hl-card", page)
            self.assertIn("Skills", page)
            self.assertIn("class=\"bar\"", page)
            self.assertIn("donut-svg", page)
            self.assertIn("Budget mix", page)
            self.assertIn("Outcomes", page)
            self.assertIn("heatmap", page)
            self.assertIn("Iteration spend", page)
            self.assertIn("summary-grid", page)
            self.assertIn(">Tasks<", page)
            self.assertIn(">Decisions<", page)
            self.assertIn(">Results<", page)
            self.assertNotIn("treemap", page)
            self.assertIn("Hardened empty-input path", page)
            self.assertIn("AbsoLoop", page)
            self.assertIn('class="brand-logo"', page)
            self.assertIn("brand-name", page)
            self.assertIn("data:image/png;base64,", page)
            self.assertNotIn("<strong>Absoloop</strong>", page)

    def test_skills_split_from_changed_files(self):
        files, skills = report_doc._split_files_and_skills([
            "src/main.py",
            ".claude/skills/tdd/",
            ".claude/skills/tdd/SKILL.md",
            ".codex/skills/tdd/",
            ".codex/skills/frontend-design/SKILL.md",
            "README.md",
        ])
        self.assertEqual(files, ["src/main.py", "README.md"])
        names = [s.name for s in skills]
        self.assertEqual(names, ["frontend-design", "tdd"])
        tdd = next(s for s in skills if s.name == "tdd")
        self.assertEqual(sorted(tdd.engines), ["claude", "codex"])

    def test_write_report_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            written = report_doc.write_report_docs(root)
            self.assertIsNotNone(written)
            assert written is not None
            self.assertTrue(written.markdown_path.is_file())
            self.assertTrue(written.html_path.is_file())
            self.assertIn("AbsoLoop Report", written.markdown_path.read_text(encoding="utf-8"))
            html = written.html_path.read_text(encoding="utf-8")
            self.assertIn("AbsoLoop", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertIn("report.md", html)
            self.assertIn("hl-card", html)

    def test_write_md_only_skips_html(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            written = report_doc.write_report_docs(root, write_html=False)
            assert written is not None
            self.assertTrue(written.markdown_path.is_file())
            self.assertFalse(written.html_path.is_file())

    def test_cli_report_no_open(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            code = cli.report_command(["-C", str(root), "--no-open"])
            self.assertEqual(code, 0)
            self.assertTrue((root / ".absoloop" / "report.md").is_file())
            self.assertTrue((root / ".absoloop" / "report.html").is_file())

    def test_cli_report_missing_project(self):
        cli = load_cli()
        with tempfile.TemporaryDirectory() as tmp:
            code = cli.report_command(["-C", tmp, "--no-open"])
            self.assertEqual(code, 1)


if __name__ == "__main__":
    unittest.main()
