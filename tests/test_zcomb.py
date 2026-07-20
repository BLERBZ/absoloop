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

    def test_state_awaiting_approval_wins_over_live_final_review(self):
        """Codex critic can leave monitor at FINAL_REVIEW after the gate.

        CLI approve reads state.json; Kanban must publish the same status so
        the green Approve control enables.
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship via Codex",
                "max_iterations": 8,
                "engine": "codex",
                "loop_id": "loop-codex-1",
            })
            _write(abs_dir / "state.json", {
                "status": "AWAITING_APPROVAL",
                "iteration": 4,
                "mission_id": "ABS-CODEX",
                "started_at": now - 600,
                "stop_reason": "accepted_pending_human_gate",
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "FINAL_REVIEW",
                "phase": "critic review",
                "iteration": 4,
                "loop_id": "loop-codex-1",
                "mission_id": "ABS-CODEX",
                "engine": "codex",
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "started_at": now - 600,
                "agent": "critic",
            })
            bridged = zcomb.build_bridge_state(project)
            metrics = bridged["metrics"]
            self.assertEqual(metrics["status"], "AWAITING_APPROVAL")
            self.assertTrue(metrics["awaitingApproval"])
            self.assertFalse(metrics["live"])
            self.assertFalse(metrics["awaitingRun"])
            by_id = {t["id"]: t for t in bridged["tasks"]["tasks"]}
            self.assertEqual(by_id["task-gate"]["status"], "review")

    def test_monitor_awaiting_approval_enables_gate_during_codex_wind_down(self):
        """Live monitor already at the gate must enable Approve immediately."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship via Codex",
                "max_iterations": 8,
                "engine": "codex",
                "loop_id": "loop-codex-2",
            })
            # Disk state can lag one flush behind monitor during stop()/report.
            _write(abs_dir / "state.json", {
                "status": "FINAL_REVIEW",
                "iteration": 2,
                "mission_id": "ABS-CODEX-2",
                "started_at": now - 300,
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "AWAITING_APPROVAL",
                "phase": "stopped",
                "iteration": 2,
                "loop_id": "loop-codex-2",
                "engine": "codex",
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "started_at": now - 300,
                "stop_reason": "accepted_pending_human_gate",
            })
            metrics = zcomb.build_bridge_state(project)["metrics"]
            self.assertEqual(metrics["status"], "AWAITING_APPROVAL")
            self.assertTrue(metrics["awaitingApproval"])
            self.assertFalse(metrics["awaitingRun"])

    def test_completed_state_wins_over_stale_monitor_awaiting_approval(self):
        """After approve, stale monitor must not keep Approve green.

        UI was enabling Approve from monitor AWAITING_APPROVAL while
        state.json was already COMPLETED — click then failed with
        \"mission status is 'COMPLETED'\".
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship via Codex",
                "max_iterations": 8,
                "engine": "codex",
                "loop_id": "loop-codex-3",
            })
            _write(abs_dir / "state.json", {
                "status": "COMPLETED",
                "iteration": 3,
                "mission_id": "ABS-CODEX-3",
                "started_at": now - 600,
                "stop_reason": "human_approved",
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "AWAITING_APPROVAL",
                "phase": "stopped",
                "iteration": 3,
                "loop_id": "loop-codex-3",
                "engine": "codex",
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "started_at": now - 600,
                "stop_reason": "accepted_pending_human_gate",
            })
            metrics = zcomb.build_bridge_state(project)["metrics"]
            self.assertEqual(metrics["status"], "COMPLETED")
            self.assertFalse(metrics["awaitingApproval"])
            self.assertFalse(metrics["live"])
            self.assertFalse(metrics["awaitingRun"])

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

    def test_past_loops_only_session_archives_not_full_history(self):
        """Done past-run cards are session-scoped — not every archive on disk."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship the original mission",
                "max_iterations": 8,
                "loop_id": "loop-3",
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-PAST",
                "started_at": now - 30,
                "cost_usd": 1.5,
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "EXECUTING",
                "phase": "builder",
                "iteration": 1,
                "loop_id": "loop-3",
                "mission_id": "ABS-PAST",
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "started_at": now - 30,
            })
            _write(abs_dir / "runs" / "loop-1" / "state.json", {
                "status": "COMPLETED",
                "iteration": 3,
                "mission_id": "ABS-PAST",
                "started_at": now - 3600,
                "stop_reason": "human_approved",
                "cost_usd": 12.4,
            })
            _write(abs_dir / "runs" / "loop-2" / "state.json", {
                "status": "BUDGET_EXHAUSTED",
                "iteration": 2,
                "mission_id": "ABS-PAST",
                "started_at": now - 1800,
                "stop_reason": "cost_budget",
                "cost_usd": 50.0,
            })
            # Session opened when only loop-1 was archived → hide loop-1,
            # surface loop-2 which was archived during this session.
            _write(abs_dir / "zcomb" / "kanban-session.json", {
                "startedAt": now - 100,
                "baselineArchiveIds": ["loop-1"],
            })

            bridged = zcomb.build_bridge_state(project)
            tasks = bridged["tasks"]["tasks"]
            past = [t for t in tasks if str(t.get("kind") or "") == "past_run"
                    or str(t["id"]).startswith("run-")]
            self.assertEqual(len(past), 1)
            self.assertEqual(past[0]["id"], "run-loop-2")
            self.assertEqual(past[0]["status"], "done")
            self.assertEqual(past[0].get("kind"), "past_run")
            self.assertEqual(past[0]["title"], "Loop 1 · Budget exhausted")
            self.assertIn("2 iters", past[0]["description"])
            self.assertIn("$50", past[0]["description"])
            # Clean summarized title — no raw long loop id dump.
            self.assertNotIn("loop-2", past[0]["title"])
            self.assertLessEqual(len(past[0]["title"]), 40)
            self.assertIn("task-execute", {t["id"] for t in tasks})

    def test_preexisting_archives_hidden_until_session_extend(self):
        """Opening Kanban with old archives must not flood Done."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship",
                "max_iterations": 4,
                "loop_id": "loop-now",
            })
            _write(abs_dir / "state.json", {
                "status": "COMPLETED",
                "iteration": 1,
                "mission_id": "ABS-1",
                "started_at": now - 60,
                "stop_reason": "human_approved",
                "cost_usd": 2.0,
            })
            _write(abs_dir / "runs" / "loop-old" / "state.json", {
                "status": "COMPLETED",
                "iteration": 5,
                "started_at": now - 10_000,
                "cost_usd": 40.0,
            })
            # First bridge call establishes baseline = existing archives.
            bridged = zcomb.build_bridge_state(project)
            past = [t for t in bridged["tasks"]["tasks"]
                    if str(t["id"]).startswith("run-")]
            self.assertEqual(past, [])
            session = json.loads(
                (abs_dir / "zcomb" / "kanban-session.json").read_text(
                    encoding="utf-8"))
            self.assertIn("loop-old", session.get("baselineArchiveIds") or [])

    def test_awaiting_keeps_session_past_run_done_cards(self):
        """During post-extend STARTING, session-archived loops stay as Done."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship the original mission",
                "max_iterations": 8,
                "loop_id": "loop-2",
                "continuation": {
                    "previous_loop_id": "loop-1",
                    "note": "Keep going",
                },
            })
            _write(abs_dir / "runs" / "loop-1" / "state.json", {
                "status": "COMPLETED",
                "iteration": 3,
                "mission_id": "ABS-1",
                "started_at": now - 600,
                "stop_reason": "human_approved",
                "cost_usd": 8.0,
            })
            # Empty baseline → this archive counts as session history.
            _write(abs_dir / "zcomb" / "kanban-session.json", {
                "startedAt": now - 10,
                "baselineArchiveIds": [],
            })
            bridged = zcomb.build_bridge_state(project)
            tasks = bridged["tasks"]["tasks"]
            ids = {t["id"] for t in tasks}
            self.assertIn("task-waiting", ids)
            self.assertIn("run-loop-1", ids)
            past = next(t for t in tasks if t["id"] == "run-loop-1")
            self.assertEqual(past["status"], "done")
            self.assertEqual(past.get("kind"), "past_run")
            self.assertRegex(past["title"], r"^Loop \d+ · ")

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
            self.assertEqual(metrics["startedAt"], started)
            self.assertIsNone(metrics.get("endedAt"))

    def test_elapsed_anchors_stable_across_resync_without_started_at(self):
        """Missing started_at must not invent a new timestamp every sync."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "stable clock",
                "max_iterations": 3,
                "loop_id": "loop-clock",
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-CLOCK",
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "EXECUTING",
                "phase": "builder",
                "iteration": 1,
                "loop_id": "loop-clock",
                "pid": os.getpid(),
                "heartbeat_ts": now,
            })
            a = zcomb.build_bridge_state(project)["metrics"]
            time.sleep(0.05)
            b = zcomb.build_bridge_state(project)["metrics"]
            self.assertEqual(a["runKey"], b["runKey"])
            self.assertEqual(a.get("startedAt"), b.get("startedAt"))
            self.assertIsNone(a.get("startedAt"))

    def test_completed_run_exposes_ended_at_for_frozen_elapsed(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            started = time.time() - 600
            ended = started + 120
            _write(abs_dir / "runtime.json", {
                "objective": "done",
                "loop_id": "loop-done",
                "max_iterations": 2,
            })
            _write(abs_dir / "state.json", {
                "status": "COMPLETED",
                "iteration": 1,
                "mission_id": "ABS-D",
                "started_at": started,
                "ended_at": ended,
                "stop_reason": "human_approved",
            })
            metrics = zcomb.build_bridge_state(project)["metrics"]
            self.assertEqual(metrics["startedAt"], started)
            self.assertEqual(metrics["endedAt"], ended)

    def test_objective_history_prefers_latest_continuation(self):
        """Kanban bar shows latest extend note; history keeps the original."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship the original mission",
                "max_iterations": 8,
                "loop_id": "loop-3",
                "continuation": {
                    "previous_loop_id": "loop-2",
                    "note": "Second continuation — polish the UI",
                },
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-7",
                "started_at": now - 30,
            })
            _write(abs_dir / "ledger.jsonl", "\n".join([
                json.dumps({
                    "ts": now - 200,
                    "type": "extension",
                    "previous_loop_id": "loop-1",
                    "loop_id": "loop-2",
                    "note": "First continuation — add tests",
                }),
                json.dumps({
                    "ts": now - 100,
                    "type": "extension",
                    "previous_loop_id": "loop-2",
                    "loop_id": "loop-3",
                    "note": "Second continuation — polish the UI",
                }),
            ]) + "\n")
            bridged = zcomb.build_bridge_state(project)
            metrics = bridged["metrics"]
            self.assertEqual(metrics["objective"], "Ship the original mission")
            self.assertEqual(
                metrics["displayedObjective"],
                "Second continuation — polish the UI",
            )
            kinds = [entry["kind"] for entry in metrics["objectiveHistory"]]
            texts = [entry["text"] for entry in metrics["objectiveHistory"]]
            self.assertEqual(
                kinds, ["objective", "continuation", "continuation"])
            self.assertEqual(texts[0], "Ship the original mission")
            self.assertEqual(texts[1], "First continuation — add tests")
            self.assertEqual(texts[2], "Second continuation — polish the UI")

    def test_objective_history_includes_loop_elapsed(self):
        """Dropdown rows expose wall-clock elapsed next to each loop id."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship the original mission",
                "max_iterations": 8,
                "loop_id": "loop-3",
                "continuation": {
                    "previous_loop_id": "loop-2",
                    "note": "Second continuation — polish the UI",
                },
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-7",
                "started_at": now - 45,
            })
            _write(abs_dir / "runs" / "loop-1" / "state.json", {
                "status": "COMPLETED",
                "iteration": 2,
                "started_at": now - 400,
                "ended_at": now - 280,
            })
            _write(abs_dir / "runs" / "loop-2" / "state.json", {
                "status": "COMPLETED",
                "iteration": 3,
                "started_at": now - 250,
                "ended_at": now - 100,
            })
            _write(abs_dir / "ledger.jsonl", "\n".join([
                json.dumps({
                    "ts": now - 200,
                    "type": "extension",
                    "previous_loop_id": "loop-1",
                    "loop_id": "loop-2",
                    "note": "First continuation — add tests",
                }),
                json.dumps({
                    "ts": now - 100,
                    "type": "extension",
                    "previous_loop_id": "loop-2",
                    "loop_id": "loop-3",
                    "note": "Second continuation — polish the UI",
                }),
            ]) + "\n")
            bridged = zcomb.build_bridge_state(project)
            history = bridged["metrics"]["objectiveHistory"]
            by_loop = {entry.get("loopId"): entry for entry in history}
            self.assertEqual(by_loop["loop-1"]["elapsedSeconds"], 120)
            self.assertEqual(by_loop["loop-2"]["elapsedSeconds"], 150)
            self.assertGreaterEqual(by_loop["loop-3"]["elapsedSeconds"], 40)
            self.assertLessEqual(by_loop["loop-3"]["elapsedSeconds"], 50)

            # Archived loops without ended_at still get elapsed via extension ts.
            _write(abs_dir / "runs" / "loop-1" / "state.json", {
                "status": "COMPLETED",
                "iteration": 2,
                "started_at": now - 400,
            })
            bridged2 = zcomb.build_bridge_state(project)
            hist2 = {
                entry.get("loopId"): entry
                for entry in bridged2["metrics"]["objectiveHistory"]
            }
            # extension for loop-1 → loop-2 is at now-200; start was now-400.
            self.assertEqual(hist2["loop-1"]["elapsedSeconds"], 200)

    def test_archived_reports_are_searchable_on_kanban(self):
        """Report archives surface as Done cards with searchable body text."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship searchable reports",
                "max_iterations": 4,
                "loop_id": "loop-live",
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-RPT",
                "started_at": now - 20,
            })
            report_body = (
                "# Absoloop Report\n\n"
                "UniqueNeedlePhrase in the archived report body.\n"
            )
            _write(abs_dir / "reports" / "loop-old" / "report.md", report_body)
            _write(abs_dir / "reports" / "loop-old" / "meta.json", {
                "loopId": "loop-old",
                "status": "COMPLETED",
                "objective": "Prior loop focus",
            })
            bridged = zcomb.build_bridge_state(project)
            tasks = bridged["tasks"]["tasks"]
            reports = [t for t in tasks if t.get("kind") == "report"]
            self.assertTrue(reports)
            blob = " ".join(
                f"{t.get('title')} {t.get('description')}" for t in reports)
            self.assertIn("UniqueNeedlePhrase", blob)
            self.assertIn("loop-old", blob)

    def test_objectives_archive_document_matches_dropdown(self):
        """sync_state writes OBJECTIVES.md with dropdown labels + statements."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Original mission statement for archive",
                "max_iterations": 4,
                "loop_id": "loop-2",
                "continuation": {
                    "previous_loop_id": "loop-1",
                    "note": "Continuation note for wave two",
                },
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-OBJ",
                "started_at": now - 30,
            })
            _write(abs_dir / "ledger.jsonl", "\n".join([
                json.dumps({
                    "ts": now - 100,
                    "type": "extension",
                    "previous_loop_id": "loop-1",
                    "loop_id": "loop-2",
                    "note": "Continuation note for wave two",
                }),
            ]) + "\n")
            zcomb.sync_state(project)
            md_path = abs_dir / "reports" / "OBJECTIVES.md"
            self.assertTrue(md_path.is_file())
            body = md_path.read_text(encoding="utf-8")
            self.assertIn("CONTINUATION · CURRENT", body)
            self.assertIn("ORIGINAL OBJECTIVE", body)
            self.assertIn("Continuation note for wave two", body)
            self.assertIn("Original mission statement for archive", body)
            self.assertIn("loop-2", body)
            self.assertTrue((abs_dir / "reports" / "OBJECTIVES.json").is_file())

    def test_run_results_mirrors_cli_critic_spend_and_stop(self):
        """Kanban Run Results panel gets critic finish, verdict, spend, stop."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            critic_rel = ".absoloop/tmp/iteration-0003-critic.json"
            _write(abs_dir / "runtime.json", {
                "objective": "Ship via critic gate",
                "max_iterations": 8,
                "max_cost_usd": 50.0,
                "loop_id": "loop-results-1",
                "engine": "claude",
            })
            _write(abs_dir / "state.json", {
                "status": "AWAITING_APPROVAL",
                "iteration": 3,
                "mission_id": "ABS-RESULTS",
                "started_at": now - 600,
                "stop_reason": "accepted_pending_human_gate",
                "cost_usd": 13.43,
                "tokens_total": 2_283_900,
            })
            _write(abs_dir / "tmp" / "iteration-0003-critic.json", {
                "num_turns": 8,
                "total_cost_usd": 0.83,
                "structured_output": {
                    "recommendation": "PASS",
                    "blocking_findings": [],
                    "summary": (
                        "Independently re-ran every documented gate and each "
                        "passed exactly as claimed"
                    ),
                },
            })
            _write(abs_dir / "ledger.jsonl", "\n".join([
                json.dumps({
                    "ts": now - 120,
                    "type": "agent_run",
                    "engine": "claude",
                    "exit_code": 0,
                    "wall_seconds": 56.2,
                    "cost_usd": 0.83,
                    "cost_is_exact": True,
                    "tokens": 200_600,
                    "result": critic_rel,
                }),
                json.dumps({
                    "ts": now - 100,
                    "type": "mission_stop",
                    "reason": "accepted_pending_human_gate",
                    "status": "AWAITING_APPROVAL",
                }),
            ]) + "\n")
            _write(abs_dir / "tmp" / "live.jsonl",
                   json.dumps({
                       "ts": now - 110,
                       "agent": "critic",
                       "kind": "verdict",
                       "detail": (
                           "PASS: Independently re-ran every documented gate "
                           "and each passed exactly as claimed"
                       ),
                   }) + "\n")

            bridged = zcomb.build_bridge_state(project)
            results = bridged["runResults"]
            self.assertTrue(results["available"])
            self.assertEqual(results["verdict"]["recommendation"], "PASS")
            self.assertIn("documented gate", results["verdict"]["summary"])
            self.assertEqual(results["critic"]["outcome"], "finished")
            self.assertEqual(results["critic"]["wallSeconds"], 56)
            self.assertEqual(results["critic"]["costUsd"], 0.83)
            self.assertEqual(results["critic"]["tokens"], 200_600)
            self.assertEqual(results["critic"]["turns"], 8)
            self.assertEqual(results["spend"]["costUsd"], 13.43)
            self.assertEqual(results["spend"]["maxCostUsd"], 50.0)
            self.assertEqual(results["spend"]["pctUsed"], 27)
            self.assertAlmostEqual(results["spend"]["remainingUsd"], 36.57,
                                   places=2)
            self.assertEqual(results["mission"]["status"], "AWAITING_APPROVAL")
            self.assertEqual(
                results["mission"]["stopReason"],
                "accepted_pending_human_gate",
            )
            self.assertEqual(results["mission"]["iteration"], 3)

            out = zcomb.sync_state(project)
            written = json.loads(
                (out / "run-results.json").read_text(encoding="utf-8"))
            self.assertTrue(written["available"])
            self.assertEqual(written["verdict"]["recommendation"], "PASS")

    def test_run_results_refresh_after_extension(self):
        """Prior-loop REJECT critic must not paint Loop Results after extend.

        Codex often REJECT → extend while tmp critic JSON, ledger agent_run,
        and live.jsonl verdicts remain. The panel should stay empty until the
        new run produces its own critic.
        """
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            prior_critic = ".absoloop/tmp/iteration-0001-critic.json"
            _write(abs_dir / "runtime.json", {
                "objective": "Continue after Codex reject",
                "max_iterations": 8,
                "max_cost_usd": 50.0,
                "loop_id": "loop-new",
                "engine": "codex",
            })
            _write(abs_dir / "state.json", {
                "status": "EXECUTING",
                "iteration": 1,
                "mission_id": "ABS-EXTEND",
                "started_at": now - 30,
                "cost_usd": 0.0,
                "tokens_total": 0,
            })
            _write(abs_dir / "tmp" / "monitor.json", {
                "status": "EXECUTING",
                "phase": "builder",
                "iteration": 1,
                "pid": os.getpid(),
                "heartbeat_ts": now,
                "engine": "codex",
                "agent": "builder",
                "started_at": now - 30,
                "cost_usd": 0.0,
                "tokens_total": 0,
            })
            # Leftover prior-loop critic on disk (same iteration number).
            _write(abs_dir / "tmp" / "iteration-0001-critic.json", {
                "recommendation": "REJECT",
                "blocking_findings": [
                    "Unrestricted INSERT privilege is a security defect",
                ],
                "summary": (
                    "Local checks passed, but the audit gate remains "
                    "unverified."
                ),
            })
            # Force mtime before the extension boundary so disk fallback
            # cannot treat this as a current-run critic.
            prior_path = abs_dir / "tmp" / "iteration-0001-critic.json"
            os.utime(prior_path, (now - 400, now - 400))
            _write(abs_dir / "ledger.jsonl", "\n".join([
                json.dumps({
                    "ts": now - 300,
                    "type": "agent_run",
                    "engine": "codex",
                    "exit_code": 0,
                    "wall_seconds": 272.0,
                    "cost_usd": 2.0,
                    "tokens": 1_860_000,
                    "result": prior_critic,
                }),
                json.dumps({
                    "ts": now - 280,
                    "type": "mission_stop",
                    "reason": "critic_reject",
                    "status": "REJECTED",
                }),
                json.dumps({
                    "ts": now - 200,
                    "type": "extension",
                    "previous_loop_id": "loop-old",
                    "loop_id": "loop-new",
                    "note": "fix security boundary and re-run audit",
                }),
            ]) + "\n")
            _write(abs_dir / "tmp" / "live.jsonl", "\n".join([
                json.dumps({
                    "ts": now - 290,
                    "agent": "critic",
                    "kind": "verdict",
                    "detail": (
                        "REJECT: Local checks passed, but the audit gate "
                        "remains unverified."
                    ),
                }),
                json.dumps({
                    "ts": now - 10,
                    "agent": "builder",
                    "kind": "tool",
                    "detail": "Read docs/runbook.md",
                }),
            ]) + "\n")

            bridged = zcomb.build_bridge_state(project)
            results = bridged["runResults"]
            self.assertFalse(results["available"])
            self.assertIsNone(results["verdict"])
            self.assertIsNone(results["critic"])
            self.assertIsNone(results["mission"])

            # After the new loop's critic lands, the panel updates.
            fresh_rel = ".absoloop/tmp/iteration-0002-critic.json"
            _write(abs_dir / "state.json", {
                "status": "AWAITING_APPROVAL",
                "iteration": 2,
                "mission_id": "ABS-EXTEND",
                "started_at": now - 30,
                "stop_reason": "accepted_pending_human_gate",
                "cost_usd": 4.5,
                "tokens_total": 900_000,
            })
            _write(abs_dir / "tmp" / "iteration-0002-critic.json", {
                "recommendation": "PASS",
                "blocking_findings": [],
                "summary": "Security boundary fixed; audit gate green.",
                "num_turns": 4,
            })
            with open(abs_dir / "ledger.jsonl", "a", encoding="utf-8") as handle:
                handle.write(json.dumps({
                    "ts": now - 5,
                    "type": "agent_run",
                    "engine": "codex",
                    "exit_code": 0,
                    "wall_seconds": 40.0,
                    "cost_usd": 0.5,
                    "tokens": 120_000,
                    "result": fresh_rel,
                }) + "\n")
            _write(abs_dir / "tmp" / "live.jsonl",
                   (abs_dir / "tmp" / "live.jsonl").read_text(encoding="utf-8")
                   + json.dumps({
                       "ts": now - 4,
                       "agent": "critic",
                       "kind": "verdict",
                       "detail": (
                           "PASS: Security boundary fixed; audit gate green."
                       ),
                   }) + "\n")

            bridged = zcomb.build_bridge_state(project)
            results = bridged["runResults"]
            self.assertTrue(results["available"])
            self.assertEqual(results["verdict"]["recommendation"], "PASS")
            self.assertIn("Security boundary fixed", results["verdict"]["summary"])
            self.assertEqual(results["verdict"]["blockingFindings"], [])
            self.assertEqual(results["critic"]["costUsd"], 0.5)
            self.assertEqual(results["mission"]["status"], "AWAITING_APPROVAL")

    def test_proposed_extension_prompt_includes_run_context(self):
        ctx = {
            "objective": "Ship the Kanban Run Results panel",
            "status": "COMPLETED",
            "stopReason": "human_approved",
            "recommendation": "PASS",
            "summary": "All gates passed; panel mirrors CLI critic spend stop.",
            "blockingFindings": [],
            "iteration": 3,
            "costUsd": 12.4,
            "projectName": "absoloop",
        }
        prompt = zcomb._build_extension_prompt(ctx)
        self.assertIn("Ship the Kanban Run Results panel", prompt)
        self.assertIn("COMPLETED", prompt)
        self.assertIn("PASS", prompt)
        self.assertIn("All gates passed", prompt)
        self.assertIn("continuation objective", prompt.lower())

    def test_heuristic_extension_proposal_for_pass(self):
        ctx = {
            "objective": "Add Run Results panel",
            "status": "COMPLETED",
            "stopReason": "human_approved",
            "recommendation": "PASS",
            "summary": "Critic verified every documented gate.",
            "blockingFindings": [],
            "iteration": 2,
            "costUsd": 5.0,
            "projectName": "demo",
        }
        proposal = zcomb._heuristic_extension_proposal(ctx)
        self.assertEqual(proposal["status"], "ready")
        self.assertEqual(proposal["source"], "heuristic")
        self.assertTrue(proposal["note"].strip())
        self.assertIn("Add Run Results panel", proposal["note"])
        chain_roles = [step["role"] for step in proposal["chain"]]
        self.assertEqual(chain_roles[0], "prompt")
        self.assertIn("response", chain_roles)

    def test_heuristic_extension_addresses_blocking_findings(self):
        ctx = {
            "objective": "Harden approve for Codex",
            "status": "BLOCKED",
            "stopReason": "critic_reject",
            "recommendation": "HOLD",
            "summary": "Approve still dark at the gate.",
            "blockingFindings": [
                "Approve button ignores AWAITING_APPROVAL from state.json",
            ],
            "iteration": 1,
            "costUsd": 3.2,
            "projectName": "demo",
        }
        proposal = zcomb._heuristic_extension_proposal(ctx)
        self.assertIn("Approve button", proposal["note"])
        self.assertTrue(proposal["rationale"])

    def test_parse_extension_llm_response_json(self):
        raw = json.dumps({
            "analysis": "Gates passed; next is polish.",
            "note": "Polish Run Results typography and add Proposed Extension.",
            "rationale": "Natural follow-on after the glanceable stance landed.",
        })
        parsed = zcomb._parse_extension_llm_response(raw)
        self.assertEqual(
            parsed["note"],
            "Polish Run Results typography and add Proposed Extension.",
        )
        self.assertIn("Gates passed", parsed["analysis"])

    def test_llm_login_failure_falls_back_to_heuristic(self):
        ctx = {
            "objective": "Ship Proposed Extension",
            "status": "COMPLETED",
            "stopReason": "human_approved",
            "recommendation": "PASS",
            "summary": "All good.",
            "blockingFindings": [],
            "iteration": 1,
            "costUsd": 1.0,
            "projectName": "demo",
            "engine": "claude",
        }
        with mock.patch.object(
            zcomb, "_call_extension_llm",
            side_effect=RuntimeError("claude: engine auth/limit: Not logged in"),
        ):
            proposal = zcomb._generate_proposed_extension(ctx, "fp-login")
        self.assertEqual(proposal["status"], "ready")
        self.assertEqual(proposal["source"], "heuristic")
        self.assertNotIn("not logged in", proposal["note"].lower())
        self.assertIn("auth/limit", (proposal.get("error") or "").lower())

    def test_run_results_includes_cached_proposed_extension(self):
        """Terminal run surfaces a ready Proposed Extension from cache."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            now = time.time()
            _write(abs_dir / "runtime.json", {
                "objective": "Ship via critic gate",
                "max_iterations": 8,
                "max_cost_usd": 50.0,
                "loop_id": "loop-propose-1",
                "engine": "claude",
            })
            _write(abs_dir / "state.json", {
                "status": "COMPLETED",
                "iteration": 2,
                "mission_id": "ABS-PROPOSE",
                "started_at": now - 400,
                "stop_reason": "human_approved",
                "cost_usd": 8.5,
                "tokens_total": 100_000,
            })
            _write(abs_dir / "tmp" / "iteration-0002-critic.json", {
                "num_turns": 4,
                "total_cost_usd": 0.4,
                "structured_output": {
                    "recommendation": "PASS",
                    "blocking_findings": [],
                    "summary": "Mission complete and approved.",
                },
            })
            _write(abs_dir / "ledger.jsonl", json.dumps({
                "ts": now - 80,
                "type": "agent_run",
                "engine": "claude",
                "exit_code": 0,
                "wall_seconds": 40,
                "cost_usd": 0.4,
                "tokens": 50_000,
                "result": ".absoloop/tmp/iteration-0002-critic.json",
            }) + "\n")

            fingerprint = zcomb._extension_fingerprint(
                loop_id="loop-propose-1",
                iteration=2,
                status="COMPLETED",
                stop_reason="human_approved",
                recommendation="PASS",
                summary="Mission complete and approved.",
            )
            cached = {
                "status": "ready",
                "source": "llm",
                "engine": "claude",
                "fingerprint": fingerprint,
                "note": "Add Proposed Extension one-click from Run Results.",
                "rationale": "Extend the completed stance work into action.",
                "chain": [
                    {"role": "prompt", "content": "prompt body"},
                    {"role": "analysis", "content": "analysis body"},
                    {"role": "response", "content": "response body"},
                ],
                "generatedAt": "2026-07-19T12:00:00Z",
            }
            _write(abs_dir / "tmp" / "proposed-extension.json", cached)

            with mock.patch.object(zcomb, "_kick_extension_worker"):
                bridged = zcomb.build_bridge_state(project)
            prop = bridged["runResults"]["proposedExtension"]
            self.assertEqual(prop["status"], "ready")
            self.assertEqual(prop["source"], "llm")
            self.assertEqual(
                prop["note"],
                "Add Proposed Extension one-click from Run Results.",
            )
            self.assertEqual(prop["chain"][0]["role"], "prompt")

    def test_ensure_proposed_extension_sync_uses_llm_then_cache(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            abs_dir.mkdir(parents=True)
            ctx = {
                "objective": "Demo objective",
                "status": "COMPLETED",
                "stopReason": "human_approved",
                "recommendation": "PASS",
                "summary": "Done.",
                "blockingFindings": [],
                "iteration": 1,
                "costUsd": 1.0,
                "projectName": "demo",
                "loopId": "loop-x",
                "engine": "claude",
            }
            fingerprint = zcomb._extension_fingerprint(
                loop_id="loop-x",
                iteration=1,
                status="COMPLETED",
                stop_reason="human_approved",
                recommendation="PASS",
                summary="Done.",
            )
            llm_raw = json.dumps({
                "analysis": "Objective landed cleanly.",
                "note": "Document the Run Results extend affordance.",
                "rationale": "Capture the new one-click path for operators.",
            })
            with mock.patch.object(
                zcomb, "_call_extension_llm", return_value=(llm_raw, "claude")
            ) as call_llm, mock.patch.dict(
                os.environ, {"ABSOLOOP_EXTEND_PROPOSE": "sync"}
            ):
                first = zcomb._ensure_proposed_extension(
                    project, abs_dir=abs_dir, ctx=ctx, fingerprint=fingerprint)
                second = zcomb._ensure_proposed_extension(
                    project, abs_dir=abs_dir, ctx=ctx, fingerprint=fingerprint)
                self.assertEqual(call_llm.call_count, 1)
            self.assertEqual(first["status"], "ready")
            self.assertEqual(first["source"], "llm")
            self.assertEqual(
                first["note"],
                "Document the Run Results extend affordance.",
            )
            self.assertEqual(second["note"], first["note"])


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


class DashboardAttachTests(unittest.TestCase):
    def test_ensure_dashboard_retargets_when_supported(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            state_dir = project / ".absoloop" / "zcomb" / "state"
            state_dir.mkdir(parents=True)
            with mock.patch.object(zcomb, "_port_in_use", return_value=True), \
                 mock.patch.object(zcomb, "retarget_dashboard",
                                   return_value=True) as retarget, \
                 mock.patch.object(zcomb, "stop_dashboard") as stop, \
                 mock.patch.object(zcomb, "start_server") as start:
                proc, status = zcomb.ensure_dashboard(project, state_dir, 3141)
            self.assertIsNone(proc)
            self.assertEqual(status, "retargeted")
            retarget.assert_called_once()
            stop.assert_not_called()
            start.assert_not_called()

    def test_ensure_dashboard_restarts_stale_pre_retarget_server(self):
        """Health-up but no /api/retarget → replace the process."""
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            state_dir = project / ".absoloop" / "zcomb" / "state"
            state_dir.mkdir(parents=True)
            fake = mock.Mock()
            with mock.patch.object(zcomb, "_port_in_use", return_value=True), \
                 mock.patch.object(zcomb, "retarget_dashboard",
                                   return_value=False), \
                 mock.patch.object(zcomb, "stop_dashboard",
                                   return_value=True) as stop, \
                 mock.patch.object(zcomb, "start_server",
                                   return_value=fake) as start, \
                 mock.patch.object(zcomb, "wait_ready", return_value=True):
                proc, status = zcomb.ensure_dashboard(project, state_dir, 3141)
            self.assertIs(proc, fake)
            self.assertEqual(status, "restarted")
            stop.assert_called_once_with(3141)
            start.assert_called_once()


class LoopSettingsTests(unittest.TestCase):
    def test_save_loop_settings_updates_runtime_not_live_process(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            _write(abs_dir / "runtime.json", {
                "objective": "Tune engines",
                "max_iterations": 5,
                "engine": "claude",
                "model": "best",
                "loop_id": "loop-settings",
            })
            with mock.patch.object(zcomb, "_engine_on_path",
                                   side_effect=lambda name: name in ("claude", "codex")):
                result = zcomb.save_loop_settings(
                    project, engine="codex", model="gpt-5.6-terra", theme="light")
            self.assertTrue(result["ok"])
            self.assertEqual(result["engine"], "codex")
            self.assertEqual(result["model"], "gpt-5.6-terra")
            self.assertEqual(result["theme"], "light")
            self.assertEqual(result["applyOn"], "next_loop")
            runtime = json.loads((abs_dir / "runtime.json").read_text(encoding="utf-8"))
            self.assertEqual(runtime["engine"], "codex")
            self.assertEqual(runtime["model"], "gpt-5.6-terra")
            ui = json.loads(
                (abs_dir / "zcomb" / "ui-settings.json").read_text(encoding="utf-8"))
            self.assertEqual(ui["theme"], "light")
            self.assertEqual(ui["engine"], "codex")

    def test_bridge_settings_lists_only_available_engines_as_selectable(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            _write(abs_dir / "runtime.json", {
                "objective": "Settings catalog",
                "max_iterations": 3,
                "engine": "grok",
                "model": "grok-build-0.1",
            })
            with mock.patch.object(zcomb, "_engine_on_path",
                                   side_effect=lambda name: name == "grok"):
                metrics = zcomb.build_bridge_state(project)["metrics"]
            settings = metrics["settings"]
            available = [e for e in settings["engines"] if e["available"]]
            self.assertEqual([e["id"] for e in available], ["grok"])
            self.assertEqual(settings["engine"], "grok")
            self.assertTrue(any(m["id"] == "grok-build-0.1"
                                for m in available[0]["models"]))

    def test_rejects_unavailable_engine(self):
        with tempfile.TemporaryDirectory() as tmp:
            project = pathlib.Path(tmp)
            abs_dir = project / ".absoloop"
            _write(abs_dir / "runtime.json", {"objective": "x", "max_iterations": 1})
            with mock.patch.object(zcomb, "_engine_on_path",
                                   side_effect=lambda name: name == "claude"):
                result = zcomb.save_loop_settings(project, engine="grok")
            self.assertFalse(result["ok"])
            self.assertIn("not available", result["error"])


if __name__ == "__main__":
    unittest.main()
