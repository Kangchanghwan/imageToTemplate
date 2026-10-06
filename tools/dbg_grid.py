import sys, cv2, numpy as np
sys.path.insert(0, ".")
from sheetparser import preprocess as PP, grid as G
p = sys.argv[1]
img0 = cv2.imread(p)
print("input", img0.shape)
img, pg, flags = PP.rectify(img0)
print("rectify", img.shape, pg, flags)
if any(f["reason"].startswith(("no_paper", "paper_")) for f in flags):
    img, org, ok = PP.table_rectify(img, keep_frame=True); print("table_rectify", ok)
cv2.imwrite("/tmp/dbg_rect.png", img)
mask = PP.line_mask(img)
hb, vb = G.line_masks(mask, 10)
ppm = 10
print("mask ink px", (mask > 0).sum())
H, W = mask.shape
vp = vb.sum(0) / 255.0
xs = G._groups(vp, 25, 10)
print("raw vertical groups over full page:", [(a, b, int(vp[a:b+1].max())) for a, b in xs])
hp = hb.sum(1) / 255.0
print("raw horizontal groups full page:", [(a, b, int(hp[a:b+1].max())) for a, b in G._groups(hp, 25, 10)][:40])
k = 8
comb = cv2.dilate(hb | vb, np.ones((k, k), np.uint8))
n, lab, st, _ = cv2.connectedComponentsWithStats(comb, connectivity=8)
big = sorted([(int(st[i, 4]), [int(v) for v in st[i, :4]]) for i in range(1, n)], reverse=True)[:5]
print("components", big)
g = G.build_grid(mask, ppm)
print("xs", [round(x/10, 1) for x in g["xs"]])
print("ys n", len(g["ys"]))
print("extras", g["extras"])
