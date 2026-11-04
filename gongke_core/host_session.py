"""宿主会话的进程身份与跨进程锁；不加载 CAD 运行时。"""
import json
import errno
import time
import os
from pathlib import Path
import subprocess


def endpoint_path():
    return Path(os.environ.get("GONGKE_FREECAD_SESSION", "~/.local/share/gongke/freecad-session.json")).expanduser()


def process_identity(pid):
    if not isinstance(pid, int) or pid <= 0:
        return None
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
        kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
        handle = kernel.OpenProcess(0x1000 | 0x100000, False, pid)
        if not handle:
            if ctypes.get_last_error() == 87:
                return None
            raise OSError(ctypes.get_last_error(), "无法核对宿主进程身份")
        try:
            if kernel.WaitForSingleObject(handle, 0) == 0:
                return None
            times = [wintypes.FILETIME() for _ in range(4)]
            buffer = ctypes.create_unicode_buffer(32768)
            length = wintypes.DWORD(len(buffer))
            if not kernel.GetProcessTimes(handle, *(ctypes.byref(t) for t in times)) or not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(length)):
                raise ctypes.WinError(ctypes.get_last_error())
            return {"pid": pid, "started": (times[0].dwHighDateTime << 32) | times[0].dwLowDateTime, "command": buffer.value}
        finally:
            kernel.CloseHandle(handle)
    result = subprocess.run(["ps", "-ww", "-p", str(pid), "-o", "stat=,lstart=,command="], capture_output=True, text=True, timeout=3, env={**os.environ, "LC_ALL": "C"})
    if result.returncode == 1 and not result.stdout.strip():
        return None
    result.check_returncode()
    fields = result.stdout.strip().split(None, 6)
    if not fields or fields[0].startswith("Z"):
        return None
    return {"pid": pid, "started": " ".join(fields[1:6]), "command": fields[6]}


class FileLock:
    def __init__(self, path, blocking=False):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.file = path.open("a+b")
        try:
            if os.name == "nt":
                import msvcrt
                self.file.seek(0)
                if not self.file.read(1):
                    self.file.write(b"0")
                    self.file.flush()
                self.file.seek(0)
                acquire = lambda: msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
            else:
                import fcntl
                acquire = lambda: fcntl.flock(self.file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
            # Windows LK_LOCK 只重试约 10 秒，短于 FreeCAD 冷启动预算。
            deadline = time.monotonic() + 60
            while True:
                try:
                    acquire()
                    break
                except OSError as exc:
                    if not blocking or exc.errno not in {errno.EACCES, errno.EAGAIN, errno.EDEADLK}:
                        raise
                    if time.monotonic() >= deadline:
                        raise TimeoutError("另一连接仍在启动 FreeCAD，请稍后重试") from exc
                    time.sleep(.1)
        except BaseException:
            self.file.close()
            raise

    def close(self):
        self.file.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()


def remove_session(path, token):
    try:
        if json.loads(path.read_text(encoding="utf-8")).get("token") == token:
            path.unlink()
    except FileNotFoundError:
        pass
