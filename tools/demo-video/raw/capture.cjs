// 原始录屏控制器。调用者只传自己启动的进程 PID；操作走真实产品界面。
const fs = require('node:fs');
const path = require('node:path');
const {spawn, spawnSync} = require('node:child_process');
const pause = ms => new Promise(resolve => setTimeout(resolve, ms));

async function startCapture(pids, directory) {
  if (!pids.length || pids.some(pid => !Number.isInteger(pid) || pid <= 0))
    throw Error('需要自有进程 PID');
  const out = path.resolve(directory);
  if (fs.existsSync(out)) throw Error(`输出目录已存在：${out}`);
  fs.mkdirSync(out, {recursive: true});
  const binary = path.join(out, 'window-capture');
  const compile = spawnSync('swiftc', ['-parse-as-library', path.join(__dirname, 'window-capture.swift'), '-o', binary], {encoding:'utf8'});
  if (compile.status !== 0) throw Error(compile.stderr);
  const child = spawn(binary, [pids.join(','), out], {stdio:['ignore', 'pipe', 'pipe']});
  let errorText = '';
  child.stderr.on('data', data => errorText += data);
  const done = new Promise((resolve, reject) => {
    child.on('error', reject);
    child.on('exit', code => resolve(code));
  });
  const command = value => fs.appendFileSync(path.join(out, 'commands.jsonl'), JSON.stringify(value) + '\n');
  for (let i = 0; !fs.existsSync(path.join(out, 'ready')); i++) {
    if (child.exitCode !== null) throw Error(errorText || '采集器未启动');
    if (i === 1500) {child.kill('SIGTERM'); throw Error('采集启动超时');}
    await pause(20);
  }
  await pause(1000); // 前留一秒；期间调用者不得操作界面。
  return {
    mark(description) { command({event: description}); },
    switchWindow(pid) {
      if (!pids.includes(pid)) throw Error('不能录制非自有窗口');
      command({pid});
    },
    async stop() {
      await pause(1000); // 后留一秒。
      command({stop:true});
      const code = await done;
      if (code !== 0) throw Error(errorText || '采集失败');
      // 只规范恒定帧率与像素格式，不裁剪、加字或绘制任何叠层。
      const encode = spawnSync('ffmpeg', ['-v','error','-i',path.join(out,'capture.mp4'),'-vf','fps=60','-c:v','libx264','-crf','16','-preset','medium','-pix_fmt','yuv420p','-an','-movflags','+faststart',path.join(out,'clip.mp4')], {encoding:'utf8'});
      if (encode.status !== 0) throw Error(encode.stderr);
      const probe = spawnSync('ffprobe', ['-v','error','-select_streams','v:0','-show_entries','stream=width,height,r_frame_rate,codec_name:format=duration','-of','json',path.join(out,'clip.mp4')], {encoding:'utf8'});
      if (probe.status !== 0) throw Error(probe.stderr);
      const media = JSON.parse(probe.stdout), video = media.streams[0];
      if (video.width !== 2560 || video.height !== 1440 || video.r_frame_rate !== '60/1' || video.codec_name !== 'h264') throw Error('输出规格不符');
      fs.writeFileSync(path.join(out,'probe.json'), JSON.stringify(media,null,2));
      return JSON.parse(fs.readFileSync(path.join(out,'events.json'),'utf8'));
    },
  };
}
module.exports = {startCapture};
