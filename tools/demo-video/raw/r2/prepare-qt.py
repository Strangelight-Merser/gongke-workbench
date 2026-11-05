"""创建录屏专用 FreeCAD 配置；不读写用户配置。"""
import argparse
from pathlib import Path
import re

parser = argparse.ArgumentParser()
parser.add_argument('work', type=Path)
args = parser.parse_args()
args.work.mkdir(parents=True, exist_ok=True)
(args.work / 'apphome').mkdir(exist_ok=True)
pack = Path('/Applications/FreeCAD.app/Contents/Resources/share/Gui/PreferencePacks/FreeCAD Dark/FreeCAD Dark.cfg')
text = pack.read_text()
for key in ('SelectionColor', 'HighlightColor'):
    text, count = re.subn(r'(<FCUInt Name="' + key + r'" Value=")[^"]+', lambda m: m[1] + str(0xE8742AFF), text)
    if count == 0:
        raise ValueError(f'{key}: missing preference, got {count}')
(args.work / 'user.cfg').write_text(text)
print(f'FREECAD_USER_HOME={args.work.resolve() / "apphome"}')
print(f'--user-cfg {args.work.resolve() / "user.cfg"}')
