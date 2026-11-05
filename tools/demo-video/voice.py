"""按已批准分镜逐镜生成中文神经配音，保留原始语音边界便于按动作剪辑。"""
import os
import asyncio
import json
from pathlib import Path
import re
import subprocess
import edge_tts

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT/os.environ.get('GONGKE_DEMO_VOICE','out/demo-video/voice')

async def main():
    OUT.mkdir(parents=True,exist_ok=True)
    rows=[]
    for line in (ROOT/'docs/demo-video/storyboard.md').read_text().splitlines():
        if not re.match(r'\| \d\d:',line):continue
        cells=[s.strip() for s in line.split('|')[1:-1]]
        index=len(rows)+1
        duration=float(re.search(r'/ (\d+)s',cells[0])[1])
        text=cells[2]
        target=OUT/f'{index:02}.mp3'
        subtitles=edge_tts.SubMaker()
        if not target.exists():
            with target.open('wb') as audio:
                async for chunk in edge_tts.Communicate(text,'zh-CN-XiaoxiaoNeural',rate='+0%',boundary='SentenceBoundary').stream():
                    if chunk['type']=='audio':audio.write(chunk['data'])
                    elif chunk['type']=='SentenceBoundary':subtitles.feed(chunk)
            target.with_suffix('.srt').write_text(subtitles.get_srt())
        actual=float(subprocess.check_output(['ffprobe','-v','quiet','-show_entries','format=duration','-of','csv=p=0',str(target)]))
        rows.append({'shot':index,'text':text,'planned_seconds':duration,'voice_seconds':actual,'audio':str(target.relative_to(ROOT))})
        print(index,round(actual,2),'/',duration,flush=True)
    (OUT/'segments.json').write_text(json.dumps(rows,ensure_ascii=False,indent=2))

if __name__=='__main__':asyncio.run(main())
