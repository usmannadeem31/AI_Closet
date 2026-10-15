"""Single-GPU model lifecycle. Only child processes owned here may be stopped."""
from contextlib import contextmanager
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import threading
import time
import urllib.request

from fastapi import HTTPException

MODELS = {
    "2b": {"label": "Qwen3-VL-2B · FP8", "repo": "Qwen/Qwen3-VL-2B-Instruct-FP8", "memory": "0.80"},
    "4b": {"label": "Qwen3-VL-4B · FP8", "repo": "Qwen/Qwen3-VL-4B-Instruct-FP8", "memory": "0.88"},
}
ALIAS = "ai-closet-local"
URL = "http://127.0.0.1:8000/v1"


def served():
    try:
        with urllib.request.urlopen(URL + "/models", timeout=1) as r:
            for model in json.load(r).get("data", []):
                if model["id"] == ALIAS:
                    return model
    except Exception:
        pass
    return None


class ModelRuntime:
    def __init__(self, root):
        self.root = Path(root)
        self.process = None
        self.selected = "2b"
        self.transition = False
        self.gate = threading.Lock()
        self.inference_active = False
        self.started_at = None
        self.startup_seconds = None
        self.log = self.root / "logs" / "gui-model-2b.log"
        self.error = None

    @staticmethod
    def identify(model):
        if model:
            for key, config in MODELS.items():
                if model.get("root") == config["repo"]:
                    return key
        return None

    def status(self):
        model = served()
        active = self.process is not None and self.process.poll() is None
        failed = bool(self.error) or (self.process is not None and self.process.poll() not in (None, 0))
        key = self.identify(model)
        state = "switching" if self.transition else "ready" if key else "starting" if active else "failed" if failed else "off"
        if state == "ready" and active and key == self.selected and self.started_at and self.startup_seconds is None:
            self.startup_seconds = round(time.monotonic() - self.started_at, 2)
        label = MODELS[key]["label"] if key else MODELS[self.selected]["label"]
        return {"state": state, "owned": active, "model": label, "active_model": key,
                "selected_model": self.selected, "inference_active": self.inference_active,
                "models": [{"id": k, **v} for k, v in MODELS.items()],
                "startup_seconds": self.startup_seconds,
                "log": (self.error or "") + (self.log.read_text(errors="replace")[-4000:] if failed and self.log.exists() else "")}

    def _stop(self):
        proc = self.process
        if proc and proc.poll() is None:
            # Stop only the process group we created, including GPU workers.
            try:
                os.killpg(proc.pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            try:
                proc.wait(timeout=15)
            except subprocess.TimeoutExpired:
                os.killpg(proc.pid, signal.SIGKILL)
                proc.wait(timeout=10)
            # A parent can exit while its workers are still shutting down.
            deadline = time.monotonic() + 15
            while time.monotonic() < deadline:
                try:
                    os.killpg(proc.pid, 0)
                except ProcessLookupError:
                    break
                time.sleep(0.2)
            else:
                try:
                    os.killpg(proc.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                time.sleep(1)
        self.process = None

    def launch(self, key):
        if key not in MODELS:
            raise HTTPException(422, "Choose the 2B or 4B model.")
        if not self.gate.acquire(blocking=False):
            raise HTTPException(409, "The AI is busy. Wait for the current answer or model switch.")
        try:
            current = served()
            current_key = self.identify(current)
            active = self.process is not None and self.process.poll() is None
            if current_key == key and not self.transition:
                self.selected = key
                return
            if active and key == self.selected:
                return
            if current and not active:
                raise HTTPException(409, "A model was started outside this website. Stop it in its terminal before switching here.")
            self.transition = True
            self.error = None
            self._stop()
            self.selected = key
            self.startup_seconds = None
            self.started_at = time.monotonic()
            self.log = self.root / "logs" / f"gui-model-{key}.log"
            self.log.parent.mkdir(parents=True, exist_ok=True)
            executable = Path(sys.executable).parent / "vllm"
            if not executable.exists():
                raise RuntimeError("Launch the website using the vllm Python environment.")
            config = MODELS[key]
            command = [str(executable), "serve", config["repo"], "--host", "127.0.0.1", "--port", "8000",
                       "--served-model-name", ALIAS, "--quantization", "fp8", "--dtype", "bfloat16", "--max-model-len", "2048",
                       "--max-num-seqs", "1", "--gpu-memory-utilization", config["memory"],
                       "--enforce-eager", "--limit-mm-per-prompt",
                       '{"image":{"count":1,"width":512,"height":512},"video":0}', "--mm-processor-cache-gb", "0"]
            with self.log.open("w") as log:
                self.process = subprocess.Popen(command, cwd=self.root,
                    env=dict(os.environ, VLLM_USE_FLASHINFER_SAMPLER="0"),
                    stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        except HTTPException:
            raise
        except Exception as exc:
            self.error = str(exc)
            raise HTTPException(500, "Could not start the model. Check startup details.") from exc
        finally:
            self.transition = False
            self.gate.release()

    def stop(self):
        if not self.gate.acquire(blocking=False):
            raise HTTPException(409, "Wait for the current answer or model switch before stopping.")
        try:
            self.transition = True
            self._stop()
            self.error = None
        finally:
            self.transition = False
            self.gate.release()

    @contextmanager
    def inference(self, expected=None):
        if not self.gate.acquire(blocking=False):
            raise HTTPException(409, "The AI is busy with another request. Please try again shortly.")
        try:
            model = served()
            key = self.identify(model)
            if self.transition or not key:
                raise HTTPException(503, "Start your selected model and wait until it is ready.")
            if expected and key != expected:
                raise HTTPException(409, "Your selected model is not loaded. Click Load selected model first.")
            self.inference_active = True
            yield key
        finally:
            self.inference_active = False
            self.gate.release()
