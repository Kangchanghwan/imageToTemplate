"""나란히 PNG 에서 같은 영역을 좌/우로 잘라 한 장으로 (긴 변 1800px 이하). 사용: crop_side.py side.png out.png x0 y0 x1 y1 [half_width]"""
import sys
from PIL import Image
src, out = sys.argv[1], sys.argv[2]
x0, y0, x1, y1 = map(int, sys.argv[3:7])
a = Image.open(src)
hw = int(sys.argv[7]) if len(sys.argv) > 7 else a.width // 2
l, r = a.crop((x0, y0, x1, y1)), a.crop((x0 + hw, y0, x1 + hw, y1))
w = Image.new("RGB", (l.width * 2 + 6, l.height), (255, 0, 0)); w.paste(l, (0, 0)); w.paste(r, (l.width + 6, 0))
s = min(1.0, 1800 / w.width); w.resize((int(w.width * s), int(w.height * s))).save(out)
