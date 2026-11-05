"""从原创 SVG 生成应用与视频共用图标；依赖 rsvg-convert、iconutil、Pillow。"""
from pathlib import Path
import subprocess,tempfile
from PIL import Image
root=Path(__file__).resolve().parents[1];brand=root/'assets/brand';build=root/'build';build.mkdir(exist_ok=True)
for n in (16,32,64,128,256,512,1024):
 subprocess.run(['rsvg-convert','-w',str(n),'-h',str(n),str(brand/'logo.svg'),'-o',str(brand/f'logo-{n}.png')],check=True)
with tempfile.TemporaryDirectory() as d:
 iconset=Path(d)/'gongke.iconset';iconset.mkdir()
 for n in (16,32,128,256,512):
  for scale in (1,2):
   (iconset/f'icon_{n}x{n}{"@2x" if scale==2 else ""}.png').write_bytes((brand/f'logo-{n*scale}.png').read_bytes())
 subprocess.run(['iconutil','-c','icns',str(iconset),'-o',str(build/'icon.icns')],check=True)
Image.open(brand/'logo-1024.png').save(build/'icon.ico',sizes=[(n,n) for n in (16,32,48,64,128,256)])
