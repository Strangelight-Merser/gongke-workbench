"""运行真实应用服务，收集与 Electron 相同的 JSON Lines 响应和事件。"""
import json
from pathlib import Path
import subprocess
import sys
import threading
import time

ROOT = Path(__file__).resolve().parents[1]


class ServiceProcess:
    def __init__(self, tmp_path, command=None, *, project=None, env=None):
        self.state = tmp_path / "state"
        self.project = project or tmp_path / "project"
        self.events, self.responses = [], {}
        self.condition = threading.Condition()
        self.serial = 0
        self.stderr = (tmp_path / "service.log").open("w", encoding="utf-8")
        self.process = subprocess.Popen([*(command or [sys.executable, "-m", "gongke_app.service"]),
                                         "--state-dir", str(self.state)], cwd=ROOT, stdin=subprocess.PIPE,
                                        stdout=subprocess.PIPE, stderr=self.stderr, text=True, encoding="utf-8", env=env)
        def read():
            for line in self.process.stdout:
                value = json.loads(line)
                with self.condition:
                    if "id" in value:
                        self.responses[value["id"]] = value
                    else:
                        self.events.append(value)
                    self.condition.notify_all()
        self.reader = threading.Thread(target=read, daemon=True)
        self.reader.start()
        method = "project.open" if (self.project / "gongke-project.json").exists() else "project.create"
        self.request(method, {"path": str(self.project)})

    def request(self, method, params=None):
        with self.condition:
            self.serial += 1
            request_id = self.serial
            self.process.stdin.write(json.dumps({"id": request_id, "method": method, "params": params or {}}) + "\n")
            self.process.stdin.flush()
            if not self.condition.wait_for(lambda: request_id in self.responses, timeout=90):
                raise AssertionError(f"服务未响应 {method}; exit={self.process.poll()}")
            response = self.responses.pop(request_id)
        if "error" in response:
            raise ValueError(response["error"]["message"])
        return response["result"]

    def close(self):
        self.process.stdin.close()
        self.process.wait(timeout=90)
        self.reader.join(timeout=5)
        self.stderr.close()
        assert self.process.returncode == 0
