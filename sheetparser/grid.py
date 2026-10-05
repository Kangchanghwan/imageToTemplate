"""선 마스크 -> 전역 격자 -> 경계 유무/두께 -> 병합. 래스터/벡터 공용 (마스크 해상도 ppm = px/mm)."""
import cv2
import numpy as np


def line_masks(mask, ppm):
    L = max(5, int(3.0 * ppm))
    hk = cv2.getStructuringElement(cv2.MORPH_RECT, (L, 1))
    vk = cv2.getStructuringElement(cv2.MORPH_RECT, (1, L))
    return cv2.morphologyEx(mask, cv2.MORPH_OPEN, hk), cv2.morphologyEx(mask, cv2.MORPH_OPEN, vk)


def _groups(proj, thr, gap):
    idx = np.nonzero(proj >= thr)[0]
    if len(idx) == 0:
        return []
    out, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            out.append((int(s), int(p)))
            s = i
        p = i
    out.append((int(s), int(p)))
    return out


def _seg_stats(hb, lines, edges, ppm):
    """hb: (H,W) 선 마스크, lines: [(lo,hi)] axis0 위치, edges: axis1 경계 중심 목록.
    반환 res[k][j] = None | (두께mm, 이중선)"""
    H = hb.shape[0]
    res = []
    for lo, hi in lines:
        a, b = max(0, lo - 2), min(H, hi + 3)
        band = hb[a:b] > 0
        row = []
        for j in range(len(edges) - 1):
            x0, x1 = edges[j], edges[j + 1]
            m = 0.1 * (x1 - x0)
            xa, xb = int(round(x0 + m)), int(round(x1 - m))
            if xb <= xa + 1:
                xa, xb = int(x0), int(x1)
            xa = max(xa, 0)
            seg = band[:, xa:xb]
            if seg.shape[1] == 0:
                row.append(None)
                continue
            hit = seg.any(0)
            if hit.mean() < 0.5:
                row.append(None)
                continue
            prof = seg[:, hit].sum(1) / hit.sum()
            thick = float(prof.sum()) / ppm
            pk = prof.max()
            on = prof > 0.5 * pk
            runs = int(np.sum(on[1:] & ~on[:-1]) + (1 if on[0] else 0))
            row.append((thick, runs >= 2))
        res.append(row)
    return res


def build_grid(mask, ppm, min_len_mm=2.5):
    H, W = mask.shape
    hb, vb = line_masks(mask, ppm)
    k = max(3, int(0.8 * ppm))
    comb = cv2.dilate(hb | vb, np.ones((k, k), np.uint8))
    n, lab, stats, _ = cv2.connectedComponentsWithStats(comb, connectivity=8)
    if n < 2:
        raise RuntimeError("no_lines")
    areas = stats[1:, cv2.CC_STAT_AREA]
    main = 1 + int(np.argmax(areas))
    x, y, w, h = [int(stats[main, i]) for i in range(4)]
    extras = []
    for i in range(1, n):
        if i != main and stats[i, 2] * stats[i, 3] > 0.03 * H * W:
            extras.append([int(stats[i, j]) for j in range(4)])
    sel = (lab[y:y + h, x:x + w] == main)
    hbc = hb[y:y + h, x:x + w] * sel
    vbc = vb[y:y + h, x:x + w] * sel
    thr = min_len_mm * ppm
    gap = max(2, int(1.0 * ppm))
    ylines = _groups(hbc.sum(1) / 255.0, thr, gap)
    xlines = _groups(vbc.sum(0) / 255.0, thr, gap)
    if len(ylines) < 2 or len(xlines) < 2:
        raise RuntimeError("no_grid")

    for _ in range(4):
        ycen = [(a + b) / 2 for a, b in ylines]
        xcen = [(a + b) / 2 for a, b in xlines]
        Hs = _seg_stats(hbc, ylines, xcen, ppm)            # [i][c]
        Vs = _seg_stats(vbc.T, xlines, ycen, ppm)          # [j][r]
        ykeep = [i for i, row in enumerate(Hs) if any(v is not None for v in row)]
        xkeep = [j for j, row in enumerate(Vs) if any(v is not None for v in row)]
        if len(ykeep) == len(ylines) and len(xkeep) == len(xlines):
            break
        ylines = [ylines[i] for i in ykeep]
        xlines = [xlines[j] for j in xkeep]
        if len(ylines) < 2 or len(xlines) < 2:
            raise RuntimeError("no_grid")
    R, C = len(ylines) - 1, len(xlines) - 1
    hs = Hs
    vs = [[Vs[j][r] for j in range(C + 1)] for r in range(R)]

    # union-find 병합
    par = list(range(R * C))

    def f(a):
        while par[a] != a:
            par[a] = par[par[a]]
            a = par[a]
        return a

    def u(a, b):
        a, b = f(a), f(b)
        if a != b:
            par[b] = a
    for r in range(R):
        for c in range(C):
            if c + 1 < C and vs[r][c + 1] is None:
                u(r * C + c, r * C + c + 1)
            if r + 1 < R and hs[r + 1][c] is None:
                u(r * C + c, (r + 1) * C + c)
    changed = True
    while changed:
        changed = False
        comp = {}
        for r in range(R):
            for c in range(C):
                comp.setdefault(f(r * C + c), []).append((r, c))
        for cells in comp.values():
            r0 = min(p[0] for p in cells); r1 = max(p[0] for p in cells)
            c0 = min(p[1] for p in cells); c1 = max(p[1] for p in cells)
            if (r1 - r0 + 1) * (c1 - c0 + 1) != len(cells):
                for rr in range(r0, r1 + 1):
                    for cc in range(c0, c1 + 1):
                        u(r0 * C + c0, rr * C + cc)
                changed = True
    comp = {}
    for r in range(R):
        for c in range(C):
            comp.setdefault(f(r * C + c), []).append((r, c))
    cells = []
    for cs_ in comp.values():
        r0 = min(p[0] for p in cs_); r1 = max(p[0] for p in cs_)
        c0 = min(p[1] for p in cs_); c1 = max(p[1] for p in cs_)
        cells.append((r0, c0, r1 - r0 + 1, c1 - c0 + 1))
    cells.sort()
    # 병합 내부 경계는 NONE
    for (r, c, rs, cs) in cells:
        for rr in range(r, r + rs):
            for cc in range(c + 1, c + cs):
                vs[rr][cc] = None
        for cc in range(c, c + cs):
            for rr in range(r + 1, r + rs):
                hs[rr][cc] = None
    return {
        "xs": [x + v for v in xcen], "ys": [y + v for v in ycen],
        "h": hs, "v": vs, "cells": cells, "extras": extras, "ppm": ppm,
    }


def trim_outer(grid, row_k=2.2, col_k=4.0):
    """표 가장자리의 비정상적으로 큰 행/열(배경 화면, 비친 선 등)을 잘라낸다. 반환 (grid, 제거수 dict)"""
    removed = {"top": 0, "bottom": 0, "left": 0, "right": 0}
    while True:
        ys, xs = grid["ys"], grid["xs"]
        hs = [ys[i + 1] - ys[i] for i in range(len(ys) - 1)]
        ws = [xs[i + 1] - xs[i] for i in range(len(xs) - 1)]
        if len(hs) < 4 or len(ws) < 2:
            break
        mh, mw = float(np.median(hs)), float(np.median(ws))
        side = None
        if hs[0] > row_k * mh: side = "top"
        elif hs[-1] > row_k * mh: side = "bottom"
        elif len(ws) > 3 and ws[0] > col_k * mw: side = "left"
        elif len(ws) > 3 and ws[-1] > col_k * mw: side = "right"
        if side is None:
            break
        R, C = len(hs), len(ws)
        r0, r1, c0, c1 = 0, R, 0, C
        if side == "top": r0 = 1
        if side == "bottom": r1 = R - 1
        if side == "left": c0 = 1
        if side == "right": c1 = C - 1
        cells = []
        for (r, c, rs, cs) in grid["cells"]:
            if r >= r0 and c >= c0 and r + rs <= r1 and c + cs <= c1:
                cells.append((r - r0, c - c0, rs, cs))
        grid = dict(grid)
        grid["xs"], grid["ys"] = xs[c0:c1 + 1], ys[r0:r1 + 1]
        grid["h"] = [row[c0:c1] for row in grid["h"][r0:r1 + 1]]
        grid["v"] = [row[c0:c1 + 1] for row in grid["v"][r0:r1]]
        grid["cells"] = sorted(cells)
        removed[side] += 1
    return grid, removed
