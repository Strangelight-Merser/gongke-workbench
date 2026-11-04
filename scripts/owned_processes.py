"""验收专用进程收尾：只处理本次 Popen 创建的子进程。"""
import atexit
import os
import signal
import subprocess


class OwnedProcesses:
    def __init__(self):
        self.children = []
        atexit.register(self.close)
        # Windows SIGTERM/TerminateProcess 无法执行 Python 清理；控制台 Break 映射为 SIGBREAK。
        signals = (signal.SIGINT, signal.SIGBREAK) if os.name == "nt" else (signal.SIGINT, signal.SIGTERM)
        for sig in signals:
            signal.signal(sig, self.interrupt)

    def interrupt(self, signum, frame):
        self.close()
        raise SystemExit(128 + signum)

    def spawn(self, *args, **kwargs):
        child = subprocess.Popen(*args, **kwargs)
        self.children.append(child)
        return child

    def close(self):
        for child in reversed(self.children):
            if child.poll() is None:
                child.terminate()
                try:
                    child.wait(timeout=8)
                except subprocess.TimeoutExpired:
                    child.kill()
                    child.wait()
        self.children.clear()
