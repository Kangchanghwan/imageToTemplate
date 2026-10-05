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
BG_MIN_DROP = 18
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
        bx = st[ids]
        hs = bx[:, 3].astype(float)
        p90 = np.percentile(hs, 90)
        tall = (hs >= 0.6 * p90) & (hs <= 1.5 * p90)
        top = int(bx[tall, 1].min()); bot = int((bx[tall, 1] + bx[tall, 3]).max())
        core_h = float(np.percentile(hs[tall], 70))   # 괄호 등으로 부풀지 않게 글자 하나의 높이
        xa, xb = int(bx[:, 0].min()), int((bx[:, 0] + bx[:, 2]).max())
        ya, yb = int(bx[:, 1].min()), int((bx[:, 1] + bx[:, 3]).max())
        sub = np.isin(lab[ya:yb, xa:xb], ids).astype(np.uint8)
        cnts, _ = cv2.findContours(sub, cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
        per = sum(cv2.arcLength(c, True) for c in cnts)
        stroke = 2.0 * sub.sum() / per if per else 0
        ih = bot - top
        ul = any(t[2] >= 0.6 * (xb - xa) and t[0] >= xa - 3 * PPM and t[0] + t[2] <= xb + 3 * PPM
                 and 0 <= t[1] - bot <= 4 * PPM for t in thin)
        out.append({"bbox": (xa, ya, xb, yb), "ink_h": core_h, "bold": bool(ih and stroke / ih > 0.135), "underline": ul,
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
                if ov >= 0.6 * min(ay1 - ay0, by1 - by0) and gap <= 20 * PPM:
                    bb = (min(a["bbox"][0], b["bbox"][0]), min(ay0, by0), max(a["bbox"][2], b["bbox"][2]), max(ay1, by1))
                    big = a if (a["bbox"][3] - a["bbox"][1]) >= (b["bbox"][3] - b["bbox"][1]) else b
                    out[i] = {"bbox": bb, "ink_h": big["ink_h"], "bold": big["bold"], "underline": a["underline"] or b["underline"],
                              "stroke_ratio": big.get("stroke_ratio", 0.0)}
                    del out[j]; merged = True
                    break
            if merged:
                break
    out.sort(key=lambda b: (b["bbox"][1] // (3 * PPM), b["bbox"][0]))
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


def run_page(path, ocr=True, debug_dir=None, source_path=None, img0=None, kind="photo"):
    """kind="pdf_scan": 입력이 이미 10px/mm 로 정규화된 용지 이미지이므로 원근 보정을 생략한다."""
    t0 = time.time()
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
        rowmode = sparse and R > 8   # 빈 양식: 잉크 있는 행만 행 단위로 읽는다 (열/행 밀림 방지)
        if rowmode:
            chunks = []
            mat = [[""] * C for _ in range(R)]
            for r in range(R):
                rc = sorted([c for c in cells if c["r"] == r], key=lambda c: c["c"])
                if not any(not c["_empty"] for c in rc):
                    continue
                last = max(i for i, c in enumerate(rc) if not c["_empty"])
                sub = rc[:last + 1]   # 마지막 잉크 칸까지만 잘라 보낸다 (이미지가 작아 빠름)
                res = OCR.read_row(flat, (tb[0], grid["ys"][r], xs_mm[sub[-1]["c"] + sub[-1]["cs"]] * PPM, grid["ys"][r + 1]),
                                   [xs_mm[c["c"] + c["cs"]] - xs_mm[c["c"]] for c in sub])
                meta["calls"] += 1
                if res and len(res) == len(sub):
                    for c, t in zip(sub, res):
                        mat[r][c["c"]] = t
        else:
            mat = []
        for (a, b) in chunks:
            sub = None
            cb = (tb[0], grid["ys"][a], tb[2], grid["ys"][b])
            mm = [(r - a, c, rs, cs) for (r, c, rs, cs) in merges if a <= r < b]
            for _ in range(2):
                ink = [(c["r"] - a, c["c"]) for c in cells if a <= c["r"] < b and not c["_empty"]]
                sub = OCR.read_table(flat, cb, b - a, C, col_w, mm, 1 if a == 0 else 0, ink,
                                     (R, a + 1, b) if len(chunks) > 1 else None)
                meta["calls"] += 1
                if sub:
                    break
            if not sub:
                mat = None
                break
            mat += sub
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
            for r in trig[:14]:
                rc = rowcells(r)
                bb = (tb[0], grid["ys"][r], tb[2], grid["ys"][r + 1])
                res = OCR.read_row(flat, bb, [xs_mm[c["c"] + c["cs"]] - xs_mm[c["c"]] for c in rc])
                meta["calls"] += 1
                meta["row_requery"] = meta.get("row_requery", 0) + 1
                if res and len(res) == len(rc):
                    for c, t in zip(rc, res):
                        c["text"] = t.strip() if not c["_empty"] else ""
            sus = [c for c in cells if not c["_empty"] and not c["text"]]
            for c in sus[:12]:  # 잉크는 있는데 빈칸 -> 이웃 포함 크롭 재질의
                cols = [j for j in (c["c"] - 1, c["c"], c["c"] + 1) if 0 <= j < C]
                rects = [(xs_mm[j] * PPM, c["_rect"][1], xs_mm[j + 1] * PPM, c["_rect"][3]) for j in cols]
                t = OCR.read_neighbors(flat, rects, cols.index(c["c"]))
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
            c["_sz"] = ST.size_from_ink(c["_info"]["ink_h"], c["text"])
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
    # --- 표 밖 텍스트 ---
    blocks = []
    if True:
        t1 = time.time()
        for b in find_blocks(flat, fgray, tb):
            x0, y0, x1, y1 = b["bbox"]
            if (x1 - x0) < 8 * PPM or x0 > tb[2] + 15 * PPM or x1 < tb[0] - 15 * PPM:
                flags.append({"reason": "block_dropped_outside_paper_or_tiny", "bbox_mm": [round(v / PPM, 1) for v in b["bbox"]]})
                continue
            if ocr:
                t = OCR.read_line(flat, b["bbox"])
                meta["calls"] += 1
            else:
                t = "x"
            if not t or not any(ch.isalnum() for ch in t):
                flags.append({"reason": "block_dropped_unreadable", "bbox_mm": [round(v / PPM, 1) for v in b["bbox"]]})
                continue
            ty0, ty1 = tb[1] / PPM, tb[3] / PPM
            by0, by1 = y0 / PPM - 1.2, y1 / PPM + 1.2   # 글자 높이에 맞는 행 높이 확보(잘림 방지)
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
                           "size_pt": ST.size_from_ink(b["ink_h"], t), "bold": b["bold"], "underline": b["underline"],
                           "font": FONT, "italic": False, "color": "#000000", "h": hh, "v": "MIDDLE",
                           "_stroke": round(b.get("stroke_ratio", 0), 3)})
        meta["sec_blocks"] = round(time.time() - t1, 1)
    # 페이지 전체 크기 단계
    allsz = [c["size_pt"] for c in cells if c["text"]] + [b["size_pt"] for b in blocks]
    if allsz:
        mp = ST.unify_sizes([round(v * 2) / 2 for v in allsz])
        for c in cells:
            if c["text"]:
                c["size_pt"] = mp[round(c["size_pt"] * 2) / 2]
        for b in blocks:
            b["size_pt"] = mp[round(b["size_pt"] * 2) / 2]
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
        for k in ("_rect", "_info", "_empty", "_sz"):
            c.pop(k, None)
    table = {"x_mm": xs_mm, "y_mm": ys_mm, "cells": cells, "borders": borders}
    src = {"path": source_path or path, "kind": kind, "page": 0}
    spec = LAY.build_page_spec(pg_mm, table, blocks, [], src)
    spec["flags"] = list(spec.get("flags", [])) + flags + cflags
    for e in grid["extras"]:
        spec["flags"].append({"reason": "extra_table_ignored", "bbox": [int(a / PPM * 10) for a in e]})
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
