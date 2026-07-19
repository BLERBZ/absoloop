"""Mission extend: top-level alias + wall-clock resume guard."""
from __future__ import annotations

import json
import pathlib
import tempfile
import time
import unittest
from unittest import mock

from tests._load import load_cli

cli = load_cli()


def _write(path: pathlib.Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


def _seed_exhausted(project: pathlib.Path, *, reason: str = "wall_clock_budget",
                    started_ago: float = 20_000, max_wall: float = 10_800) -> None:
    abs_dir = project / ".absoloop"
    _write(abs_dir / "state.json", {
        "status": "BUDGET_EXHAUSTED",
        "stop_reason": reason,
        "iteration": 3,
        "mission_id": "ABS-MINIMAL-001",
        "started_at": time.time() - started_ago,
        "cost_usd": 17.0,
        "tokens_total": 3_269_338,
    })
    _write(abs_dir / "runtime.json", {
        "mission_id": "ABS-MINIMAL-001",
        "loop_id": "loop-old",
        "objective": "Continue with the PROMPT_RUNBOOK workflow and prompts.",
        "max_iterations": 50,
        "max_cost_usd": 50.0,
        "max_wall_seconds": max_wall,
        "definition_of_done": ["Ship it."],
        "delivery": {"mode": "local"},
    })
    _write(abs_dir / "goal.md", "# /goal — Continue with the PROMPT_RUNBOOK\n")
    (project / "scripts").mkdir(parents=True, exist_ok=True)
    (project / "scripts" / "absoloop-run").write_text("#!/bin/sh\n", encoding="utf-8")


class ExtendCommandTests(unittest.TestCase):
    def test_top_level_extend_dispatches_force_extend(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _seed_exhausted(project)
            with mock.patch.object(cli, "extend_mission", return_value=0) as ext, \
                 mock.patch.object(cli, "default_engine", return_value="codex"):
                code = cli.main(["extend", "-C", str(project), "-m", "keep going"])
            self.assertEqual(code, 0)
            ext.assert_called_once()
            args = ext.call_args
            self.assertEqual(args.args[0], project.resolve())
            self.assertEqual(args.args[3], "keep going")

    def test_extend_command_aliases_resume_extend(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _seed_exhausted(project)
            with mock.patch.object(cli, "extend_mission", return_value=7) as ext, \
                 mock.patch.object(cli, "default_engine", return_value="codex"):
                code = cli.extend_command(["-C", str(project)])
            self.assertEqual(code, 7)
            ext.assert_called_once()

    def test_resume_blocks_when_wall_clock_still_exhausted(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _seed_exhausted(project)
            with mock.patch.object(cli, "start_loop") as start, \
                 mock.patch.object(cli, "default_engine", return_value="codex"):
                code = cli.resume_command(["-C", str(project)])
            self.assertEqual(code, 1)
            start.assert_not_called()

    def test_resume_allowed_after_raising_wall_cap(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            # Cap raised past elapsed time → plain resume is viable again.
            _seed_exhausted(project, started_ago=1_000, max_wall=10_800)
            with mock.patch.object(cli, "start_loop", return_value=0) as start, \
                 mock.patch.object(cli, "default_engine", return_value="codex"), \
                 mock.patch.object(cli, "resolve_engine_model", return_value="gpt"), \
                 mock.patch.object(cli, "persist_engine_model"):
                code = cli.resume_command(["-C", str(project)])
            self.assertEqual(code, 0)
            start.assert_called_once()

    def test_next_step_hint_wall_clock_points_at_extend(self):
        hint = cli.next_step_hint({
            "status": "BUDGET_EXHAUSTED",
            "stop_reason": "wall_clock_budget",
        })
        self.assertIn("absoloop extend", hint)
        self.assertIn("wall-clock", hint.lower())

    def test_wall_clock_still_exhausted_helper(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _seed_exhausted(project)
            state = json.loads(
                (project / ".absoloop" / "state.json").read_text(encoding="utf-8"))
            self.assertTrue(cli.wall_clock_still_exhausted(project, state))
            state["started_at"] = time.time()
            self.assertFalse(cli.wall_clock_still_exhausted(project, state))


if __name__ == "__main__":
    unittest.main()
