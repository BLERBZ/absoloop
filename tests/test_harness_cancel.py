"""Cross-process cancel: live PID tracking, cancel flag, and CLI cancel."""
from __future__ import annotations

import os
import pathlib
import stat
import subprocess
import sys
import tempfile
import threading
import time
import unittest

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))

os.environ.setdefault("ABSOLOOP_CHIME", "0")

from absoloop_harness import runtime as run_ctrl
from absoloop_harness.config import Config, DEFAULTS
from absoloop_harness.core import AgentRequest, EventType
from absoloop_harness.orchestrator import Orchestrator
from absoloop_harness.providers.grok import GrokAdapter
from absoloop_harness.workspace import RunStore

FAKE = pathlib.Path(__file__).resolve().parent / "fakes" / "fake_provider.py"


def _fake_cfg() -> Config:
    import copy
    import os
    FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)
    values = copy.deepcopy(DEFAULTS)
    for provider in ("grok", "claude", "codex"):
        values["providers"][provider] = {
            "command": str(FAKE), "model": "", "timeout_seconds": 60,
            "env_allowlist": ["FAKE_PROVIDER_MODE", "FAKE_PROVIDER_SESSION",
                              "FAKE_PROVIDER_EDIT_FILE"],
        }
    values["gates"]["required"] = []
    values["gates"]["commands"] = {"tests": ""}
    return Config(values, {})


def make_repo(root: pathlib.Path) -> None:
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.email", "t@t"], check=True)
    subprocess.run(["git", "-C", str(root), "config", "user.name", "t"], check=True)
    (root / "base.txt").write_text("base\n", encoding="utf-8")
    subprocess.run(["git", "-C", str(root), "add", "-A"], check=True)
    subprocess.run(["git", "-C", str(root), "commit", "-qm", "init"], check=True)


class RuntimeHelpers(unittest.TestCase):
    def test_begin_register_cancel_finish(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "run-x"
            run_ctrl.begin_run(run_dir, run_id="run-x", strategy="single",
                               providers=["grok"])
            live = run_ctrl.read_live(run_dir)
            self.assertEqual(live["status"], "running")
            self.assertEqual(live["orchestrator_pid"], __import__("os").getpid())

            run_ctrl.register_child(run_dir, role="grok", provider="grok",
                                    pid=os_getpid(), pgid=os_getpid())
            self.assertEqual(len(run_ctrl.read_live(run_dir)["children"]), 1)

            run_ctrl.request_cancel(run_dir)
            self.assertTrue(run_ctrl.cancel_requested(run_dir))
            self.assertTrue(run_ctrl.cancel_flag_path(run_dir).is_file())

            run_ctrl.unregister_child(run_dir, "grok")
            run_ctrl.finish_run(run_dir, "cancelled")
            self.assertEqual(run_ctrl.read_live(run_dir)["status"], "cancelled")
            self.assertEqual(run_ctrl.read_live(run_dir)["children"], [])

    def test_cancel_already_finished(self):
        with tempfile.TemporaryDirectory() as tmp:
            run_dir = pathlib.Path(tmp) / "done"
            run_ctrl.begin_run(run_dir, run_id="done", strategy="single",
                               providers=["grok"])
            run_ctrl.finish_run(run_dir, "completed")
            result = run_ctrl.cancel_run(run_dir)
            self.assertFalse(result["ok"])
            self.assertEqual(result["reason"], "already_finished")


def os_getpid():
    import os
    return os.getpid()


class CancelViaFlag(unittest.TestCase):
    def tearDown(self):
        import os
        os.environ["FAKE_PROVIDER_MODE"] = "success"

    def test_adapter_honors_external_cancel_flag(self):
        import os
        os.environ["FAKE_PROVIDER_MODE"] = "hang"
        FAKE.chmod(FAKE.stat().st_mode | stat.S_IXUSR)
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            store = RunStore(root, "cancel-flag-run")
            run_ctrl.begin_run(store.run_dir, run_id=store.run_id,
                               strategy="single", providers=["grok"])
            adapter = GrokAdapter({
                "command": str(FAKE),
                "env_allowlist": ["FAKE_PROVIDER_MODE"],
            })
            adapter.bind_run(store.run_dir, "grok")
            events = []

            def consume():
                request = AgentRequest(prompt="hang", cwd=tmp,
                                       permission_profile="edit",
                                       timeout_seconds=30)
                events.extend(list(adapter.start(request, run_id=store.run_id)))

            thread = threading.Thread(target=consume)
            thread.start()
            # Wait until the child is registered in live.json
            for _ in range(50):
                if run_ctrl.read_live(store.run_dir).get("children"):
                    break
                time.sleep(0.1)
            self.assertTrue(run_ctrl.read_live(store.run_dir).get("children"),
                            "child never registered")
            result = run_ctrl.cancel_run(store.run_dir)
            self.assertTrue(result["ok"])
            thread.join(timeout=15)
            self.assertFalse(thread.is_alive())
            types = [e.type for e in events]
            self.assertIn(EventType.RUN_FAILED, types)
            cancelled = [e for e in events if e.type == EventType.RUN_FAILED
                         and e.data.get("cancelled")]
            self.assertTrue(cancelled, events)


class CancelOrchestrator(unittest.TestCase):
    def tearDown(self):
        import os
        os.environ["FAKE_PROVIDER_MODE"] = "success"

    def test_single_records_cancelled_status(self):
        import os
        os.environ["FAKE_PROVIDER_MODE"] = "hang"
        with tempfile.TemporaryDirectory() as tmp:
            root = pathlib.Path(tmp)
            make_repo(root)
            orch = Orchestrator(root, _fake_cfg())
            holder = {}

            def run():
                holder["manifest"] = orch.single(
                    "grok", "hang forever", "edit", run_id="orch-cancel")

            thread = threading.Thread(target=run)
            thread.start()
            store = RunStore(root, "orch-cancel")
            for _ in range(50):
                if run_ctrl.is_run_live(store.run_dir):
                    break
                time.sleep(0.1)
            self.assertTrue(run_ctrl.is_run_live(store.run_dir))
            # Cross-terminal cancel: flag + kill process groups.
            result = run_ctrl.cancel_run(store.run_dir)
            self.assertTrue(result["ok"], result)
            thread.join(timeout=20)
            self.assertFalse(thread.is_alive())
            manifest = holder.get("manifest") or store.read_manifest()
            self.assertEqual(manifest.get("status"), "cancelled")
            self.assertIsNone(manifest.get("selected_candidate"))
            self.assertFalse(run_ctrl.is_run_live(store.run_dir))


if __name__ == "__main__":
    unittest.main()
