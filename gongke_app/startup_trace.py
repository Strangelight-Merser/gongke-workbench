"""临时 CI 启动诊断；定位 41771770952 后删除，不记录请求、凭据或局部变量。"""
_stream = None
_started = None


def start(enabled):
    import os
    directory = os.environ.get("GONGKE_STARTUP_TRACE_DIR") if enabled else None
    if not directory:
        return
    import atexit
    import faulthandler
    from pathlib import Path
    import time
    global _stream, _started
    Path(directory).mkdir(parents=True, exist_ok=True)
    _stream = (Path(directory) / f"service-{os.getpid()}.log").open("w", encoding="utf-8", buffering=1)
    _started = time.monotonic()
    faulthandler.enable(file=_stream, all_threads=True)
    # 原测试 15 秒超时之前留下两次全线程栈，不能等原来的 60 秒。
    faulthandler.dump_traceback_later(5, repeat=True, file=_stream)
    def finish():
        stage("process.exit")
        faulthandler.cancel_dump_traceback_later()
        faulthandler.disable()
        _stream.close()
    atexit.register(finish)
    stage("service.module.enter")


def stage(name):
    if _stream is not None:
        import time
        _stream.write(f"{time.monotonic() - _started:.6f} {name}\n")
