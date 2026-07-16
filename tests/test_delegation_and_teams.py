"""Two-layer teams: env injection, delegation posture, Grok mission argv."""
from __future__ import annotations

import os
import pathlib
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness.config import DEFAULTS
from absoloop_harness.core import AgentEvent, AgentRequest, EventType
from absoloop_harness.delegation import delegation_posture, with_delegation
from absoloop_harness.providers.claude import ClaudeAdapter
from absoloop_harness.providers.grok import GrokAdapter
from absoloop_harness.spawn_evidence import (
    events_show_inner_teams,
    events_show_outer_spawn,
    text_shows_inner_teams,
)


class DefaultEnvAllowlists(unittest.TestCase):
    def test_defaults_allowlist_team_and_auth_keys(self):
        self.assertIn("XAI_API_KEY", DEFAULTS["providers"]["grok"]["env_allowlist"])
        self.assertIn("GROK_HOME", DEFAULTS["providers"]["grok"]["env_allowlist"])
        self.assertIn("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS",
                      DEFAULTS["providers"]["claude"]["env_allowlist"])
        self.assertIn("ANTHROPIC_API_KEY",
                      DEFAULTS["providers"]["claude"]["env_allowlist"])
        self.assertIn("OPENAI_API_KEY",
                      DEFAULTS["providers"]["codex"]["env_allowlist"])


class ClaudeTeamsEnv(unittest.TestCase):
    def test_provider_extra_env_enables_agent_teams(self):
        adapter = ClaudeAdapter({})
        request = AgentRequest(prompt="hi", cwd=".", permission_profile="read")
        env = adapter.provider_extra_env(request)
        self.assertEqual(env.get("CLAUDE_CODE_EXPERIMENTAL_AGENT_TEAMS"), "1")


class DelegationPosture(unittest.TestCase):
    def test_engine_specific_blocks(self):
        self.assertIn("Agent Teams", delegation_posture("claude"))
        self.assertIn("subagents", delegation_posture("codex"))
        self.assertIn("spawn_subagent", delegation_posture("grok"))

    def test_with_delegation_skips_read_profile(self):
        prompt = "Implement the feature"
        self.assertEqual(with_delegation(prompt, "claude", "read"), prompt)
        tasked = with_delegation(prompt, "claude", "edit")
        self.assertIn(prompt, tasked)
        self.assertIn("Agent Teams", tasked)

    def test_orchestrator_request_appends_posture(self):
        from absoloop_harness.config import Config
        from absoloop_harness.orchestrator import Orchestrator
        orch = Orchestrator(pathlib.Path("."), Config(DEFAULTS, {}))
        req = orch._request("do the work", pathlib.Path("."), "edit", "grok")
        self.assertIn("spawn_subagent", req.prompt)
        read_req = orch._request("review only", pathlib.Path("."), "read", "grok")
        self.assertNotIn("spawn_subagent", read_req.prompt)


class GrokMissionArgv(unittest.TestCase):
    def test_harness_grok_uses_prompt_file_and_streaming_json(self):
        adapter = GrokAdapter({})
        with tempfile.TemporaryDirectory() as tmp:
            request = AgentRequest(prompt="hello world", cwd=tmp,
                                   permission_profile="edit")
            argv, stdin = adapter.build_argv(request, None, pathlib.Path(tmp))
        self.assertIsNone(stdin)
        joined = " ".join(argv)
        self.assertIn("--prompt-file", joined)
        self.assertIn("streaming-json", joined)

    def test_mission_runner_grok_permission_and_extract(self):
        # Load templates/absoloop-run without executing main (__name__ != __main__).
        import runpy
        runner_path = (pathlib.Path(__file__).resolve().parent.parent
                       / "templates" / "absoloop-run")
        ns = runpy.run_path(str(runner_path), run_name="absoloop_run_tmpl")
        flags = ns["grok_permission_flags"]("read")
        self.assertIn("--tools", flags)
        edit = ns["grok_permission_flags"]("edit")
        self.assertIn("--allow", edit)
        parsed = ns["_extract_json_object"](
            'noise {"done": false, "summary": "x"} trailing')
        self.assertEqual(parsed.get("done"), False)
        posture = ns["delegation_posture"]("claude")
        self.assertIn("Agent Teams", posture)


class SpawnEvidence(unittest.TestCase):
    def test_outer_and_inner_markers(self):
        events = [
            AgentEvent(type=EventType.RUN_STARTED, provider="claude",
                       text="claude started", raw_type="_absoloop_spawn"),
            AgentEvent(type=EventType.TOOL_STARTED, provider="claude",
                       text="Task", data={"tool": "spawn_subagent"}),
        ]
        self.assertTrue(events_show_outer_spawn(events))
        self.assertTrue(events_show_inner_teams(events))
        self.assertTrue(text_shows_inner_teams("spawned a teammate for review"))


class MissionEngines(unittest.TestCase):
    def test_cli_engines_include_grok(self):
        cli_path = pathlib.Path(__file__).resolve().parent.parent / "bin" / "absoloop"
        import importlib.util
        spec = importlib.util.spec_from_file_location("absoloop_cli", cli_path)
        # bin/absoloop is a script with side effects on import — only check source.
        text = cli_path.read_text(encoding="utf-8")
        self.assertIn('ENGINES = ("claude", "codex", "grok")', text)
        self.assertIn('"grok"', text)
        self.assertIn("permission_profile", text)


if __name__ == "__main__":
    unittest.main()
