"""临时 macOS CI 探针；记录早期 Python 导入及栈，不替代原始 15 秒测试。"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

root = Path(__file__).resolve().parents[1]
output = root / "out/service-startup/probe"
output.mkdir(parents=True, exist_ok=True)
# 在导入应用前开启定时栈；连 service.module.enter 都没到时仍有证据。
bootstrap = '''
import faulthandler, runpy, sys
stack = open(sys.argv.pop(1), 'w')
faulthandler.enable(file=stack, all_threads=True)
faulthandler.dump_traceback_later(5, repeat=True, file=stack)
runpy.run_module('gongke_app.service', run_name='__main__')
'''
requests = [{"id": 1, "method": "system.status"},
            {"id": 2, "method": "project.create", "params": {"path": str(output / "project"), "teaching": True}},
            {"id": 3, "method": "design.calculate"}]
started = time.monotonic()
try:
    result = subprocess.run([sys.executable, '-X', 'importtime', '-c', bootstrap,
                             str(output / 'early-stack.log'), '--state-dir', str(output / 'state')],
        cwd=root, env={**os.environ, 'GONGKE_STARTUP_TRACE_DIR': str(output)},
        input=''.join(json.dumps(row) + '\n' for row in requests).encode(), capture_output=True, timeout=15)
    stdout, stderr = result.stdout, result.stderr
    summary = {'returncode': result.returncode, 'timed_out': False}
except subprocess.TimeoutExpired as error:
    stdout, stderr = error.stdout or b'', error.stderr or b''
    summary = {'timed_out': True}
summary['elapsed_s'] = time.monotonic() - started
(output / 'stdout.jsonl').write_bytes(stdout)
(output / 'imports.log').write_bytes(stderr)
(output / 'result.json').write_text(json.dumps(summary, indent=2), encoding='utf-8')
print(json.dumps(summary))
# 原测试先运行；本探针只补充诊断，不改变原测试的红绿结果。
