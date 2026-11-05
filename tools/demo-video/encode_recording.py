"""将 CDP 连续录屏按实际时间戳编码；静止时保持上一帧，不改动播放速度。"""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def main():
    p=argparse.ArgumentParser()
    p.add_argument('directory',type=Path)
    p.add_argument('--output',type=Path)
    a=p.parse_args()
    root=a.directory.resolve()
    data=json.loads((root/'recording.json').read_text())
    frames=data['frames']
    if not frames:raise ValueError('录屏无帧')
    output=(a.output or root/'raw.mp4').resolve()
    lines=[]
    for i,f in enumerate(frames):
        filename=root/'frames'/f['file']
        next_time=frames[i+1]['timestamp'] if i+1<len(frames) else max(data['ended']/1000,f['timestamp']+1/30)
        # ffconcat 引号语法，禁止将路径作为 shell 代码执行。
        quoted=str(filename).replace("'", "'\\''")
        lines.extend([f"file '{quoted}'",f"duration {max(0.001,next_time-f['timestamp']):.6f}"])
    lines.append(lines[-2])
    listing=root/'frames.ffconcat'
    listing.write_text('\n'.join(lines)+'\n')
    subprocess.run(['ffmpeg','-hide_banner','-loglevel','error','-y','-f','concat','-safe','0','-i',str(listing),
                    '-vf','fps=30,scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2',
                    '-c:v','libx264','-preset','fast','-crf','19','-pix_fmt','yuv420p','-movflags','+faststart',str(output)],check=True)
    probe=json.loads(subprocess.check_output(['ffprobe','-v','quiet','-show_format','-show_streams','-of','json',str(output)]))
    (output.with_suffix('.provenance.json')).write_text(json.dumps({'source':str(root),'first_timestamp':frames[0]['timestamp'],
        'last_timestamp':frames[-1]['timestamp'],'frames':len(frames),'speed':1,
        'sha256':hashlib.file_digest(output.open('rb'),'sha256').hexdigest(),'probe':probe},ensure_ascii=False,indent=2))
    print(output)

if __name__=='__main__':main()
