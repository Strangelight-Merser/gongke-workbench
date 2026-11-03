const { test } = require('node:test');
const assert = require('node:assert/strict');
const { mkdtempSync, writeFileSync, rmSync } = require('node:fs');
const { tmpdir } = require('node:os');
const { join } = require('node:path');
const { contentRect } = require('../../dist-electron/embed/geometry.cjs');
const { EmbedTransport } = require('../../dist-electron/embed/transport.cjs');

test('CSS 边界按缩放转换并裁在客户区，负坐标不能覆盖工程侧栏外窗口', () => {
  assert.deepEqual(contentRect({x: -10, y: 20, width: 300, height: 400, visible: true}, 500, 500, 1.5),
    { x: 0, y: 30, width: 435, height: 470, visible: true });
  assert.deepEqual(contentRect({x: 800, y: 900, width: 30, height: 40, visible: false}, 500, 500, 1),
    { x: 500, y: 500, width: 0, height: 0, visible: false });
  for (const invalid of [NaN, Infinity, -Infinity])
    assert.throws(() => contentRect({x: invalid, y: 0, width: 10, height: 10, visible: true}, 500, 500, 1));
  assert.throws(() => contentRect({x: 0, y: 0, width: -1, height: 10, visible: true}, 500, 500, 1));
});

test('JSONL 分片、中文、乱序回执和原生错误不串请求，辅助进程退出使待决请求失败', async () => {
  const directory = mkdtempSync(join(tmpdir(), 'gongke-embed-'));
  const file = join(directory, 'helper.cjs');
  writeFileSync(file, `
    const rl = require('node:readline').createInterface({input: process.stdin});
    const send = obj => process.stdout.write(JSON.stringify(obj)+'\\n');
    rl.on('line', line => {
      const r = JSON.parse(line);
      if (r.method === 'late') return setTimeout(() => send({id:r.id,result:'晚到'}), 40);
      if (r.method === 'fail') return send({id:r.id,error:'原生拒绝'});
      if (r.method === 'exit') return process.exit(7);
      if (r.method === 'shutdown') { send({id:r.id,result:{ok:true}}); return process.exit(0); }
      const out=Buffer.from(JSON.stringify({id:r.id,result:'窗口 ready'})+'\\n');
      process.stdout.write(out.subarray(0, out.length-3));
      setTimeout(()=>process.stdout.write(out.subarray(out.length-3)),5);
    });
  `);
  const transport = new EmbedTransport(process.execPath, [file]);
  try {
    assert.deepEqual(await Promise.all([transport.request('late'), transport.request('unicode')]), ['晚到','窗口 ready']);
    await assert.rejects(transport.request('fail'), /原生拒绝/);
    await assert.rejects(transport.request('exit'), /已退出/);
    await assert.rejects(transport.request('status'), /不可用/);
  } finally { await transport.stop(); rmSync(directory, { recursive: true }); }
});
