"""渲染明确标注的截图风格预览；不把它当连续录屏或 Agent 运行证据。"""
import argparse
import hashlib
import json
from pathlib import Path
import re
import subprocess

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[2]
FPS, DURATION = 30, 18


def font(size, weight=500):
    value = ImageFont.truetype(str(ROOT / 'desktop/src/assets/preview-font.ttf'), size)
    value.set_variation_by_axes([weight])
    return value


def seconds(value):
    h, m, s, ms = map(int, re.split('[:,]', value))
    return h * 3600 + m * 60 + s + ms / 1000


def stamp(value):
    ms = round(value * 1000)
    return f'{ms//3600000:02}:{ms//60000%60:02}:{ms//1000%60:02},{ms%1000:03}'


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--screenshots', type=Path, required=True)
    parser.add_argument('--output', type=Path, default=ROOT / 'out/demo-video')
    args = parser.parse_args()
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    sources = [args.screenshots / name for name in ['04-bounded-faces.png', '08-repaired.png']]
    # 均来自真实验收截图；裁剪只取模型与特征树，没有修饰任何结果或界面文字。
    pictures = []
    for p in sources:
        source = Image.open(p).convert('RGB')
        source = source.resize((2048, round(source.height * 2048/source.width)), Image.Resampling.LANCZOS)
        pictures.append(source.crop((335, 390, 1542, 1080)))
    rows = []
    for block in (output / 'check-voice.srt').read_text().strip().split('\n\n'):
        lines = block.splitlines()
        start, end = lines[1].split(' --> ')
        rows.append([seconds(start) + .65, seconds(end) + .65, ''.join(lines[2:])])
    # edge-tts 句边界可能重叠 50ms；以后一条的开始截断前一条，不叠字幕。
    for current, following in zip(rows, rows[1:]):
        current[1] = min(current[1], following[0])
    subtitles = []
    for start, end, text in rows:
        parts = text.split('，')
        if len(text) > 16 and len(parts) == 2:
            split = start + (end-start)*len(parts[0])/len(text)
            subtitles.extend([(start,split,parts[0]),(split,end,parts[1])])
        else:
            subtitles.append((start,end,text))
    (output / 'style-preview.srt').write_text('\n\n'.join(
        f'{i}\n{stamp(a)} --> {stamp(b)}\n{s}' for i,(a,b,s) in enumerate(subtitles,1))+'\n', encoding='utf-8')
    narration = ''.join(row[2] for row in rows)
    (output / 'narration.txt').write_text(narration+'\n', encoding='utf-8')
    # 改后截图切换必须跟着“修改之后”这一句，不提前显示。
    transition = rows[2][0]
    command = ['ffmpeg','-hide_banner','-loglevel','error','-y','-f','rawvideo',
        '-pix_fmt','rgb24','-s','1920x1080','-r',str(FPS),'-i','-',
        '-i',str(output/'check-voice.mp3'),'-filter_complex',
        '[1:a]adelay=650|650,apad,loudnorm=I=-16:TP=-1.5:LRA=7[a]',
        '-map','0:v','-map','[a]','-t',str(DURATION),'-c:v','libx264',
        '-preset','medium','-crf','18','-pix_fmt','yuv420p','-c:a','aac',
        '-b:a','192k','-movflags','+faststart',str(output/'style-preview.mp4')]
    process = subprocess.Popen(command, stdin=subprocess.PIPE)
    for frame in range(FPS*DURATION):
        t = frame/FPS
        canvas = Image.new('RGB',(1920,1080),(11,22,37))
        draw = ImageDraw.Draw(canvas)
        draw.line((72,109,1848,109),fill=(53,73,92),width=1)
        draw.text((72,45),'构想引擎',font=font(31,650),fill=(237,244,249))
        draw.text((1360,48),'真实界面截图 · 非录屏',font=font(27),fill=(173,193,210))
        if t < transition:
            heading=['模型建好','还要检查']
            caption='尺寸不符，定位到模型'
        else:
            heading=['保留特征','继续编辑']
            caption='修改之后，再次核对'
        draw.text((72,268),heading[0],font=font(61,650),fill=(244,248,252))
        draw.text((72,352),heading[1],font=font(61,650),fill=(99,214,202))
        draw.line((76,473,130,473),fill=(99,214,202),width=4)
        draw.text((75,516),caption,font=font(27),fill=(173,193,210))
        draw.text((75,854),'工具操作演示',font=font(24),fill=(140,163,183))
        # 缓入缓出裁剪变焦，只有摄影机变化，没有给截图补造模型动作。
        progress = min(1,max(0,(t-1)/5))
        eased = progress*progress*(3-2*progress)
        zoom = 1 + .11*eased
        source = pictures[0 if t < transition else 1]
        w,h = source.size
        cropw,croph = w/zoom,h/zoom
        crop = source.crop((w-cropw,0,w,croph))
        picture = crop.resize((1264,723),Image.Resampling.LANCZOS)
        mask = Image.new('L',picture.size,0)
        ImageDraw.Draw(mask).rounded_rectangle((0,0,1263,722),radius=20,fill=255)
        canvas.paste(picture,(584,195),mask)
        draw = ImageDraw.Draw(canvas)
        for start,end,text in subtitles:
            if start <= t < end:
                face = font(39,500)
                width = draw.textlength(text,font=face)
                draw.text(((1920-width)/2,1003),text,font=face,fill=(247,250,253))
        if frame in [45,180,330,495]:
            canvas.save(output/f'qa-{frame:03}.png')
        process.stdin.write(canvas.tobytes())
    process.stdin.close()
    if process.wait():
        raise RuntimeError('ffmpeg 编码失败')
    meta = {str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in sources}
    probe = json.loads(subprocess.check_output(['ffprobe','-v','error','-show_streams','-show_format',
        '-of','json',str(output/'style-preview.mp4')]))
    (output/'preview-manifest.json').write_text(json.dumps({
        'kind':'真实验收截图风格预览，非录屏，不是正式成片',
        'sources':meta,'voice':'zh-CN-XiaoxiaoNeural','rate':'-20%',
        'music':None,'fps':FPS,'duration':DURATION,'probe':probe},ensure_ascii=False,indent=2))


if __name__ == '__main__':
    main()
