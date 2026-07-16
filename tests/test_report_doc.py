"""Tests for Absoloop mission report Markdown + lite HTML viewer."""
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
        "latest_agent_result": ".absoloop/iteration-0002-agent-result.json",
        "latest_critic_findings": ".absoloop/iteration-0002-critic.json",
    }, indent=2) + "\n", encoding="utf-8")
    (abs_dir / "iteration-0002-agent-result.json").write_text(json.dumps({
        "structured_output": {"summary": "Hardened empty-input path; tests green."},
    }), encoding="utf-8")
    ledger = [
        {"type": "agent_run", "ts": 1700000000, "engine": "claude",
         "exit_code": 0, "cost_usd": 0.8, "cost_is_exact": True,
         "tokens": {"total": 900}, "wall_seconds": 40,
         "result": ".absoloop/iteration-0002-agent-result.json"},
        {"type": "iteration", "ts": 1700000040, "iteration": 1, "done": False},
        {"type": "iteration", "ts": 1700000100, "iteration": 2, "done": True},
        {"type": "integrity_check", "ts": 1700000110, "exit_code": 0},
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
            self.assertEqual(report.agent_runs, 1)
            self.assertTrue(report.integrity_ok)
            md = report_doc.render_markdown(report)
            self.assertIn("# Absoloop Report", md)
            self.assertIn("At a glance", md)
            self.assertIn("Run arc", md)
            self.assertIn("Make the parser stop crashing", md)
            self.assertIn("Hardened empty-input path", md)
            self.assertIn("absoloop approve", md)

    def test_html_viewer_contains_infographic_pieces(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            report = report_doc.collect_report(root)
            assert report is not None
            page = report_doc.render_html(report)
            self.assertIn("<!DOCTYPE html>", page)
            self.assertIn("status-pill", page)
            self.assertIn("Needs review", page)
            self.assertIn("Run arc", page)
            self.assertIn("class=\"bar\"", page)
            self.assertIn("Hardened empty-input path", page)

    def test_write_report_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            written = report_doc.write_report_docs(root)
            self.assertIsNotNone(written)
            assert written is not None
            self.assertTrue(written.markdown_path.is_file())
            self.assertTrue(written.html_path.is_file())
            self.assertIn("Absoloop Report", written.markdown_path.read_text(encoding="utf-8"))
            html = written.html_path.read_text(encoding="utf-8")
            self.assertIn("Absoloop", html)
            self.assertIn("report.md", html)

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
