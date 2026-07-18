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

    def test_teammate_spawns_become_agents_with_quirky_names(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json",
                   {"objective": "x", "max_iterations": 5, "engine": "claude"})
            _write(abs_dir / "state.json",
                   {"status": "EXECUTING", "iteration": 1, "started_at": now - 30})
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "EXECUTING", "phase": "builder", "iteration": 1,
                "pid": os.getpid(), "heartbeat_ts": now, "agent": "builder",
                "started_at": now - 30,
            })
            lines = [
                json.dumps({"ts": now - 5, "agent": "builder", "kind": "tool",
                            "detail": "spawn teammate · Agent: Independent critic of mission"}),
                json.dumps({"ts": now - 4, "agent": "builder", "kind": "tool",
                            "detail": "spawn teammate · Task: Write unit tests for parser"}),
                json.dumps({"ts": now - 3, "agent": "builder", "kind": "tool",
                            "detail": "Bash: pytest -q 2>&1 && echo OK | tail -5"}),
            ]
            _write(abs_dir / "tmp" / "live.jsonl", "\n".join(lines) + "\n")

            bridged = zcomb.build_bridge_state(project)
            agents = bridged["agents"]["agents"]
            self.assertEqual(len(agents), 4)  # builder + critic + 2 teammates
            teammates = [a for a in agents if a["id"].startswith("teammate-")]
            self.assertEqual(len(teammates), 2)
            for mate in teammates:
                self.assertEqual(mate["status"], "active")
                self.assertIn("Spawned teammate", mate["role"])
            names = {m["name"] for m in teammates}
            self.assertEqual(len(names), 2)  # distinct quirky names

            spawned = [a for a in bridged["activity"] if a["type"] == "spawned"]
            self.assertEqual(len(spawned), 2)
            self.assertTrue(all(a["agentId"].startswith("teammate-")
                                for a in spawned))
            self.assertIn("joins the team", spawned[0]["message"])

            # Raw shell noise is humanized
            shell = [a for a in bridged["activity"]
                     if a["message"].startswith("Ran `")]
            self.assertEqual(len(shell), 1)
            self.assertNotIn("2>&1", shell[0]["message"])

    def test_quirky_names_are_deterministic_and_themed(self):
        name1 = zcomb.quirky_teammate_name("Independent critic of mission")
        name2 = zcomb.quirky_teammate_name("Independent critic of mission")
        self.assertEqual(name1, name2)
        used = set()
        a = zcomb.quirky_teammate_name("review the diff", used)
        b = zcomb.quirky_teammate_name("review the diff again", used)
        self.assertNotEqual(a, b)

    def test_tasks_carry_contextual_descriptions(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            _write(abs_dir / "runtime.json",
                   {"objective": "Ship the widget", "max_iterations": 4})
            _write(abs_dir / "state.json",
                   {"status": "EXECUTING", "iteration": 2, "mission_id": "ABS-7",
                    "started_at": time.time() - 60})
            bridged = zcomb.build_bridge_state(project)
            by_id = {t["id"]: t for t in bridged["tasks"]["tasks"]}
            self.assertIn("Ship the widget", by_id["task-scaffold"]["description"])
            self.assertIn("2/4", by_id["task-execute"]["description"])
            self.assertIn("ABS-7", by_id["task-deliver"]["description"])
            self.assertTrue(all("description" in t
                                for t in bridged["tasks"]["tasks"]))

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

    def test_awaiting_new_run_after_scaffold(self):
        """Runtime without state → Kanban waits for the new run/objective."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            _write(project / ".absoloop" / "runtime.json", {
                "objective": "Ship the widget",
                "max_iterations": 5,
                "loop_id": "loop-new",
            })
            bridged = zcomb.build_bridge_state(project)
            metrics = bridged["metrics"]
            self.assertTrue(metrics["awaitingRun"])
            self.assertEqual(metrics["status"], "STARTING")
            self.assertEqual(metrics["loopId"], "loop-new")
            self.assertEqual(metrics["objective"], "Ship the widget")
            self.assertEqual(metrics["runKey"], "loop-new:pending")
            self.assertEqual(metrics["projectName"], project.name)
            titles = [t["title"] for t in bridged["tasks"]["tasks"]]
            self.assertTrue(any("Waiting for new Absoloop run" in t for t in titles))
            self.assertTrue(any("Ship the widget" in t for t in titles))

    def test_stale_monitor_from_prior_loop_is_ignored(self):
        """After extend, leftover monitor.json for the old loop must not paint."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Continue the work",
                "max_iterations": 8,
                "loop_id": "loop-2",
            })
            # No state.json (archived by extend); stale monitor from loop-1.
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "COMPLETED",
                "phase": "deliver",
                "iteration": 5,
                "loop_id": "loop-1",
                "mission_id": "ABS-9",
                "pid": 1,
                "heartbeat_ts": now - 10_000,
                "started_at": now - 20_000,
            })
            bridged = zcomb.build_bridge_state(project)
            metrics = bridged["metrics"]
            self.assertTrue(metrics["awaitingRun"])
            self.assertEqual(metrics["loopId"], "loop-2")
            self.assertFalse(metrics["live"])
            self.assertNotEqual(metrics["status"], "COMPLETED")
            task_ids = {t["id"] for t in bridged["tasks"]["tasks"]}
            self.assertIn("task-waiting", task_ids)
            self.assertNotIn("task-execute", task_ids)

    def test_live_run_emits_stable_run_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            started = now - 60
            _write(abs_dir / "runtime.json", {
                "objective": "Make tests pass",
                "max_iterations": 10,
                "loop_id": "loop-1",
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 2,
                "mission_id": "ABS-42",
                "started_at": started,
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "EXECUTING",
                "phase": "builder",
                "iteration": 2,
                "loop_id": "loop-1",
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "started_at": started,
                "agent": "builder",
            })
            bridged = zcomb.build_bridge_state(project)
            metrics = bridged["metrics"]
            self.assertFalse(metrics["awaitingRun"])
            self.assertTrue(metrics["live"])
            self.assertEqual(metrics["runKey"], f"loop-1:{int(started)}")
            self.assertEqual(metrics["loopId"], "loop-1")


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
