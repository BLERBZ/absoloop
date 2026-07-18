"""Tests for AbsoLoop mission report Markdown + lite HTML viewer."""
from __future__ import annotations

import base64
import json
import tempfile
import unittest
from pathlib import Path

from tests._load import REPO, load_cli

import sys

sys.path.insert(0, str(REPO))
from absoloop_harness import report_doc  # noqa: E402

# 1x1 PNG
_TINY_PNG = base64.standard_b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


def _seed_mission(root: Path) -> Path:
    abs_dir = root / ".absoloop"
    abs_dir.mkdir(parents=True)
    tmp = abs_dir / "tmp"
    tmp.mkdir(parents=True)
    evidence_png = root / "qa-frame.png"
    evidence_png.write_bytes(_TINY_PNG)
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
            "changed_artifacts": [
                "parser.py",
                "tests/test_parser.py",
                "qa-frame.png",
            ],
            "commands_run": ["pytest tests/test_parser.py -q (8 passed)"],
            "risks": ["No integration coverage for streaming input."],
            "evidence": ["qa-frame.png"],
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
    return evidence_png


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
            self.assertEqual(report.highlights[1].evidence, ["qa-frame.png"])
            self.assertEqual(report.highlights[2].recommendation, "PASS")
            titles = [t.title for t in report.timeline]
            self.assertTrue(any("Builder" in t and "Iteration 1" in t for t in titles))
            self.assertTrue(any("Critic" in t and "PASS" in t for t in titles))
            # Noisy "Still in progress" iteration rows are collapsed away.
            self.assertFalse(any(t == "Iteration 1" for t in titles))
            md = report_doc.render_markdown(report)
            self.assertIn("# AbsoLoop Report", md)
            self.assertIn("## Outcome", md)
            self.assertIn("## What shipped", md)
            self.assertIn("## Evidence", md)
            self.assertIn("## Builder work", md)
            self.assertIn("## Critic", md)
            self.assertIn("## Mission ops", md)
            self.assertIn("qa-frame.png", md)
            self.assertIn("Make the parser stop crashing", md)
            self.assertIn("Hardened empty-input path", md)
            self.assertIn("parser.py", md)
            self.assertIn("Verdict", md)
            self.assertIn("absoloop approve", md)
            # Full procedural summary wall should not dump iter-1 prose body.
            self.assertNotIn("Tests still failing on nested blanks.", md)
            self.assertNotIn("## Builder highlights", md)
            self.assertNotIn("## At a glance", md)
            self.assertNotIn("## Pointers", md)

    def test_html_viewer_results_first(self):
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
            self.assertIn("What shipped", page)
            self.assertIn("Evidence", page)
            self.assertIn("Builder work", page)
            self.assertIn("Mission ops", page)
            self.assertIn("ops-details", page)
            self.assertIn("evidence-grid", page)
            self.assertIn("hl-card", page)
            self.assertIn("Skills", page)
            self.assertIn("class=\"bar\"", page)
            self.assertIn("donut-svg", page)
            self.assertIn("Budget mix", page)
            self.assertIn("Outcomes", page)
            self.assertIn("Iteration spend", page)
            self.assertNotIn("Run heatmap", page)
            self.assertNotIn('class="heatmap"', page)
            self.assertNotIn(">Tasks<", page)
            self.assertIn("Hardened empty-input path", page)
            self.assertIn("AbsoLoop", page)
            self.assertIn('class="brand-logo"', page)
            self.assertIn("brand-name", page)
            self.assertIn("data:image/png;base64,", page)
            self.assertIn("data:image/jpeg;base64,", page)
            self.assertNotIn("<strong>Absoloop</strong>", page)
            # Full summary body should not appear on builder cards.
            self.assertNotIn("Tests still failing on nested blanks.", page)

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

    def test_artifact_first_changed_files_when_git_noisy(self):
        highlights = [
            report_doc.AgentHighlight(
                ts=1, role="builder", iteration=1, engine="claude",
                headline="x", summary="x", status_label="Done claimed", tone="ok",
                artifacts=["out/video.mp4", "out/q-intro.png"],
                evidence=["out/q-intro.png"],
            )
        ]
        noisy = [f"home-file-{i}.txt" for i in range(50)]
        selected = report_doc._select_changed_files(noisy, highlights)
        self.assertIn("out/video.mp4", selected)
        self.assertNotIn("home-file-0.txt", selected)

    def test_write_report_docs(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            _seed_mission(root)
            written = report_doc.write_report_docs(root)
            self.assertIsNotNone(written)
            assert written is not None
            self.assertTrue(written.markdown_path.is_file())
            self.assertTrue(written.html_path.is_file())
            md = written.markdown_path.read_text(encoding="utf-8")
            self.assertIn("AbsoLoop Report", md)
            self.assertIn("## Outcome", md)
            html = written.html_path.read_text(encoding="utf-8")
            self.assertIn("AbsoLoop", html)
            self.assertIn("data:image/png;base64,", html)
            self.assertIn("report.md", html)
            self.assertIn("hl-card", html)
            self.assertIn("evidence-grid", html)

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

    def test_results_sections_refresh_after_extension(self):
        """Evidence / shipped / builder / critic must reflect the current run only."""
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            abs_dir = root / ".absoloop"
            abs_dir.mkdir(parents=True)
            tmp_dir = abs_dir / "tmp"
            tmp_dir.mkdir()
            old_png = root / "old-frame.png"
            new_png = root / "new-frame.png"
            old_png.write_bytes(_TINY_PNG)
            new_png.write_bytes(_TINY_PNG)
            (abs_dir / "runtime.json").write_text(json.dumps({
                "mission_id": "m-extend",
                "loop_id": "loop-new",
                "objective": "Refresh report evidence after extend",
                "engine": "claude",
                "max_iterations": 5,
                "max_cost_usd": 10.0,
                "max_wall_seconds": 600,
                "delivery": {"mode": "local"},
            }, indent=2) + "\n", encoding="utf-8")
            (abs_dir / "state.json").write_text(json.dumps({
                "mission_id": "m-extend",
                "status": "AWAITING_APPROVAL",
                "stop_reason": "builder done + critic PASS",
                "iteration": 1,
                "cost_usd": 0.5,
                "latest_agent_result": ".absoloop/tmp/iteration-0001-agent-result.json",
                "latest_critic_findings": ".absoloop/tmp/iteration-0001-critic.json",
            }, indent=2) + "\n", encoding="utf-8")
            (tmp_dir / "prior-loop-agent-result.json").write_text(json.dumps({
                "structured_output": {
                    "done": True,
                    "summary": "Prior-run work that must not appear in results.",
                    "changed_artifacts": ["legacy/shipped.py", "old-frame.png"],
                    "commands_run": ["pytest -q"],
                    "evidence": ["old-frame.png"],
                },
            }), encoding="utf-8")
            (tmp_dir / "prior-loop-critic.json").write_text(json.dumps({
                "structured_output": {
                    "recommendation": "PASS",
                    "blocking_findings": ["stale prior finding"],
                    "summary": "Prior critic must not win.",
                },
            }), encoding="utf-8")
            (tmp_dir / "iteration-0001-agent-result.json").write_text(json.dumps({
                "structured_output": {
                    "done": True,
                    "summary": "Current-run deliverable with fresh evidence.",
                    "changed_artifacts": ["fresh/shipped.py", "new-frame.png"],
                    "commands_run": ["pytest tests/test_fresh.py -q"],
                    "evidence": ["new-frame.png"],
                },
            }), encoding="utf-8")
            (tmp_dir / "iteration-0001-critic.json").write_text(json.dumps({
                "structured_output": {
                    "recommendation": "PASS",
                    "blocking_findings": [],
                    "summary": "Current critic accepts the new evidence.",
                },
            }), encoding="utf-8")
            ledger = [
                {"type": "agent_run", "ts": 1700000000, "engine": "claude",
                 "exit_code": 0, "cost_usd": 0.9, "wall_seconds": 30,
                 "result": ".absoloop/tmp/prior-loop-agent-result.json"},
                {"type": "agent_run", "ts": 1700000100, "engine": "claude",
                 "exit_code": 0, "cost_usd": 0.2, "wall_seconds": 10,
                 "result": ".absoloop/tmp/prior-loop-critic.json"},
                {"type": "mission_stop", "ts": 1700000200,
                 "status": "COMPLETED", "reason": "approved"},
                {"type": "extension", "ts": 1700000300,
                 "previous_loop_id": "loop-old", "loop_id": "loop-new",
                 "note": "refresh evidence"},
                {"type": "agent_run", "ts": 1700000400, "engine": "claude",
                 "exit_code": 0, "cost_usd": 0.4, "wall_seconds": 20,
                 "result": ".absoloop/tmp/iteration-0001-agent-result.json"},
                {"type": "agent_run", "ts": 1700000500, "engine": "claude",
                 "exit_code": 0, "cost_usd": 0.1, "wall_seconds": 8,
                 "result": ".absoloop/tmp/iteration-0001-critic.json"},
            ]
            (abs_dir / "ledger.jsonl").write_text(
                "\n".join(json.dumps(e) for e in ledger) + "\n", encoding="utf-8")

            report = report_doc.collect_report(root)
            assert report is not None
            evidence = report_doc._collect_evidence_images(report.highlights)
            shipped = report_doc._shipped_artifacts(report.highlights)
            self.assertEqual(evidence, ["new-frame.png"])
            self.assertNotIn("old-frame.png", evidence)
            self.assertEqual(shipped, ["fresh/shipped.py"])
            self.assertNotIn("legacy/shipped.py", shipped)
            self.assertEqual(len(report.highlights), 2)
            self.assertTrue(all(
                "prior" not in (h.result_path or "") for h in report.highlights
            ))
            critic = report_doc._latest_critic(report)
            assert critic is not None
            self.assertEqual(critic.blocking_findings, [])
            self.assertIn("Current critic", critic.summary)

            md = report_doc.render_markdown(report)
            results_md = md.split("## Mission ops", 1)[0]
            self.assertIn("new-frame.png", results_md)
            self.assertNotIn("old-frame.png", results_md)
            self.assertIn("fresh/shipped.py", results_md)
            self.assertNotIn("legacy/shipped.py", results_md)
            self.assertIn("Current-run deliverable", results_md)
            self.assertNotIn("Prior-run work that must not appear", results_md)
            self.assertNotIn("stale prior finding", results_md)
            # Full mission arc under Mission ops may retain prior history.
            self.assertIn("Mission extended", md)

            html = report_doc.render_html(report)
            self.assertIn("new-frame.png", html)
            self.assertNotIn("old-frame.png", html)


if __name__ == "__main__":
    unittest.main()
