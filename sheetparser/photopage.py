"""사진 -> PageSpec v2 (표 + 표 밖 텍스트 블록).
격자는 CV 로 고정, 글자는 보정 표 이미지 1회 호출 + 의심 칸만 이웃 포함 크롭으로 재질의."""
import os
import time
from collections import Counter

import cv2
import numpy as np

from . import grid as G, layout as LAY, ocr as OCR, preprocess as PP, style as ST

PPM = PP.PPM
THICK_BIAS_MM = 0.2
BG_MIN_DROP = 12
BG_MAX_GRAY = 245      # 평탄화 후 종이=255. 이보다 확실히 어두워야 bg
BG_MIN_UNIFORM = 0.65  # 칸 내부 균일도
FONT = "Nanum Gothic"


def _hex(bgr):
    b, g, r = [int(max(0, min(255, round(v)))) for v in bgr]
    return "#%02x%02x%02x" % (r, g, b)


def find_blocks(img, fgray, tb):
    """표 밖 잉크에서 텍스트 줄 bbox(px) 찾기. tb=(x0,y0,x1,y1) 표 외곽 px."""
    H, W = fgray.shape
    x0, y0, x1, y1 = [int(v) for v in tb]
    hsv = cv2.cvtColor(img, cv2.COLOR_BGR2HSV)
    paper = ((hsv[..., 2] > 120) & (hsv[..., 1] < 70)).astype(np.uint8)
    paper = cv2.morphologyEx(paper, cv2.MORPH_OPEN, np.ones((15, 15), np.uint8))
    n, lab = cv2.connectedComponents(paper)
    cnt = np.bincount(lab.ravel()); cnt[0] = 0
    if cnt.max() == 0:
        return []
    paper = (lab == cnt.argmax()).astype(np.uint8)
    cnts, _ = cv2.findContours(paper, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)  # 구멍(굵은 글자 등) 메움
    paper = np.zeros_like(paper)
    cv2.drawContours(paper, [max(cnts, key=cv2.contourArea)], -1, 1, -1)
    paper = cv2.erode(paper, np.ones((15, 15), np.uint8))
    sm = cv2.resize(fgray, (W // 4, H // 4), interpolation=cv2.INTER_AREA)
    bgm = cv2.resize(cv2.medianBlur(sm, 71), (W, H), interpolation=cv2.INTER_LINEAR)  # 약 28mm 창: 굵은 큰 글자도 배경으로 안 먹힘
    ink = (((bgm.astype(np.int16) - fgray) > 60) & (fgray < 200) & (paper > 0)).astype(np.uint8)
    m = int(1.5 * PPM)
    ink[max(y0 - m, 0):y1 + m, max(x0 - m, 0):x1 + m] = 0
    win = np.zeros_like(ink)
    win[:] = 1
    ink &= win
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    keep = np.zeros(n, bool)
    thin = []
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if h <= 6 and 8 * PPM <= w <= 120 * PPM and a >= 0.5 * w * h:
            thin.append((x, y, w, h))
        if a < 12 or h < 0.8 * PPM or h > 14 * PPM or w > 60 * PPM:
            continue
        if w > 40 * PPM and h < 2 * PPM:
            continue
        if h > 7.5 * PPM and w < 2.5 * PPM:  # 클립 철사 같은 가늘고 긴 세로 조각
            continue
        keep[i] = True
    km = keep[lab].astype(np.uint8)
    dil = cv2.dilate(km, np.ones((int(1.0 * PPM), int(14 * PPM)), np.uint8))
    n2, lab2 = cv2.connectedComponents(dil)
    out = []
    for k in range(1, n2):
        ids = np.unique(lab[(lab2 == k) & (km > 0)])
        ids = ids[ids > 0]
        if len(ids) < 2:
            continue
        if len(ids) >= 8:   # 도장/서명 같은 큰 덩어리에 휘둘리지 않게 윗/아랫 끝의 10/90 분위로 글줄 높이를 잰다
            ext = float(np.percentile(st[ids, 1] + st[ids, 3], 90) - np.percentile(st[ids, 1], 10))
        else:
            ext = float((st[ids, 1] + st[ids, 3]).max() - st[ids, 1].min())
        order = ids[np.argsort(st[ids, 0])]
        groups, cur, cmx = [], [order[0]], st[order[0], 0] + st[order[0], 2]
        for i_ in order[1:]:   # 가로로 글줄 높이의 1.25배 넘게 벌어진 곳은 따로 읽는다. 단 표 오른쪽 끝(14mm 안)까지 가는 마지막 조각만
            if st[i_, 0] - cmx > 1.25 * ext and not groups and st[i_, 0] > (x0 + x1) / 2 and \
                    (st[order, 0] + st[order, 2]).max() >= x1 - 14 * PPM:
                groups.append(cur); cur = []
            cur.append(i_); cmx = max(cmx, st[i_, 0] + st[i_, 2])
        groups.append(cur)
        for grp in groups:
            ids = np.array(grp)
            if len(ids) < 2:
                continue
            bx = st[ids]
            bx_all = bx
            if len(bx) >= 4:   # 도장/서명 같은 큰 덩어리(중앙값의 2.2배 초과)는 글자가 아니다
                okk = bx[:, 3] <= 2.2 * np.median(bx[:, 3])
                ids, bx = ids[okk], bx[okk]
                if len(ids) < 2:
                    continue
            hs = bx[:, 3].astype(float)
            p90 = np.percentile(hs, 90)
            tall = (hs >= 0.6 * p90) & (hs <= 1.5 * p90)
            top = int(bx[tall, 1].min()); bot = int((bx[tall, 1] + bx[tall, 3]).max())
            core_h = float(np.percentile(hs[tall], 70))   # 괄호 등으로 부풀지 않게 글자 하나의 높이
            xa, xb = int(bx_all[:, 0].min()), int((bx_all[:, 0] + bx_all[:, 2]).max())   # 읽기 범위는 도장 덩어리까지 포함 (가려진 글자도 읽어 본다)
            ya, yb = int(bx_all[:, 1].min()), int((bx_all[:, 1] + bx_all[:, 3]).max())
            sub = np.isin(lab[ya:yb, xa:xb], ids).astype(np.uint8)
            cnts, _ = cv2.findContours(sub, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
            per = sum(cv2.arcLength(c, True) for c in cnts)
            stroke = 2.0 * sub.sum() / per if per else 0
            ih = bot - top
            ul = any(t[2] >= 0.6 * (xb - xa) and t[0] >= xa - 3 * PPM and t[0] + t[2] <= xb + 3 * PPM
                     and 0 <= t[1] - bot <= 4 * PPM for t in thin)
            out.append({"bbox": (xa, ya, xb, yb), "ink_h": core_h, "ext_small": False, "line": k, "nc": len(bx), "bold": bool(ih and stroke / ih > 0.135), "underline": ul,
                        "stroke_ratio": float(stroke / ih) if ih else 0.0})
    merged = True
    while merged:
        merged = False
        for i in range(len(out)):
            for j in range(i + 1, len(out)):
                a, b = out[i], out[j]
                ay0, ay1, by0, by1 = a["bbox"][1], a["bbox"][3], b["bbox"][1], b["bbox"][3]
                ov = min(ay1, by1) - max(ay0, by0)
                gap = max(a["bbox"][0], b["bbox"][0]) - min(a["bbox"][2], b["bbox"][2])
                if ov >= 0.6 * min(ay1 - ay0, by1 - by0) and gap <= min(20 * PPM, 2.0 * min(a['ink_h'], b['ink_h']) / 0.88):
                    bb = (min(a["bbox"][0], b["bbox"][0]), min(ay0, by0), max(a["bbox"][2], b["bbox"][2]), max(ay1, by1))
                    big = a if (a["bbox"][3] - a["bbox"][1]) >= (b["bbox"][3] - b["bbox"][1]) else b
                    out[i] = {"bbox": bb, "ink_h": big["ink_h"], "ext_small": big.get("ext_small"), "line": big.get("line"), "nc": a.get("nc", 0) + b.get("nc", 0), "bold": big["bold"], "underline": a["underline"] or b["underline"],
                              "stroke_ratio": big.get("stroke_ratio", 0.0)}
                    del out[j]; merged = True
                    break
            if merged:
                break
    out.sort(key=lambda b: (b["bbox"][1] // (3 * PPM), b["bbox"][0]))
    return out


def _bands(blocks, my=30):
    """블록마다 세로 읽기 범위(px). 기본은 잉크 위아래 my px 여유인데, 가로로 겹치는 이웃 글줄의 잉크가 그 안에 들어오면
    (줄 간격이 좁거나 괄호 때문에 잉크 높이가 서로 겹치는 두 줄 칸) 이웃과의 중간선에서 자른다."""
    out = []
    for i, b in enumerate(blocks):
        x0, y0, x1, y1 = b["bbox"]
        lo, hi = y0 - my, y1 + my
        for j, o in enumerate(blocks):
            if i == j or o["bbox"][2] <= x0 or o["bbox"][0] >= x1:
                continue
            ox0, oy0, ox1, oy1 = o["bbox"]
            if (oy0 + oy1) / 2 < (y0 + y1) / 2:   # 위 이웃
                if oy1 > lo:
                    lo = max(lo, (oy1 + y0) / 2)
            else:
                if oy0 < hi:
                    hi = min(hi, (y1 + oy0) / 2)
        out.append((lo, hi))
    return out


def _extend_left(grid, mask):
    """표 왼쪽 선이 사진 밖으로 잘렸을 때: 첫 세로선 왼쪽 띠에 표 잉크가 있으면 0 에서 시작하는 열을 하나 더한다."""
    x0 = grid["xs"][0]
    ya, yb = int(grid["ys"][0]), int(grid["ys"][-1])
    if x0 < 8 * PPM or x0 > 60 * PPM:
        return grid
    strip = mask[ya:yb, int(1.5 * PPM):int(x0 - 1.5 * PPM)]
    if (strip > 0).sum() < 150:
        return grid
    if any(c == 0 and cs > 1 for (r, c, rs, cs) in grid["cells"]):
        return grid
    g = dict(grid)
    g["xs"] = [0.0] + list(grid["xs"])
    g["h"] = [[row[0]] + list(row) for row in grid["h"]]
    g["v"] = [[None] + list(row) for row in grid["v"]]
    g["cells"] = sorted([(r, c + 1, rs, cs) for (r, c, rs, cs) in grid["cells"]] +
                        [(r, 0, 1, 1) for r in range(len(grid["ys"]) - 1)
                         if not any(cr <= r < cr + crs and cc == 0 for (cr, cc, crs, ccs) in [])])
    g["ext_left"] = True
    return g


BOLD_THR = 0.08   # 한글 음절 획 두께 / 글자 크기(em) 가 이 이상이면 굵게 (실측: 보통 0.047~0.075, 굵게 0.093~0.11)
ALIGN_TOL_MM = 2.0


def _maj(vals):
    return bool(vals) and sum(vals) * 2 > len(vals)


def bold_pass(cells, HR, meta):
    """굵기: 한글 음절 덩어리의 획 두께를 글자 크기(em)로 나눠 쓴다. 숫자 칸은 글꼴이 달라 두께를 못 쓰므로 같은 행의 한글 칸 다수결.
    머리글 행은 행 단위(다수결), 본문 한글 칸은 칸마다(합계 행처럼 칸마다 다른 원본을 뭉개지 않는다).
    페이지 전체 분포에 보통/굵게 두 군집이 뚜렷이(간격 0.012 em 이상) 있으면 그 간격 가운데를 문턱으로 쓴다."""
    vals = {}
    for c in cells:
        if not c["text"]:
            continue
        h = c["_info"].get("hth")
        if h:
            vals[id(c)] = h[0] / (max(c["size_pt"], 1.0) * 25.4 / 72 * PPM)
    if not vals:
        return
    thr = BOLD_THR
    sv = sorted(vals.values())
    best = None
    for a, b in zip(sv, sv[1:]):
        if 0.06 <= (a + b) / 2 <= 0.105 and b - a >= 0.012 and (best is None or b - a > best[0]):
            best = (b - a, (a + b) / 2)
    if best:
        thr = best[1]
    meta["bold_thr"] = round(thr, 4)
    own = {id(c): (vals[id(c)] >= thr) for c in cells if id(c) in vals}
    hv = [own[id(c)] for c in cells if c["r"] < HR and id(c) in own]
    rowb = {}
    for c in cells:
        if id(c) in own:
            rowb.setdefault(c["r"], []).append(own[id(c)])
    for c in cells:
        if not c["text"]:
            continue
        if c["r"] < HR and hv:
            c["bold"] = _maj(hv)
        elif id(c) in own:
            c["bold"] = own[id(c)]
        else:
            c["bold"] = _maj(rowb.get(c["r"], []))


def align_pass(cells, HR):
    """가로 정렬. 기본은 좌우 여백 차이 2mm(칸 폭 5% 중 큰 값) 이내면 가운데.
    - 글줄이 2줄 이상이면 줄들의 왼쪽 끝이 1mm 안에서 같으면 왼쪽, 오른쪽 끝이 같으면 오른쪽 (자동 줄바꿈된 긴 글은 여백이 비슷해 가운데로 오판하기 쉽다).
    - 글이 칸을 80% 이상 채우는 긴 글(공백 뺀 21자 이상)은 왼쪽.
    - 여백 차이가 경계 근처(문턱의 1~2배)인 칸은 같은 열(본문)/행(머리글)에서 분명한 칸들의 다수결을 따른다(분명한 칸 3개 이상, 60% 이상)."""
    dec = {}
    for c in cells:
        i = c["_info"]
        if not c["text"] or "gl" not in i:
            continue
        cw = i["cw"] / PPM
        d = (i["gr"] - i["gl"]) / PPM
        tol = max(ALIGN_TOL_MM, 0.05 * cw)
        o = "CENTER" if abs(d) <= tol else ("LEFT" if d > 0 else "RIGHT")
        weak = tol < abs(d) < 2 * tol
        lb = i.get("lbx") or []
        if len(lb) >= 2:
            s0 = (max(a for a, b in lb) - min(a for a, b in lb)) / PPM
            s1 = (max(b for a, b in lb) - min(b for a, b in lb)) / PPM
            if s0 <= 1.0 and s1 > 1.0:
                o, weak = "LEFT", False
            elif s1 <= 1.0 and s0 > 1.0:
                o, weak = "RIGHT", False
        elif i["fill"] >= 0.8 and len("".join(c["text"].split())) > 20:
            o, weak = "LEFT", False
        dec[id(c)] = (o, weak)
    groups = {}
    for c in cells:
        if id(c) in dec:
            k = ("h", c["r"]) if c["r"] < HR else ("c", c["c"], c["cs"])
            groups.setdefault(k, []).append(c)
    for k, cs_ in groups.items():
        strong = [dec[id(c)][0] for c in cs_ if not dec[id(c)][1]]
        maj = None
        if len(strong) >= 3:
            top, n = Counter(strong).most_common(1)[0]
            if n >= 0.6 * len(strong):
                maj = top
        for c in cs_:
            o, weak = dec[id(c)]
            c["h"] = maj if (weak and maj) else o


def _cut(text, lines):
    """text(줄바꿈 없는 글)에서 줄 문자열 lines[:-1] 각각의 끝에 가장 가까운 자리(공백 제외 글자 수 기준)에 줄바꿈. 안 맞으면 None."""
    from .score import lev
    idx = [k for k, ch in enumerate(text) if not ch.isspace()]
    n = len(idx)
    a, cuts = 0, []
    for ln in lines[:-1]:
        L = "".join(ln.split())
        if not L:
            return None
        best = None
        for j in range(max(a + 1, a + len(L) - 3), min(n - 1, a + len(L) + 3) + 1):
            e = lev("".join(text[idx[k]] for k in range(a, j)), L)
            if best is None or e < best[0] or (e == best[0] and abs(j - a - len(L)) < abs(best[1] - a - len(L))):
                best = (e, j)
        if best is None or best[0] > max(2, 0.4 * len(L)):
            return None
        a = best[1]
        cuts.append(a)
    out, prev = [], 0
    for cj in cuts:
        out.append(text[prev:idx[cj]].strip()); prev = idx[cj]
    out.append(text[prev:].strip())
    return "\n".join(out)


def break_pass(flat, cells, meta):
    """칸 안 글줄 수(이미지의 글줄 띠)가 2 이상이면 줄마다 크롭을 paddle 로 읽어 칸 글자에서 줄바꿈 자리를 찾아 \n 을 넣는다.
    글자 자체는 칸 전체 읽기 결과를 그대로 쓴다(위치만 맞춘다). 폭 때문에 자동 줄바꿈된 줄도 원본 그대로 둔다."""
    from concurrent.futures import ThreadPoolExecutor
    H, W = flat.shape[:2]
    todo = []
    for c in cells:
        i = c["_info"]
        bands = i.get("lbands") or []
        if len(bands) >= 2 and len("".join(c["text"].split())) >= 4 and "\n" not in c["text"]:
            todo.append(c)

    def job(c):
        x0, y0, x1, y1 = [int(v) for v in c["_rect"]]
        bands = c["_info"]["lbands"]
        out = []
        for k in range(len(bands) - 1):
            lo = bands[k][0] - 6 if k == 0 else (bands[k - 1][1] + bands[k][0]) // 2
            hi = (bands[k][1] + bands[k + 1][0]) // 2
            crop = OCR._ink_tight(flat[max(lo, 0):min(hi + 1, H), max(x0 + 3, 0):min(x1 - 3, W)])
            try:
                out.append(OCR._paddle_one(crop, max_tokens=120)[0])
            except Exception:
                return None
        return out
    if not todo:
        return
    with ThreadPoolExecutor(4) as ex:
        res = list(ex.map(job, todo))
    meta["calls"] += sum(len(c["_info"]["lbands"]) - 1 for c in todo)
    nb = 0
    for c, lines in zip(todo, res):
        if not lines:
            meta["break_fail"] = meta.get("break_fail", 0) + 1
            continue
        t = _cut(c["text"], lines + ["x"])
        if t:
            c["text"] = t; nb += 1
    meta["breaks"] = nb


def _run_page(path, ocr=True, debug_dir=None, source_path=None, img0=None, kind="photo"):
    """kind="pdf_scan": 입력이 이미 10px/mm 로 정규화된 용지 이미지이므로 원근 보정을 생략한다."""
    t0 = time.time()
    OCR.stats_reset()
    if img0 is None:
        img0 = cv2.imread(path)
    if img0 is None:
        raise RuntimeError("cannot read " + str(path))
    if kind == "pdf_scan":
        img, pg_mm, flags = img0, [round(img0.shape[1] / PPM, 1), round(img0.shape[0] / PPM, 1)], [{"reason": "pdf_scan_no_perspective"}]
    else:
        img, pg_mm, flags = PP.rectify(img0)
    if kind != "pdf_scan" and any(f["reason"].startswith(("no_paper", "paper_")) for f in flags):
        img, org, ok = PP.table_rectify(img, keep_frame=True)
        flags.append({"reason": "table_quad_rectified" if ok else "table_quad_failed"})
        flags.append({"reason": "mm_scale_from_table_estimate"})
        pg_mm = [210, round(img.shape[0] / PPM, 1)]
    mask = PP.line_mask(img)
    try:
        grid = G.build_grid(mask, PPM)
    except RuntimeError as e:
        raise RuntimeError("grid_failed:%s" % e)
    grid, trimmed = G.trim_outer(grid)
    if any(trimmed.values()):
        flags.append({"reason": "outer_rows_cols_trimmed:" + ",".join("%s=%d" % kv for kv in trimmed.items() if kv[1])})
    grid = _extend_left(grid, mask)
    if grid.get("ext_left"):
        flags.append({"reason": "table_clipped_left_column_added"})
    xs_mm = [x / PPM for x in grid["xs"]]
    ys_mm = [y / PPM for y in grid["ys"]]
    R, C = len(ys_mm) - 1, len(xs_mm) - 1
    tb = (grid["xs"][0], grid["ys"][0], grid["xs"][-1], grid["ys"][-1])
    flat = PP.flatten(img, tb)
    fgray = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    sn = lambda i: ST.style_name(None if i is None else (max(i[0] - THICK_BIAS_MM, 0), i[1]))
    borders = {"h": [[sn(grid["h"][i][c]) for c in range(C)] for i in range(R + 1)],
               "v": [[sn(grid["v"][r][j]) for j in range(C + 1)] for r in range(R)]}
    cells, nbg = [], 0
    for (r, c, rs, cs) in grid["cells"]:
        rect = (xs_mm[c] * PPM, ys_mm[r] * PPM, xs_mm[c + cs] * PPM, ys_mm[r + rs] * PPM)
        info = ST.analyze(flat, fgray, rect)
        bg = None
        cells.append({"r": r, "c": c, "rs": rs, "cs": cs, "text": "", "h": info.get("h", "LEFT"),
                      "v": info.get("v", "MIDDLE"), "size_pt": 10, "bold": info.get("bold", False), "bg": bg,
                      "wrap": True, "font": FONT, "underline": False, "italic": False, "color": "#000000",
                      "src_bbox": [int(round(a)) for a in rect], "_rect": rect, "_info": info,
                      "_empty": info["empty"]})
    meds = [c["_info"]["med"] for c in cells if "med" in c["_info"]]
    pref = float(np.percentile(meds, 75)) if meds else 255.0   # 종이(흰 칸) 기준 밝기
    meta_bg = [(c["r"], c["c"], round(c["_info"]["med"]), round(c["_info"]["uni"], 2)) for c in cells
               if "med" in c["_info"] and pref - c["_info"]["med"] >= 6]
    for c in cells:
        i = c["_info"]
        if i.get("bgr") is not None and i.get("uni", 0) >= BG_MIN_UNIFORM and pref - i["med"] >= BG_MIN_DROP and i["med"] <= BG_MAX_GRAY:
            c["bg"] = _hex(i["bgr"]); nbg += 1
    meta = {"calls": 0, "bg_dbg": meta_bg, "bg_pref": round(pref)}
    cflags = []
    # --- 내용: 표 전체 1회 호출 ---
    if ocr:
        t1 = time.time()
        merges = [(c["r"], c["c"], c["rs"], c["cs"]) for c in cells if c["rs"] > 1 or c["cs"] > 1]
        col_w = [xs_mm[i + 1] - xs_mm[i] for i in range(C)]
        mat = None
        MAXSIDE = 1900  # 비전 인코더 메모리 보호: 긴 변이 이보다 크면 행 묶음으로 나눠 호출
        chunks = [(0, R)]
        sparse = sum(1 for c in cells if not c["_empty"]) < 0.25 * R * C
        if max(tb[3] - tb[1], tb[2] - tb[0]) > MAXSIDE or (sparse and R > 8):
            n = int(np.ceil((tb[3] - tb[1]) / MAXSIDE))
            if sparse:
                n = max(n, int(np.ceil(R / 6)))
            per = int(np.ceil(R / n))
            chunks, a = [], 0
            while a < R:
                b = min(R, a + per)
                # 병합 셀을 가르지 않게 경계 이동
                moved = True
                while moved and b < R:
                    moved = False
                    for (mr, mc, mrs, mcs) in merges:
                        if mr < b < mr + mrs:
                            b = mr + mrs; moved = True
                chunks.append((a, b)); a = b
        paddle = OCR.ACTIVE in ("paddle", "hybrid")
        if not paddle:   # 32B 호출 한도용: 칸마다 글줄 수 x 잉크 폭 -> 예상 출력 토큰
            Hf, Wf = flat.shape[:2]
            for c in cells:
                if not c["_empty"]:
                    x0_, y0_, x1_, y1_ = [int(v) for v in c["_rect"]]
                    c["_est"] = OCR.est_tokens(flat[max(y0_ + 3, 0):min(y1_ - 3, Hf), max(x0_ + 3, 0):min(x1_ - 3, Wf)])
        rowmode = sparse and R > 8 and not paddle   # 빈 양식: 잉크 있는 행만 행 단위로 읽는다 (열/행 밀림 방지)
        if paddle:
            chunks = []
            mat, pconf = OCR.paddle_cells(flat, cells, R, C)
            meta["calls"] += sum(1 for c in cells if not c["_empty"])
            if OCR.ACTIVE == "hybrid":
                mat = OCR.hybrid_fix(flat, cells, mat, pconf, xs_mm, C, meta)
        elif rowmode:
            chunks = []
            mat = [[""] * C for _ in range(R)]
            for r in range(R):
                rc = sorted([c for c in cells if c["r"] == r], key=lambda c: c["c"])
                if not any(not c["_empty"] for c in rc):
                    continue
                last = max(i for i, c in enumerate(rc) if not c["_empty"])
                sub = rc[:last + 1]   # 마지막 잉크 칸까지만 잘라 보낸다 (이미지가 작아 빠름)
                res = OCR.read_row(flat, (tb[0], grid["ys"][r], xs_mm[sub[-1]["c"] + sub[-1]["cs"]] * PPM, grid["ys"][r + 1]),
                                   [xs_mm[c["c"] + c["cs"]] - xs_mm[c["c"]] for c in sub],
                                   [i for i, c in enumerate(sub) if not c["_empty"]],
                                   [c["_est"] for c in sub if not c["_empty"]])
                meta["calls"] += 1
                if res and len(res) == len(sub):
                    for c, t in zip(sub, res):
                        mat[r][c["c"]] = t
        else:
            mat = []
        work = [(a, b, 1.0) for (a, b) in chunks]
        while work:
            a, b, mul = work.pop(0)
            sub = None
            cb = (tb[0], grid["ys"][a], tb[2], grid["ys"][b])
            mm = [(r - a, c, rs, cs) for (r, c, rs, cs) in merges if a <= r < b]
            ink = [(c["r"] - a, c["c"]) for c in cells if a <= c["r"] < b and not c["_empty"]]
            est = {(c["r"] - a, c["c"]): c["_est"] for c in cells if a <= c["r"] < b and not c["_empty"]}
            over = None
            for _ in range(2):
                try:
                    sub = OCR.read_table(flat, cb, b - a, C, col_w, mm, 1 if a == 0 else 0, ink,
                                         (R, a + 1, b) if len(chunks) > 1 or (a, b) != (0, R) else None, est, mul)
                except OCR.Overflow as e:   # 출력이 한도에서 잘렸거나 컨텍스트 초과 예상: 행을 나눠 다시 요청한다
                    over = e
                    break
                meta["calls"] += 1
                if sub:
                    break
            if over is not None:
                mid = (a + b) // 2
                while mid < b and any(mr < mid < mr + mrs for (mr, mc, mrs, mcs) in merges):
                    mid += 1
                if b - a > 1 and a < mid < b:
                    OCR.STATS["split"] += 1
                    work[:0] = [(a, mid, 1.0), (mid, b, 1.0)]
                    continue
                if over.kind == "truncated" and mul == 1.0:   # 더 못 나누는 한 행: 한도를 2배로 1회 재요청
                    OCR.STATS["retry"] += 1
                    work.insert(0, (a, b, 2.0))
                    continue
                sub = None
            if not sub:
                mat = None
                break
            mat += sub[0]   # 어긋난 행(sub[1])은 칸이 비어 있어 아래 행 재질의가 다시 읽는다
        meta["chunks"] = len(chunks)
        if mat is None:
            cflags.append({"reason": "table_ocr_failed"})
        else:
            sus = []
            for c in cells:
                t = mat[c["r"]][c["c"]].strip()
                if c["_empty"] and t:
                    t = ""; meta["ghost_dropped"] = meta.get("ghost_dropped", 0) + 1
                elif not c["_empty"] and not t:
                    sus.append(c)
                c["text"] = t
            # 행 단위 재질의: 머리글 행, 잉크 있는데 빈 칸, 문자 칸 중복(열 밀림 의심)
            def rowcells(r):
                return sorted([c for c in cells if c["r"] == r], key=lambda c: c["c"])
            trig = []
            for r in range(R):
                rc = rowcells(r)
                if not rc:
                    continue
                tx = [c["text"] for c in rc if c["text"] and not c["text"].replace(".", "").isdigit()]
                if any(not c["_empty"] and not c["text"] for c in rc) or len(tx) != len(set(tx)):
                    trig.append(r)
            for r in (trig[:14] if not paddle else []):
                rc = rowcells(r)
                bb = (tb[0], grid["ys"][r], tb[2], grid["ys"][r + 1])
                want = [i for i, c in enumerate(rc) if not c["_empty"]]
                if not want:
                    continue
                res = OCR.read_row(flat, bb, [xs_mm[c["c"] + c["cs"]] - xs_mm[c["c"]] for c in rc], want, [rc[i]["_est"] for i in want])
                meta["calls"] += 1
                meta["row_requery"] = meta.get("row_requery", 0) + 1
                if res and len(res) == len(rc):
                    for c, t in zip(rc, res):
                        c["text"] = t.strip() if not c["_empty"] else ""
            sus = [c for c in cells if not c["_empty"] and not c["text"]]
            for c in (sus[:12] if not paddle else []):  # 잉크는 있는데 빈칸 -> 이웃 포함 크롭 재질의
                cols = [j for j in (c["c"] - 1, c["c"], c["c"] + 1) if 0 <= j < C]
                rects = [(xs_mm[j] * PPM, c["_rect"][1], xs_mm[j + 1] * PPM, c["_rect"][3]) for j in cols]
                t = OCR.read_neighbors(flat, rects, cols.index(c["c"]), c.get("_est"))
                meta["calls"] += 1
                meta["requery"] = meta.get("requery", 0) + 1
                if t and t.strip():
                    c["text"] = t.strip()
                else:
                    cflags.append({"r": c["r"], "c": c["c"], "reason": "ink_but_empty_text"})
        meta["sec_table_ocr"] = round(time.time() - t1, 1)
    # --- 글자 크기: 글줄 높이 -> 열/행 최빈값 -> 페이지 단계 ---
    for c in cells:
        if c["text"] and c["_info"].get("ink_h"):
            c["_sz"] = ST.size_from_ink(c["_info"]["ink_h"], c["text"], nlines=c["_info"].get("nlines") if len(c["text"].strip()) >= 12 else None)   # 짧은 글자는 자모 사이 틈이 줄로 세어진다
    def mode(vals):
        q = [round(v * 2) / 2 for v in vals]
        cnt = Counter(q).most_common()
        top = [v for v, n in cnt if n == cnt[0][1]]
        return float(np.median(top)) if len(top) > 1 else top[0]
    HR = 1
    bycol, hdr = {}, []
    for c in cells:
        if "_sz" not in c:
            continue
        if c["r"] < HR:
            hdr.append(c["_sz"])
        elif c["cs"] == 1:
            bycol.setdefault(c["c"], []).append(c["_sz"])
    hdr_m = mode(hdr) if hdr else None
    col_m = {k: mode(v) for k, v in bycol.items()}
    allbody = [v for vs in bycol.values() for v in vs]
    body_m = mode(allbody) if allbody else None
    # 굵기: 머리글 행은 행 단위, 본문은 열 단위 다수결 (글자 있는 칸만, 열 단위 표본이 3개 미만이면 본문 전체)
    def maj(vals):
        return bool(vals) and sum(vals) * 2 > len(vals)
    hdr_b = maj([c["bold"] for c in cells if c["r"] < HR and c["text"]])
    col_b = {}
    for c in cells:
        if c["r"] >= HR and c["cs"] == 1 and c["text"]:
            col_b.setdefault(c["c"], []).append(c["bold"])
    body_b = maj([b for v in col_b.values() for b in v])
    col_b = {k: (maj(v) if len(v) >= 3 else body_b) for k, v in col_b.items()}
    meta["bold_dbg"] = {"hdr": hdr_b, "cols": {str(k): v for k, v in col_b.items()}}
    for c in cells:
        if not c["text"]:
            continue
        if c["r"] < HR:   # 머리글 행: 행 단위 최빈값 (측정 실패 칸도 같은 값)
            c["size_pt"] = hdr_m if hdr_m else c["size_pt"]
            c["bold"] = hdr_b
        elif c["cs"] == 1:   # 본문: 열 단위 최빈값. 측정 실패(잉크가 테두리에 닿음 등)한 칸도 열 값을 따른다
            c["size_pt"] = col_m.get(c["c"], body_m if body_m else c["size_pt"])
            c["bold"] = col_b.get(c["c"], body_b)
        elif "_sz" in c:
            c["size_pt"] = round(c["_sz"] * 2) / 2
    if ocr:
        break_pass(flat, cells, meta)
    # --- 표 밖 텍스트 ---
    blocks = []
    if True:
        t1 = time.time()
        fb = find_blocks(flat, fgray, tb)
        bands = _bands(fb)
        for b, band in zip(fb, bands):
            x0, y0, x1, y1 = b["bbox"]
            if (x1 - x0) < 8 * PPM or x0 > tb[2] + 15 * PPM or x1 < tb[0] - 15 * PPM:
                flags.append({"reason": "block_dropped_outside_paper_or_tiny", "bbox_mm": [round(v / PPM, 1) for v in b["bbox"]]})
                continue
            if ocr:
                t = OCR.read_line_paddle(flat, b["bbox"], band) if OCR.ACTIVE in ("paddle", "hybrid") else \
                    OCR.read_line(flat, b["bbox"], band, OCR.est_tokens(flat[max(int(band[0]), 0):int(band[1]), max(int(x0) - 5, 0):int(x1) + 5]))
                meta["calls"] += 1
            else:
                t = "x"
            if not t or not any(ch.isalnum() for ch in t):
                flags.append({"reason": "block_dropped_unreadable", "bbox_mm": [round(v / PPM, 1) for v in b["bbox"]]})
                continue
            ty0, ty1 = tb[1] / PPM, tb[3] / PPM
            by0, by1 = y0 / PPM - 1.2, y1 / PPM + 1.2   # 글자 높이에 맞는 행 높이 확보(잘림 방지)
            by0, by1 = max(by0, band[0] / PPM), min(by1, band[1] / PPM)   # 이웃 글줄과 겹치면 중간선에서 자른다(안 그러면 layout 이 겹친 블록을 버린다)
            if by1 > ty0 - 0.3 and y1 / PPM <= ty0 + 1:
                by1 = ty0 - 0.3
            if by0 < ty1 + 0.3 and y0 / PPM >= ty1 - 1:
                by0 = ty1 + 0.3
            bx1 = min(x1 / PPM + 0.12 * (x1 - x0) / PPM, pg_mm[0] - 1.0)   # 시트 글꼴이 더 넓어도 안 잘리게 오른쪽 여유
            bb = [x0 / PPM, by0, max(bx1, x1 / PPM), by1]
            hh = "LEFT"
            tx0, tx1 = tb[0] / PPM, tb[2] / PPM
            if abs((x0 + x1) / 2 / PPM - (tx0 + tx1) / 2) < 0.06 * (tx1 - tx0) and x0 / PPM > tx0 - 3 and x1 / PPM < tx1 + 3:
                bb[0], bb[2], hh = tx0, tx1, "CENTER"   # 표 가운데 제목: 표 전체 폭으로 병합 + 가운데 정렬 (넘침/잘림 방지)
            blocks.append({"bbox_mm": bb, "text": t.strip(),
                           "size_pt": ST.size_from_ink(b["ink_h"] * (0.88 if b.get("ext_small") and ("(" in t or ")" in t) else 1.0), t), "bold": b["bold"], "underline": b["underline"],
                           "font": FONT, "italic": False, "color": "#000000", "h": hh, "v": "MIDDLE",
                           "_stroke": round(b.get("stroke_ratio", 0), 3), "_line": b.get("line"), "_nc": b.get("nc", 0)})
        meta["sec_blocks"] = round(time.time() - t1, 1)
    # 같은 글줄에서 갈라진 조각(작성자 ... / (서명))은 글자 수가 가장 많은(가장 믿을 만한) 조각의 크기를 같이 쓴다. 서명 도장에 가린 조각은 높이가 부풀거나 줄어든다.
    byl = {}
    for b in blocks:
        if b.get("_line") is not None:
            byl.setdefault(b["_line"], []).append(b)
    for grp in byl.values():
        if len(grp) >= 2:
            ref = max(grp, key=lambda b: b["_nc"])
            for b in grp:
                b["size_pt"] = ref["size_pt"]
            grp.sort(key=lambda b: b["bbox_mm"][0])
            last = grp[-1]
            tx0, tx1 = tb[0] / PPM, tb[2] / PPM
            if last["h"] == "LEFT" and last["bbox_mm"][0] > (tx0 + tx1) / 2 and last["bbox_mm"][2] >= tx1 - 14:
                last["h"] = "RIGHT"   # 표 오른쪽 끝에 붙은 마지막 조각
    # 페이지 전체 크기 단계 (표 칸 글자와 표 밖 글줄은 따로 묶는다: 11.0 과 10.5 처럼 가까운 두 단계를 한 단계로 뭉개지 않게)
    for grp, key in (([c for c in cells if c["text"]], "c"), (blocks, "b")):
        if grp:
            mp = ST.unify_sizes([round(g["size_pt"] * 2) / 2 for g in grp])
            for g in grp:
                g["size_pt"] = mp[round(g["size_pt"] * 2) / 2]
    bold_pass([c for c in cells if c["text"]], HR, meta)
    align_pass([c for c in cells if c["text"]], HR)
    # 제목: 표 가운데에 놓인 본문보다 확연히 큰 글줄은 굵게 (큰 글자는 잉크 두께 비율이 낮게 측정되어 굵기 판정이 늘 보통으로 나온다)
    bsz = [c["size_pt"] for c in cells if c["r"] >= HR and c["text"] and c["cs"] == 1]
    if bsz:
        bm = float(np.median(bsz))
        for b in blocks:
            if b["h"] == "CENTER" and b["size_pt"] >= 1.2 * bm and b["_stroke"] >= 0.08:
                b["bold"] = True
    # 열별 글자 크기 분산(본문)
    cs_ = {}
    for c in cells:
        if c["r"] >= HR and c["cs"] == 1 and c["text"]:
            cs_.setdefault(c["c"], []).append(c["size_pt"])
    meta["tb"] = [int(v) for v in tb]
    meta["col_size_std"] = {str(k): round(float(np.std(v)), 2) for k, v in cs_.items()}
    meta["bg_cells"] = nbg
    meta["stroke_dbg"] = [[c["r"], c["c"], round(c["_info"].get("stroke_ratio", 0), 3)] for c in cells if c["text"] and "_info" in c]
    for c in cells:
        for k in ("_rect", "_info", "_empty", "_sz", "_est"):
            c.pop(k, None)
    table = {"x_mm": xs_mm, "y_mm": ys_mm, "cells": cells, "borders": borders}
    src = {"path": source_path or path, "kind": kind, "page": 0}
    spec = LAY.build_page_spec(pg_mm, table, blocks, [], src)
    spec["flags"] = list(spec.get("flags", [])) + flags + cflags
    for e in grid["extras"]:
        spec["flags"].append({"reason": "extra_table_ignored", "bbox": [int(a / PPM * 10) for a in e]})
    meta["vlm"] = {k: (round(v, 1) if isinstance(v, float) else v) for k, v in OCR.STATS.items()}
    meta["trunc"] = {"paddle": {k: OCR.PADDLE_STATS[k] for k in ("trunc", "retry_ok", "to32", "max_prompt", "max_out")},
                     "qwen32b": {k: OCR.STATS[k] for k in ("trunc", "retry", "split", "trunc_final")}}
    meta["call_log"] = list(OCR.CALL_LOG)
    spec["meta"].update(meta)
    spec["meta"]["sec_total"] = round(time.time() - t0, 2)
    spec["meta"]["blocks"] = [{"text": b["text"], "bbox_mm": [round(v, 1) for v in b["bbox_mm"]], "size_pt": b["size_pt"]} for b in blocks]
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
        name = os.path.splitext(os.path.basename(path))[0]
        out = img.copy()
        for c in cells:
            if c.get("bg"):
                x0, y0, x1, y1 = c["src_bbox"]
                cv2.rectangle(out, (x0, y0), (x1, y1), (255, 120, 0), 6)
        for (r, c, rs, cs) in grid["cells"]:
            cv2.rectangle(out, (int(xs_mm[c] * PPM), int(ys_mm[r] * PPM)), (int(xs_mm[c + cs] * PPM), int(ys_mm[r + rs] * PPM)), (0, 0, 255), 2)
        for b in blocks:
            x0, y0, x1, y1 = [int(v * PPM) for v in b["bbox_mm"]]
            cv2.rectangle(out, (x0, y0), (x1, y1), (0, 160, 0), 3)
        cv2.imwrite(os.path.join(debug_dir, name + "_overlay.png"), out)
        cv2.imwrite(os.path.join(debug_dir, name + "_flat.jpg"), flat, [cv2.IMWRITE_JPEG_QUALITY, 90])
        rp = os.path.join(debug_dir, name + "_rectified.jpg")
        cv2.imwrite(rp, img, [cv2.IMWRITE_JPEG_QUALITY, 90])
        spec["meta"]["rectified"] = rp
    return spec


def run_page(path, ocr=True, debug_dir=None, source_path=None, img0=None, kind="photo"):
    """OCR 백엔드 진입점. auto 면 사진(kind=photo)은 paddle, 스캔 PDF(pdf_scan)는 32B.
    paddle 결과에 이상(요청 실패, 잉크 있는 칸이 빈 글자, 80자 초과 칸, 예외)이 있으면 그 장은 32B 로 다시 읽는다."""
    kw = dict(path=path, ocr=ocr, debug_dir=debug_dir, source_path=source_path, img0=img0, kind=kind)
    if OCR.BACKEND != "auto":
        OCR.ACTIVE = OCR.BACKEND
        sp = _run_page(**kw)
        sp["meta"]["ocr_backend"] = OCR.ACTIVE
        return sp
    if kind != "photo" or not ocr:
        OCR.ACTIVE = "qwen32b"
        sp = _run_page(**kw)
        sp["meta"]["ocr_backend"] = "qwen32b"
        return sp
    OCR.ACTIVE = "paddle"
    OCR.paddle_reset()
    reason = None
    try:
        sp = _run_page(**kw)
        st = OCR.PADDLE_STATS
        if st["fail"] or st["empty"] or st["long"]:
            reason = "paddle fail=%d empty=%d long=%d" % (st["fail"], st["empty"], st["long"])
        elif any(f.get("reason") == "table_ocr_failed" for f in sp.get("flags", [])):
            reason = "table_ocr_failed"
    except Exception as e:
        reason = "paddle exception: %s" % e
    if reason is None:
        sp["meta"]["ocr_backend"] = "paddle"
        return sp
    OCR.ACTIVE = "qwen32b"
    sp = _run_page(**kw)
    sp["meta"]["ocr_backend"] = "qwen32b"
    sp["meta"]["auto_fallback"] = reason
    return sp
