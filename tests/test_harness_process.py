"""Integration tests driving real adapters against the fake provider
executable: success, partial JSON, unknown events, stderr noise, non-zero
exit, timeout, cancellation, live session capture, and secret redaction."""
from __future__ import annotations

import os
import pathlib
import stat
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

from absoloop_harness.core import AgentRequest, EventType
from absoloop_harness.process import SupervisedProcess, build_child_env
from absoloop_harness.providers.claude import ClaudeAdapter
from absoloop_harness.providers.codex import CodexAdapter
from absoloop_harness.providers.grok import GrokAdapter

FAKE = pathlib.Path(__file__).resolve().parent / "fakes" / "fake_provider.py"


def _ensure_executable() -> str:
    FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
    return str(FAKE)


def _adapter(kind, mode="success", extra_env=None):
    classes = {"grok": GrokAdapter, "claude": ClaudeAdapter, "codex": CodexAdapter}
    adapter = classes[kind]({"command": _ensure_executable(),
                             "env_allowlist": ["FAKE_PROVIDER_MODE",
                                               "FAKE_PROVIDER_SESSION",
                                               "FAKE_PROVIDER_EDIT_FILE"]})
    os.environ["FAKE_PROVIDER_MODE"] = mode
    return adapter


def _run(adapter, prompt="do the task", timeout=30.0, run_id="t"):
    with tempfile.TemporaryDirectory() as tmp:
        request = AgentRequest(prompt=prompt, cwd=tmp, permission_profile="edit",
                               timeout_seconds=timeout)
        return list(adapter.start(request, run_id=run_id))


class SuccessRuns(unittest.TestCase):
    def test_all_three_providers_normalize_success(self):
        for kind in ("grok", "claude", "codex"):
            adapter = _adapter(kind)
            events = _run(adapter)
            types = [event.type for event in events]
            self.assertEqual(types[0], EventType.RUN_STARTED, kind)
            self.assertIn(EventType.RUN_COMPLETED, types, kind)
            self.assertNotIn(EventType.RUN_FAILED, types, kind)
            self.assertEqual(adapter.last_session.native_id, "fake-session-123", kind)

    def test_stderr_never_pollutes_events(self):
        adapter = _adapter("grok", mode="stderr-noise")
        events = _run(adapter)
        self.assertIn(EventType.RUN_COMPLETED, [e.type for e in events])
        self.assertIn("update available", adapter.last_outcome.stderr)
        for event in events:
            self.assertNotIn("update available", event.text)


class Misbehavior(unittest.TestCase):
    def test_partial_json_surfaces_as_unknown(self):
        events = _run(_adapter("grok", mode="partial-json"))
        unknown = [e for e in events if e.raw_type == "_unparsed"]
        self.assertTrue(unknown)
        self.assertIn(EventType.RUN_COMPLETED, [e.type for e in events])

    def test_unknown_events_preserved(self):
        events = _run(_adapter("codex", mode="unknown"))
        unknown = [e for e in events if e.type == EventType.UNKNOWN]
        self.assertTrue(any("totally.new.event" in e.raw_type for e in unknown))
        self.assertIn(EventType.RUN_COMPLETED, [e.type for e in events])

    def test_nonzero_exit_is_run_failed(self):
        for kind in ("grok", "claude", "codex"):
            events = _run(_adapter(kind, mode="fail"))
            self.assertIn(EventType.RUN_FAILED, [e.type for e in events], kind)
            self.assertNotIn(EventType.RUN_COMPLETED, [e.type for e in events], kind)

    def test_timeout_kills_and_reports(self):
        adapter = _adapter("grok", mode="hang")
        started = time.time()
        events = _run(adapter, timeout=2.0)
        self.assertLess(time.time() - started, 30)
        failed = [e for e in events if e.type == EventType.RUN_FAILED]
        self.assertTrue(failed and failed[0].data.get("timed_out"))

    def test_cancellation_terminates_group(self):
        adapter = _adapter("claude", mode="hang")
        collected = []

        def consume():
            collected.extend(_run(adapter, timeout=60.0, run_id="cancel-me"))

        thread = threading.Thread(target=consume)
        thread.start()
        time.sleep(1.0)
        adapter.cancel("cancel-me")
        thread.join(timeout=15)
        self.assertFalse(thread.is_alive(), "cancel did not unblock the stream")
        failed = [e for e in collected if e.type == EventType.RUN_FAILED]
        self.assertTrue(failed and failed[0].data.get("cancelled"))


class Redaction(unittest.TestCase):
    def test_leaked_secret_redacted_from_stream(self):
        events = _run(_adapter("grok", mode="leak"))
        joined = " ".join(event.text for event in events)
        self.assertNotIn("xai-supersecretapikey1234567890", joined)
        self.assertIn("[REDACTED]", joined)


class EnvAllowlist(unittest.TestCase):
    def test_child_env_is_minimal(self):
        os.environ["ABSOLOOP_TEST_SECRET_TOKEN"] = "must-not-leak"
        try:
            env = build_child_env()
            self.assertNotIn("ABSOLOOP_TEST_SECRET_TOKEN", env)
            self.assertIn("PATH", env)
        finally:
            os.environ.pop("ABSOLOOP_TEST_SECRET_TOKEN", None)

    def test_allowlisted_extra_passes(self):
        os.environ["ABSOLOOP_TEST_PLAIN"] = "ok"
        try:
            env = build_child_env(["ABSOLOOP_TEST_PLAIN"])
            self.assertEqual(env["ABSOLOOP_TEST_PLAIN"], "ok")
        finally:
            os.environ.pop("ABSOLOOP_TEST_PLAIN", None)


class LiveResume(unittest.TestCase):
    def test_resume_streams_with_session(self):
        adapter = _adapter("codex")
        events = _run(adapter)
        session = adapter.last_session
        self.assertIsNotNone(session)
        with tempfile.TemporaryDirectory() as tmp:
            request = AgentRequest(prompt="continue", cwd=tmp,
                                   permission_profile="edit", timeout_seconds=30)
            resumed = list(adapter.resume(session, request, run_id="resume-t"))
        self.assertIn(EventType.RUN_COMPLETED, [e.type for e in resumed])


if __name__ == "__main__":
    unittest.main()
