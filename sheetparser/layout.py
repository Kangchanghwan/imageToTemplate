"""PageSpec(v2) 조립기. 표 격자(mm 경계) + 표 밖 텍스트 블록 + 이미지 -> 페이지 전체를 덮는 격자.

build_page_spec(page_mm, table, blocks, images, source) -> dict
  table : {"x_mm": [...], "y_mm": [...], "cells": [{"r","c","rs","cs", text/서식...}],
           "borders": {"h": [[..]], "v": [[..]]}}   (표 로컬 인덱스, R+1 x C / R x (C+1))
  blocks: [{"bbox_mm": [x0,y0,x1,y1], "text", "size_pt", "bold", "underline", "font", "h", ...}]
  images: [{"bbox_mm": [...], "png_b64"}]
table 이 None 이면 표 없는 페이지.
"""
import bisect

PX_MM = 96 / 25.4
MERGE_MM = 1.0   # 이보다 가까운 비-표 경계는 합친다


def _cluster(vals, fixed, tol=MERGE_MM):
    """fixed(표 선) 는 유지, 나머지는 fixed 에 tol 안이면 흡수, 서로 tol 안이면 첫 값으로 합침."""
    fixed = sorted(set(round(v, 3) for v in fixed))
    out = list(fixed)
    free = sorted(set(round(v, 3) for v in vals))
    last = None
    for v in free:
        if any(abs(v - f) < tol for f in fixed):
            continue
        if last is not None and v - last < tol:
            continue
        out.append(v)
        last = v
    return sorted(out)


def _idx(bounds, v):
    """v 에 가장 가까운 경계 인덱스."""
    i = bisect.bisect_left(bounds, v)
    cands = [j for j in (i - 1, i) if 0 <= j < len(bounds)]
    return min(cands, key=lambda j: abs(bounds[j] - v))


def _px(bounds_mm, total_px):
    cum = [int(round(b * PX_MM)) for b in bounds_mm]
    cum[0] = 0
    cum[-1] = total_px
    for i in range(1, len(cum)):  # 단조 증가 보장
        cum[i] = max(cum[i], cum[i - 1])
    return cum


SHEET_PT_SCALE = 0.975
LINE_FACTOR = 1.3     # 시트 글줄이 차지하는 높이 = 글자 크기(px) x 1.3 (이보다 행이 낮으면 윗부분이 잘린다)


def pad_blocks(blocks, table, page_mm):
    """표 밖 블록의 행 높이가 시트 글줄 높이보다 낮으면 위/아래 빈 공간으로 같은 만큼 넓힌다(가운데 유지).
    표 선, 다른 블록(가로로 겹치는 것)과 겹치지 않게 제한한다. 글자 위치는 세로 가운데 정렬이므로 변하지 않는다."""
    H = page_mm[1]
    tb = (table["x_mm"][0], table["y_mm"][0], table["x_mm"][-1], table["y_mm"][-1]) if table else None
    orig = [list(b["bbox_mm"]) for b in blocks]
    out = []
    for k, b in enumerate(blocks):
        x0, y0, x1, y1 = orig[k]
        sp = max(1, int(b.get("size_pt", 10) / SHEET_PT_SCALE + 0.5))
        need = sp * 96 / 72 * LINE_FACTOR / PX_MM
        h = y1 - y0
        # 가로: 병합된 칸은 넘친 글자를 자르므로 시트 글꼴(굵게일수록 넓음)이 더 넓어도 들어가게 정렬 방향으로 여유를 둔다
        w = x1 - x0
        ex = (0.14 if b.get("bold") else 0.07) * w + 1.0
        al = b.get("h", "LEFT")
        nx0 = x0 - (ex / 2 if al == "CENTER" else ex if al == "RIGHT" else 0)
        nx1 = x1 + (ex / 2 if al == "CENTER" else ex if al == "LEFT" else 0)
        W = page_mm[0]
        nx0, nx1 = max(nx0, 1.0), min(nx1, W - 1.0)
        for j, o in enumerate(orig):
            if j == k or o[3] <= y0 or o[1] >= y1:
                continue
            if o[0] >= x1 - 0.1:
                nx1 = min(nx1, o[0] - 0.3)
            elif o[2] <= x0 + 0.1:
                nx0 = max(nx0, o[2] + 0.3)
        nx0, nx1 = min(nx0, x0), max(nx1, x1)
        if h >= need:
            d = dict(b); d["bbox_mm"] = [nx0, y0, nx1, y1]
            out.append(d); continue
        lo, hi = 0.0, H
        if tb and x1 > tb[0] and x0 < tb[2]:
            if y1 <= tb[1] + 0.6:
                hi = tb[1] - 0.3
            elif y0 >= tb[3] - 0.6:
                lo = tb[3] + 0.3
        for j, o in enumerate(orig):
            if j == k or o[2] <= x0 or o[0] >= x1:
                continue
            oc, c = (o[1] + o[3]) / 2, (y0 + y1) / 2
            if oc < c:
                lo = max(lo, (o[3] + y0) / 2)
            else:
                hi = min(hi, (y1 + o[1]) / 2)
        g = (need - h) / 2
        a, bb = y0 - g, y1 + g
        if bb > hi:
            a -= bb - hi; bb = hi
        if a < lo:
            bb = min(hi, bb + lo - a); a = lo
        d = dict(b)
        d["bbox_mm"] = [nx0, max(a, lo), nx1, min(bb, hi)]
        out.append(d)
    return out


def build_page_spec(page_mm, table, blocks, images, source):
    W, H = page_mm
    blocks = pad_blocks(blocks, table, page_mm)
    fx, fy = [0.0, W], [0.0, H]
    freex, freey = [], []
    if table:
        fx += table["x_mm"]
        fy += table["y_mm"]
    for b in blocks:
        x0, y0, x1, y1 = b["bbox_mm"]
        freex += [x0, x1]
        freey += [y0, y1]
    xs = _cluster(freex, fx)
    ys = _cluster(freey, fy)
    # 1px 미만 간격 제거(표 선이 아닌 경계만)
    tfx = set(round(v, 3) for v in (table["x_mm"] if table else []))
    tfy = set(round(v, 3) for v in (table["y_mm"] if table else []))
    xs = [v for i, v in enumerate(xs) if i == 0 or i == len(xs) - 1 or v in tfx or v - xs[i - 1] >= 0.3]
    ys = [v for i, v in enumerate(ys) if i == 0 or i == len(ys) - 1 or v in tfy or v - ys[i - 1] >= 0.3]
    cpx = _px(xs, int(round(W * PX_MM)))
    rpx = _px(ys, int(W * 0 + H * PX_MM))
    C, R = len(xs) - 1, len(ys) - 1
    columns = [cpx[i + 1] - cpx[i] for i in range(C)]
    rows = [rpx[i + 1] - rpx[i] for i in range(R)]
    hB = [["NONE"] * C for _ in range(R + 1)]
    vB = [["NONE"] * (C + 1) for _ in range(R)]
    cells = []
    if table:
        tx = [_idx(xs, v) for v in table["x_mm"]]   # 표 열 경계 -> 페이지 열 경계 인덱스
        ty = [_idx(ys, v) for v in table["y_mm"]]
        for c in table["cells"]:
            r0, c0 = ty[c["r"]], tx[c["c"]]
            r1, c1 = ty[c["r"] + c.get("rs", 1)], tx[c["c"] + c.get("cs", 1)]
            d = dict(c)
            d.update({"r": r0, "c": c0, "rs": max(1, r1 - r0), "cs": max(1, c1 - c0), "role": "table"})
            cells.append(d)
        th, tv = table["borders"]["h"], table["borders"]["v"]
        for i in range(len(th)):
            for c in range(len(th[i])):
                st = th[i][c]
                if st == "NONE":
                    continue
                for pc in range(tx[c], tx[c + 1]):
                    hB[ty[i]][pc] = st
        for r in range(len(tv)):
            for j in range(len(tv[r])):
                st = tv[r][j]
                if st == "NONE":
                    continue
                for pr in range(ty[r], ty[r + 1]):
                    vB[pr][tx[j]] = st
    occupied = set()
    for c in cells:
        for rr in range(c["r"], c["r"] + c["rs"]):
            for cc in range(c["c"], c["c"] + c["cs"]):
                occupied.add((rr, cc))
    flags = []
    for b in blocks:
        x0, y0, x1, y1 = b["bbox_mm"]
        r0, r1 = _idx(ys, y0), _idx(ys, y1)
        c0, c1 = _idx(xs, x0), _idx(xs, x1)
        if r1 <= r0:
            r1 = r0 + 1
        if c1 <= c0:
            c1 = c0 + 1
        if any((rr, cc) in occupied for rr in range(r0, r1) for cc in range(c0, c1)):
            flags.append({"reason": "block_overlaps_table", "text": b.get("text", "")[:20]})
            continue
        for rr in range(r0, r1):
            for cc in range(c0, c1):
                occupied.add((rr, cc))
        d = {k: v for k, v in b.items() if k != "bbox_mm"}
        d.setdefault("h", "LEFT")
        d.setdefault("v", "MIDDLE")
        d.update({"r": r0, "c": c0, "rs": r1 - r0, "cs": c1 - c0, "wrap": False, "role": "text",
                  "src_bbox": [round(v, 2) for v in b["bbox_mm"]]})
        cells.append(d)
    imgs = []
    for im in images:
        x0, y0, x1, y1 = im["bbox_mm"]
        r = max(0, bisect.bisect_right(ys, y0) - 1)
        c = max(0, bisect.bisect_right(xs, x0) - 1)
        r, c = min(r, R - 1), min(c, C - 1)
        imgs.append({"r": r, "c": c, "dx_px": int(round((x0 - xs[c]) * PX_MM)), "dy_px": int(round((y0 - ys[r]) * PX_MM)),
                     "w_px": int(round((x1 - x0) * PX_MM)), "h_px": int(round((y1 - y0) * PX_MM)),
                     "png_b64": im["png_b64"], "bbox_mm": [round(v, 2) for v in im["bbox_mm"]]})
    return {"version": 2, "mode": "page", "source": source, "page_mm": [W, H],
            "columns": columns, "rows": rows, "cells": cells,
            "borders": {"h": hB, "v": vB}, "images": imgs, "flags": flags,
            "meta": {"x_mm": xs, "y_mm": ys}}
