"""PageSpec -> 시트 모양 근사 렌더(PIL, 맥). Sheets 생성 한도로 실제 시트 PDF 를 못 받을 때 서식(정렬/굵기/줄바꿈) 확인용.
사용: render_spec.py <spec.json> <원본.png> <out.png> [위쪽 비율]"""
import json, sys
from PIL import Image, ImageDraw, ImageFont
spec = json.load(open(sys.argv[1])); src = Image.open(sys.argv[2]).convert("RGB"); out = sys.argv[3]
frac = float(sys.argv[4]) if len(sys.argv) > 4 else 0.4
FP = "/System/Library/Fonts/AppleSDGothicNeo.ttc"
def font(sz, bold):
    f = ImageFont.truetype(FP, max(6, int(round(sz))))
    try: f.set_variation_by_name("Bold" if bold else "Regular")
    except Exception:
        try: f = ImageFont.truetype(FP, max(6, int(round(sz))), index=(6 if bold else 0))
        except Exception: pass
    return f
cols, rows = spec["columns"], spec["rows"]
xs = [0]; [xs.append(xs[-1] + w) for w in cols]
ys = [0]; [ys.append(ys[-1] + h) for h in rows]
W, H = xs[-1], ys[-1]
im = Image.new("RGB", (W, H), "white"); d = ImageDraw.Draw(im)
def wrap(txt, f, maxw):
    lines = []
    for ln in txt.split("\n"):
        cur = ""
        for ch in ln:
            if d.textlength(cur + ch, font=f) > maxw and cur:
                lines.append(cur); cur = ch
            else: cur += ch
        lines.append(cur)
    return lines
for c in spec["cells"]:
    x0, x1 = xs[c["c"]], xs[c["c"] + c["cs"]]; y0, y1 = ys[c["r"]], ys[c["r"] + c["rs"]]
    if c.get("bg"): d.rectangle([x0, y0, x1, y1], fill=c["bg"])
    t = c.get("text", "")
    if not t: continue
    px = c.get("size_pt", 10) / 0.975 * 96 / 72 * 0.975
    f = font(px, c.get("bold"))
    lines = wrap(t, f, x1 - x0 - 4) if c.get("role", "table") == "table" else t.split("\n")
    lh = px * 1.25; th = lh * len(lines); ty = y0 + (y1 - y0 - th) / 2
    for ln in lines:
        w = d.textlength(ln, font=f)
        tx = x0 + 3 if c["h"] == "LEFT" else (x1 - 3 - w if c["h"] == "RIGHT" else x0 + (x1 - x0 - w) / 2)
        d.text((tx, ty), ln, font=f, fill="black"); ty += lh
bw = {"NONE": 0, "SOLID": 1, "SOLID_MEDIUM": 2, "SOLID_THICK": 3, "DOUBLE": 3}
for i, row in enumerate(spec["borders"]["h"]):
    for cidx, st in enumerate(row):
        if bw[st]: d.line([xs[cidx], ys[i], xs[cidx + 1], ys[i]], fill="black", width=bw[st])
for r, row in enumerate(spec["borders"]["v"]):
    for j, st in enumerate(row):
        if bw[st]: d.line([xs[j], ys[r], xs[j], ys[r + 1]], fill="black", width=bw[st])
s = W / src.width; srs = src.resize((W, int(src.height * s)))
cut = int(H * frac)
a = srs.crop((0, 0, W, cut)); b = im.crop((0, 0, W, cut))
side = Image.new("RGB", (W * 2 + 20, cut), "#888"); side.paste(a, (0, 0)); side.paste(b, (W + 20, 0))
side.save(out); print(side.size)
