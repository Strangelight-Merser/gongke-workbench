"""握手和纯机械计算不依赖几何/数值扩展的冷加载。"""
import json
from pathlib import Path
import subprocess
import sys


def test_stdio_does_not_preload_numeric_extensions(tmp_path):
    # 将不应触达的导入直接拒绝，比依赖本机热缓存的耗时断言更明确。
    bootstrap = '''
import sys, importlib.abc, runpy
class NoNumericPreload(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path=None, target=None):
        if fullname.split('.')[0] in {'numpy', 'scipy', 'OCP', 'build123d'}:
            raise AssertionError('Unexpected startup import: ' + fullname)
sys.meta_path.insert(0, NoNumericPreload())
runpy.run_module('gongke_app.service', run_name='__main__')
'''
    requests = [dict(id=1, method='system.status'),
                dict(id=2, method='project.create', params={'path': str(tmp_path / '工程'), 'teaching': True}),
                dict(id=3, method='design.calculate')]
    result = subprocess.run([sys.executable, '-c', bootstrap, '--state-dir', str(tmp_path / 'state')],
        input=''.join(json.dumps(item) + '\n' for item in requests), capture_output=True,
        text=True, cwd=Path(__file__).resolve().parents[1], timeout=15)
    assert result.returncode == 0, result.stderr
    replies = {row['id']: row for row in map(json.loads, result.stdout.splitlines()) if 'id' in row}
    assert all('error' not in replies[key] for key in (1, 2, 3)), replies


def test_stdio_handshake_without_reverse_dns(tmp_path):
    bootstrap = """
import socket, runpy
def reject_dns(*args, **kwargs):
    raise AssertionError('本机服务不能依赖反向 DNS')
socket.getfqdn = reject_dns
socket.gethostbyaddr = reject_dns
runpy.run_module('gongke_app.service', run_name='__main__')
"""
    result = subprocess.run([sys.executable, '-c', bootstrap, '--state-dir', str(tmp_path / 'state')],
        input=json.dumps(dict(id=1, method='system.status')) + '\n', capture_output=True,
        text=True, cwd=Path(__file__).resolve().parents[1], timeout=15)
    assert result.returncode == 0, result.stderr
    replies = [json.loads(row) for row in result.stdout.splitlines()]
    reply = next(row for row in replies if row.get('id') == 1)
    assert 'result' in reply and 'error' not in reply, replies
