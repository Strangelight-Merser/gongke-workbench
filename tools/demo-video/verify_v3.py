"""检查 v3 仅改变开场图纸裁切，保存逐镜水印复核记录。"""
import hashlib,json
from pathlib import Path
ROOT=Path(__file__).resolve().parents[2]
a=ROOT/'out/demo-video/final-v2';b=ROOT/'out/demo-video/final-v3'
def sha(p):
 with p.open('rb') as f:return hashlib.file_digest(f,'sha256').hexdigest()
p=json.loads((a/'timeline.json').read_text());q=json.loads((b/'timeline.json').read_text())
assert p[1:]==q[1:]
opening=dict(q[0]['segments'][0]);crop=opening.pop('drawing_crop');opening.pop('crop_note')
assert opening==p[0]['segments'][0]
assert crop==[.10,.025,.45,.25]
for file in ['film.srt','narration.txt']:assert (a/file).read_bytes()==(b/file).read_bytes()
assert sha(a/'film.mp4')==json.loads((a/'validation.json').read_text())['film_sha256']
report={'ok':True,'only_change':'第1镜图纸裁切到主视图上部与尺寸区域，避开水印；不遮盖、不重绘','crop_normalized_ltrb':crop,'original_raster_pixels_ltrb':[240,42,1080,424],'other_shots_unchanged':True,'narration_and_srt_unchanged':True,'v2_untouched':True,'shot_review':[
 {'shot':1,'page_visible':True,'review':'12秒全段均使用同一无水印裁切，实际查看动画抽帧'},
 *[{'shot':i,'page_visible':False,'review':text} for i,text in [(2,'模型工作台，PDF仅为标签'),(3,'会话回放与模型，PDF标签未打开'),(4,'会话回放与模型，PDF标签未打开'),(5,'特征树和保存，未显示PDF页'),(6,'凸台检查示例，无图纸页'),(7,'参数修改与模型，无图纸页'),(8,'Agent接入与引导，无图纸页'),(9,'验收文字卡片，无图纸页'),(10,'模型收尾，PDF仅为标签')]]]}
(b/'revision-checks.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
print('v3 scope and source checks passed')
