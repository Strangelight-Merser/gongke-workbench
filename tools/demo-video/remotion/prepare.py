"""从已授权的真实图纸、模型和录屏生成 Remotion 素材；学生资料只留 out。"""
import json,shutil,sys
from pathlib import Path
ROOT=Path(__file__).resolve().parents[3];sys.path.insert(0,str(ROOT))
from gongke_app.project import Project
from gongke_app.drawing_input import read_drawing
from gongke_app.drawing_check import extract_outline
out=ROOT/'out/demo-video/rebuild';assets=out/'assets';assets.mkdir(parents=True,exist_ok=True)
growth=out/sys.argv[1]
p=Project.open(growth/'project');d=read_drawing(p,'inputs/f00b1b9d-e9b/robot4.pdf',limit=500)
rows,box,scale,dimensions=extract_outline(d,'page-1/lines/74')
texts=[r for r in d['items'] if r['source'] in [x['item'] for x in dimensions]]
scene=json.loads((growth/'scene-06.json').read_text())
(assets/'geometry.json').write_text(json.dumps({'outline':rows,'box':box,'scale':scale,'dimensions':dimensions,'dimensionLines':[r for r in d['items'] if r['source'] in {key for dim in dimensions for key in [dim['dimension_line'],*dim['extension_lines']]}],'texts':texts,'mesh':scene['objects'][0],'sourceSha256':d['sha256']},ensure_ascii=False))
for weight in ['Regular','Bold']:shutil.copyfile(Path.home()/f'Library/Fonts/SourceHanSansSC-{weight}.otf',assets/f'SourceHanSansSC-{weight}.otf')
shutil.copyfile(ROOT/'desktop/assets/brand/logo.svg',assets/'logo.svg')
shutil.copyfile(growth/'stage-6.png',assets/'stage-6.png')
record=json.loads((growth/'recording.json').read_text());(assets/'recording.json').write_text(json.dumps(record))
# 保留实际连续时间；静止时保持原帧，不生成插值界面。
lines=[]
for i,f in enumerate(record['frames']):
 end=record['frames'][i+1]['timestamp'] if i+1<len(record['frames']) else record['ended']/1000
 name=str(growth/'frames'/f['file']).replace("'","'\\''")
 lines += [f"file '{name}'",f"duration {max(.001,end-f['timestamp']):.6f}"]
lines.append(lines[-2]);(growth/'frames.ffconcat').write_text('\n'.join(lines)+'\n')
print(json.dumps({'box':box,'dimensions':dimensions,'frames':len(record['frames'])}))
