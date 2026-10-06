import sys, cv2, numpy as np
sys.path.insert(0, ".")
from sheetparser import preprocess as PP, grid as G
for p in sys.argv[1:]:
    img0 = cv2.imread(p)
    img, pg, flags = PP.rectify(img0)
    if any(f["reason"].startswith(("no_paper", "paper_")) for f in flags):
        img, org, ok = PP.table_rectify(img, keep_frame=True)
    mask = PP.line_mask(img)
    g = G.build_grid(mask, 10)
    xs, ys = g["xs"], g["ys"]
    R, C = len(ys) - 1, len(xs) - 1
    print(p, "R", R, "C", C)
    print(" colw", [round((xs[i+1]-xs[i])/10,1) for i in range(C)])
    print(" rowh", [round((ys[i+1]-ys[i])/10,1) for i in range(R)])
    h, v = g["h"], g["v"]
    # 바깥 열: 위/아래 닫힘, 바깥 세로선 비율
    for name, c in (("left", 0), ("right", C-1)):
        top = h[0][c] is not None; bot = h[R][c] is not None
        edge = sum(1 for r in range(R) if v[r][0 if c == 0 else C] is not None) / R
        print("  col", name, "top", top, "bot", bot, "outer_v_frac", round(edge, 2))
    for name, r in (("top", 0), ("bottom", R-1)):
        l = v[r][0] is not None; rr = v[r][C] is not None
        edge = sum(1 for c in range(C) if h[0 if r == 0 else R][c] is not None) / C
        print("  row", name, "left", l, "right", rr, "outer_h_frac", round(edge, 2))
    g2, t = G.trim_outer(g)
    print("  trimmed", t)
