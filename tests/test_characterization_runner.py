"""Characterization tests for `templates/absoloop-run` stream parsing and
state logic — pinned before the harness refactor so legacy loop behavior
stays covered by regression tests.
"""
from __future__ import annotations

import json
import unittest

from tests._load import load_runner

run = load_runner()


class ClaudeStreamEvents(unittest.TestCase):
    def test_init_event(self):
        line = json.dumps({"type": "system", "subtype": "init", "model": "claude-x"})
        events = run.claude_stream_events(line)
        self.assertEqual(events, [("start", "session started (model claude-x)")])

    def test_tool_use_and_text(self):
        line = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Bash", "input": {"command": "ls"}},
            {"type": "text", "text": "done  now"},
        ]}})
        events = run.claude_stream_events(line)
        self.assertEqual(events[0], ("tool", "Bash: ls"))
        self.assertEqual(events[1], ("say", "done now"))

    def test_task_tool_emits_spawn_teammate_prefix(self):
        line = json.dumps({"type": "assistant", "message": {"content": [
            {"type": "tool_use", "name": "Task",
             "input": {"description": "Write unit tests for parser"}},
        ]}})
        events = run.claude_stream_events(line)
        self.assertEqual(events, [(
            "tool",
            "spawn teammate · Task: Write unit tests for parser",
        )])

    def test_garbage_line_is_ignored(self):
        self.assertEqual(run.claude_stream_events("{not json"), [])


class CodexStreamEvents(unittest.TestCase):
    def test_thread_started(self):
        line = json.dumps({"type": "thread.started", "thread_id": "t1"})
        self.assertEqual(run.codex_stream_events(line),
                         [("start", "session started")])

    def test_command_execution_with_exit(self):
        line = json.dumps({"type": "item.completed", "item": {
            "item_type": "command_execution", "command": "pytest", "exit_code": 1}})
        self.assertEqual(run.codex_stream_events(line),
                         [("tool", "ran: pytest (exit 1)")])

    def test_file_change(self):
        line = json.dumps({"type": "item.completed", "item": {
            "item_type": "file_change",
            "changes": [{"path": "a.py"}, {"path": "b.py"}]}})
        self.assertEqual(run.codex_stream_events(line),
                         [("tool", "edited: a.py, b.py")])

    def test_collab_spawn_agent_emits_spawn_teammate_prefix(self):
        line = json.dumps({"type": "item.started", "item": {
            "id": "item_0",
            "type": "collab_tool_call",
            "tool": "spawn_agent",
            "prompt": "Write unit tests for parser",
            "sender_thread_id": "thread-parent",
            "receiver_thread_ids": ["thread-child"],
            "agents_states": {
                "thread-child": {"status": "running", "message": None},
            },
            "status": "in_progress",
        }})
        self.assertEqual(run.codex_stream_events(line), [(
            "tool",
            "spawn teammate · spawn_agent: Write unit tests for parser",
        )])

    def test_collab_wait_is_plain_tool_not_spawn(self):
        line = json.dumps({"type": "item.completed", "item": {
            "id": "item_1",
            "type": "collab_tool_call",
            "tool": "wait",
            "prompt": None,
            "receiver_thread_ids": ["thread-child"],
            "agents_states": {},
            "status": "completed",
        }})
        events = run.codex_stream_events(line)
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0][0], "tool")
        self.assertTrue(events[0][1].startswith("wait:"))
        self.assertNotIn("spawn teammate", events[0][1])

    def test_usage(self):
        line = json.dumps({"type": "turn.completed",
                           "usage": {"input_tokens": 10, "output_tokens": 3}})
        events = run.codex_stream_events(line)
        self.assertEqual(events[0][0], "usage")

    def test_error(self):
        line = json.dumps({"type": "error", "message": "boom"})
        self.assertEqual(run.codex_stream_events(line), [("error", "boom")])

    def test_agent_message_strips_done_summary_json(self):
        blob = json.dumps({
            "done": False,
            "summary": "Starting a bounded parity slice",
            "changed_artifacts": [],
            "risks": [],
        }, separators=(",", ":"))
        line = json.dumps({"type": "item.completed", "item": {
            "item_type": "agent_message", "text": blob}})
        self.assertEqual(
            run.codex_stream_events(line),
            [("say", "Starting a bounded parity slice")],
        )


class Fingerprints(unittest.TestCase):
    def test_normalized_fingerprint_is_line_order_insensitive(self):
        self.assertEqual(run.normalized_fingerprint("a\nb"),
                         run.normalized_fingerprint("b\na"))

    def test_normalized_fingerprint_drops_volatile_lines(self):
        self.assertEqual(run.normalized_fingerprint("a\ntime=123"),
                         run.normalized_fingerprint("a\ntime=456"))

    def test_different_text_differs(self):
        self.assertNotEqual(run.normalized_fingerprint("a"),
                            run.normalized_fingerprint("b"))


class ThinkingRung(unittest.TestCase):
    def test_fallback_to_default_ladder(self):
        state = run.State(mission_id="m", repeated_failure_count=0)
        rung = run.thinking_rung({"thinking_ladder": "invalid"}, state)
        self.assertEqual(rung["claude_keyword"], "think")

    def test_caps_at_last_rung(self):
        state = run.State(mission_id="m", repeated_failure_count=99)
        rung = run.thinking_rung({}, state)
        self.assertEqual(rung["claude_keyword"], "ultrathink")

    def test_uses_runtime_ladder_when_valid(self):
        ladder = [{"claude_keyword": "custom", "codex_effort": "medium"}]
        state = run.State(mission_id="m", repeated_failure_count=0)
        rung = run.thinking_rung({"thinking_ladder": ladder}, state)
        self.assertEqual(rung["claude_keyword"], "custom")


class StateShape(unittest.TestCase):
    def test_state_roundtrip(self):
        from dataclasses import asdict
        state = run.State(mission_id="m", status="EXECUTING", iteration=2)
        clone = run.State(**asdict(state))
        self.assertEqual(asdict(clone), asdict(state))


if __name__ == "__main__":
    unittest.main()
