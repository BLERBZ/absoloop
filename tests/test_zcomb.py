"""ZComb bridge: Absoloop telemetry → Kanban state files."""
from __future__ import annotations

import json
import os
import pathlib
import sys
import tempfile
import time
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness import zcomb


def _write(path: pathlib.Path, payload) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if isinstance(payload, str):
        path.write_text(payload, encoding="utf-8")
    else:
        path.write_text(json.dumps(payload), encoding="utf-8")


class BridgeStateTests(unittest.TestCase):
    def test_empty_project_placeholder(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            bridged = zcomb.build_bridge_state(project)
            self.assertEqual(len(bridged["agents"]["agents"]), 2)
            titles = [t["title"] for t in bridged["tasks"]["tasks"]]
            self.assertTrue(any("Waiting" in t for t in titles))

    def test_live_executing_maps_pipeline(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Make tests pass",
                "max_iterations": 10,
                "engine": "claude",
                "loop_id": "loop-1",
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 2,
                "mission_id": "ABS-42",
                "started_at": now - 60,
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "EXECUTING",
                "phase": "builder",
                "iteration": 2,
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "engine": "claude",
                "agent": "builder",
                "started_at": now - 60,
                "last_activity": {"ts": now, "detail": "editing tests"},
                "cost_usd": 0.42,
                "tokens_total": 12000,
            })
            _write(abs_dir / "tmp" / "live.jsonl",
                   json.dumps({"ts": now, "agent": "builder", "kind": "tool",
                               "detail": "Read foo.py"}) + "\n")

            bridged = zcomb.build_bridge_state(project)
            agents = {a["id"]: a for a in bridged["agents"]["agents"]}
            self.assertEqual(agents["builder-01"]["status"], "active")
            self.assertIn("editing", agents["builder-01"]["currentTask"] or "")

            by_id = {t["id"]: t for t in bridged["tasks"]["tasks"]}
            self.assertEqual(by_id["task-scaffold"]["status"], "done")
            self.assertEqual(by_id["task-execute"]["status"], "in_progress")
            self.assertEqual(by_id["iter-0002"]["status"], "in_progress")
            self.assertEqual(by_id["iter-0001"]["status"], "done")

            self.assertGreaterEqual(bridged["metrics"]["completionPct"], 0)
            self.assertTrue(any(a["type"] == "task_started"
                                for a in bridged["activity"]))
            self.assertTrue(bridged["metrics"]["live"])

    def test_awaiting_approval_puts_gate_in_review(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            _write(abs_dir / "runtime.json", {"objective": "x", "max_iterations": 5})
            _write(abs_dir / "state.json", {
                "status": "AWAITING_APPROVAL",
                "iteration": 3,
                "mission_id": "ABS-1",
                "started_at": time.time() - 100,
            })
            bridged = zcomb.build_bridge_state(project)
            by_id = {t["id"]: t for t in bridged["tasks"]["tasks"]}
            self.assertEqual(by_id["task-gate"]["status"], "review")
            self.assertGreaterEqual(bridged["metrics"]["completionPct"], 85)

    def test_sync_state_writes_files(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _write(project / ".absoloop" / "runtime.json",
                   {"objective": "sync me", "max_iterations": 3})
            _write(project / ".absoloop" / "state.json",
                   {"status": "READY", "iteration": 0})
            out = zcomb.sync_state(project)
            self.assertTrue((out / "agents.json").is_file())
            self.assertTrue((out / "tasks.json").is_file())
            self.assertTrue((out / "metrics.json").is_file())
            self.assertTrue((out / "activity.jsonl").is_file())
            agents = json.loads((out / "agents.json").read_text(encoding="utf-8"))
            self.assertIn("agents", agents)


class CliDispatchTests(unittest.TestCase):
    def test_extract_zcomb_flag(self):
        cleaned, want = zcomb.extract_zcomb_flag(
            ["--zcomb", "-C", "./proj", "--port", "4000"])
        self.assertTrue(want)
        self.assertEqual(cleaned, ["-C", "./proj", "--port", "4000"])
        cleaned, want = zcomb.extract_zcomb_flag(["watch", "--once"])
        self.assertFalse(want)
        self.assertEqual(cleaned, ["watch", "--once"])

    def test_zcomb_once_no_node_required_for_bridge(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _write(project / ".absoloop" / "runtime.json",
                   {"objective": "once", "max_iterations": 1})
            with mock.patch.object(zcomb, "ensure_dashboard_built"):
                code = zcomb.zcomb_command(
                    ["-C", str(project), "--once", "--no-browser"])
            self.assertEqual(code, 0)
            self.assertTrue(
                (project / ".absoloop" / "zcomb" / "state" / "tasks.json").is_file())


if __name__ == "__main__":
    unittest.main()
