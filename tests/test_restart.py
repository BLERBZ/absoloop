"""Mission restart: factory-reset wipe of runs/objectives under .absoloop/."""
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


def _seed_history(project: pathlib.Path) -> pathlib.Path:
    abs_dir = project / ".absoloop"
    _write(abs_dir / "state.json", {
        "status": "COMPLETED",
        "iteration": 3,
        "mission_id": "ABS-42",
    })
    _write(abs_dir / "runtime.json", {"objective": "old work", "loop_id": "ABS-42"})
    _write(abs_dir / "goal.md", "# Goal\n\nold contract\n")
    _write(abs_dir / "ledger.jsonl", '{"type":"start"}\n')
    _write(abs_dir / "report.md", "# Report\n")
    _write(abs_dir / "report.html", "<html></html>")
    _write(abs_dir / "checkpoints" / "0003-done.json", {"status": "COMPLETED"})
    _write(abs_dir / "tmp" / "monitor.json", {"status": "COMPLETED", "live": False})
    _write(abs_dir / "runs" / "ABS-41" / "state.json", {"status": "COMPLETED"})
    _write(abs_dir / "runs" / "ABS-41" / "goal.md", "# old\n")
    _write(abs_dir / "worktrees" / "run-1" / "builder" / "marker.txt", "x")
    _write(abs_dir / "zcomb" / "state" / "activity.jsonl", '{"e":1}\n')
    _write(abs_dir / "schedules" / "nightly.toml", "name = 'nightly'\n")
    _write(abs_dir / "schedules" / "history.jsonl", '{"fired":1}\n')
    # Scaffold kept across factory reset
    _write(abs_dir / "schemas" / "agent-result.schema.json", {"type": "object"})
    _write(abs_dir / "prompts" / "builder.md", "build\n")
    return abs_dir


class RestartCommandTests(unittest.TestCase):
    def test_restart_requires_absoloop_dir(self):
        with tempfile.TemporaryDirectory() as tmp:
            code = cli.restart_command(["-C", tmp, "--yes"])
            self.assertEqual(code, 1)

    def test_restart_wipes_history_keeps_scaffold(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = _seed_history(project)

            code = cli.restart_command(["-C", str(project), "--yes"])
            self.assertEqual(code, 0)

            for name in ("state.json", "runtime.json", "goal.md", "ledger.jsonl",
                         "report.md", "report.html"):
                self.assertFalse((abs_dir / name).exists(), name)
            for name in ("checkpoints", "tmp", "runs", "worktrees", "zcomb"):
                self.assertFalse((abs_dir / name).exists(), name)
            self.assertFalse((abs_dir / "schedules" / "history.jsonl").exists())
            self.assertTrue((abs_dir / "schedules" / "nightly.toml").is_file())
            self.assertTrue((abs_dir / "schemas" / "agent-result.schema.json").is_file())
            self.assertTrue((abs_dir / "prompts" / "builder.md").is_file())

    def test_restart_empty_history_ok(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            (project / ".absoloop" / "schemas").mkdir(parents=True)
            code = cli.restart_command(["-C", str(project), "--yes"])
            self.assertEqual(code, 0)

    def test_restart_declined_confirmation(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _seed_history(project)
            with mock.patch("sys.stdin") as stdin:
                stdin.isatty.return_value = True
                with mock.patch("builtins.input", return_value="n"):
                    code = cli.restart_command(["-C", str(project)])
            self.assertEqual(code, 1)
            self.assertTrue((project / ".absoloop" / "state.json").is_file())

    def test_restart_non_tty_requires_yes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _seed_history(project)
            with mock.patch("sys.stdin") as stdin:
                stdin.isatty.return_value = False
                code = cli.restart_command(["-C", str(project)])
            self.assertEqual(code, 1)
            self.assertTrue((project / ".absoloop" / "state.json").is_file())

    def test_restart_stops_live_loop_then_wipes(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = _seed_history(project)
            now = time.time()
            fake_pid = 515151
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-99",
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "schema": 1,
                "pid": fake_pid,
                "heartbeat_ts": now,
                "status": "EXECUTING",
                "mission_id": "ABS-99",
            })
            with mock.patch.object(cli, "pid_alive", side_effect=[True, True, False]), \
                 mock.patch.object(cli, "terminate_mission_pid",
                                   return_value=True) as term:
                code = cli.restart_command(["-C", str(project), "--yes"])
            self.assertEqual(code, 0)
            term.assert_called_once_with(fake_pid)
            self.assertFalse((abs_dir / "state.json").exists())
            self.assertFalse((abs_dir / "tmp").exists())

    def test_factory_reset_helper_returns_labels(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = _seed_history(project)
            wiped = cli.factory_reset_project(abs_dir)
            self.assertIn("state.json", wiped)
            self.assertIn("runs/", wiped)
            self.assertIn("schedules/history.jsonl", wiped)


if __name__ == "__main__":
    unittest.main()
