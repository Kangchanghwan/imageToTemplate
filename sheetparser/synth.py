"""합성 표 PDF + 정답 TableSpec + 가짜 사진."""
import json
import os
import random

import cv2
import fitz
import numpy as np

PX_MM = 96 / 25.4
MM = 72 / 25.4
FONT = "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"
FONTB = "/usr/share/fonts/truetype/nanum/NanumGothicBold.ttf"
WORDS = ["이름", "날짜", "근무시간", "비고", "합계", "확인", "출근", "퇴근", "장소", "내용", "김민수", "2025.09.01", "09:00",
         "13:30", "4시간", "교과활동", "정보", "수학", "과학실", "도서관", "담당교사", "서명", "월", "화", "목", "1교시",
         "진산중학교", "총 근무시간", "점검", "특이사항 없음", "학습지원", "상담"]
TH = {"SOLID": 0.25, "SOLID_MEDIUM": 0.5, "SOLID_THICK": 1.0}
PASTEL = [(0.85, 0.92, 1.0), (1.0, 0.93, 0.8), (0.88, 0.97, 0.88), (0.93, 0.93, 0.93), (1.0, 0.88, 0.88)]


def _hex(c):
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def make_one(seed, outdir, name):
    rng = random.Random(seed)
    R, C = rng.randint(5, 11), rng.randint(3, 7)
    tw = rng.uniform(150, 185)
    w = [rng.uniform(0.6, 1.6) for _ in range(C)]
    colw = [x / sum(w) * tw for x in w]
    rowh = [rng.uniform(8, 14) for _ in range(R)]
    x0 = (210 - tw) / 2 + rng.uniform(-6, 6)
    y0 = rng.uniform(25, 55)
    # 병합
    occ = [[None] * C for _ in range(R)]
    merges = []
    def put(r, c, rs, cs):
        if r + rs > R or c + cs > C: return False
        if any(occ[a][b] is not None for a in range(r, r + rs) for b in range(c, c + cs)): return False
        for a in range(r, r + rs):
            for b in range(c, c + cs): occ[a][b] = (r, c)
        merges.append((r, c, rs, cs)); return True
    if rng.random() < 0.7: put(0, 0, 1, C)
    for _ in range(rng.randint(2, 4)):
        for _t in range(10):
            rs, cs = rng.randint(1, 3), rng.randint(1, 3)
            if rs * cs > 1 and put(rng.randrange(R), rng.randrange(C), rs, cs): break
    anchors = []
    for r in range(R):
        for c in range(C):
            if occ[r][c] is None: anchors.append((r, c, 1, 1))
    anchors += merges
    anchors.sort()
    # 선 스타일
    def pick(outer):
        if outer: return rng.choice(["SOLID_THICK", "SOLID_MEDIUM", "SOLID_MEDIUM"])
        return rng.choices(["SOLID", "SOLID_MEDIUM", "SOLID_THICK"], [60, 28, 12])[0]
    hl = [pick(i in (0, R)) for i in range(R + 1)]
    vl = [pick(j in (0, C)) for j in range(C + 1)]
    if R > 3 and rng.random() < 0.5: hl[rng.choice([1, 2])] = "DOUBLE"
    xs = [x0]
    for a in colw: xs.append(xs[-1] + a)
    ys = [y0]
    for a in rowh: ys.append(ys[-1] + a)
    cover = lambda r, c: occ[r][c]
    hb = [["NONE"] * C for _ in range(R + 1)]
    vb = [["NONE"] * (C + 1) for _ in range(R)]
    for i in range(R + 1):
        for c in range(C):
            inside = 0 < i < R and occ[i - 1][c] is not None and occ[i - 1][c] == occ[i][c]
            hb[i][c] = "NONE" if inside else hl[i]
    for r in range(R):
        for j in range(C + 1):
            inside = 0 < j < C and occ[r][j - 1] is not None and occ[r][j - 1] == occ[r][j]
            vb[r][j] = "NONE" if inside else vl[j]
    doc = fitz.open()
    page = doc.new_page(width=595.276, height=841.89)
    page.insert_font(fontname="ng", fontfile=FONT)
    page.insert_font(fontname="ngb", fontfile=FONTB)
    fnt = {"ng": fitz.Font(fontfile=FONT), "ngb": fitz.Font(fontfile=FONTB)}
    cells = []
    for (r, c, rs, cs) in anchors:
        cx0, cx1, cy0, cy1 = xs[c], xs[c + cs], ys[r], ys[r + rs]
        bg = None
        if rng.random() < 0.22 or (r == 1 and rng.random() < 0.4):
            bg = rng.choice(PASTEL)
            page.draw_rect(fitz.Rect(cx0 * MM, cy0 * MM, cx1 * MM, cy1 * MM), fill=bg, color=None, width=0)
        title = (r == 0 and cs == C)
        bold = title or (r == 1 and rng.random() < 0.5) or rng.random() < 0.08
        size = 14 if title else rng.choice([8, 9, 10, 10, 11])
        text, hh, vv = "", "LEFT", "MIDDLE"
        if title: text = "근무일정표"; hh = "CENTER"
        elif rng.random() < 0.8:
            nl = 2 if ((cy1 - cy0) > 2 * size * 0.4 * 1.25 + 7 and rng.random() < 0.3) else 1
            lines = []
            cw_ = cx1 - cx0
            for _ in range(nl):
                t = rng.choice(WORDS)
                while True:
                    tl = fnt["ngb" if bold else "ng"].text_length(t, size) / MM
                    if tl <= 0.7 * cw_ or len(t) <= 1: break
                    t = t[:-1]
                lines.append(t)
            text = "\n".join(lines)
            hh = rng.choice(["LEFT", "CENTER", "RIGHT"])
            vv = rng.choice(["TOP", "MIDDLE", "BOTTOM"])
        if text:
            fn = "ngb" if bold else "ng"
            lines = text.split("\n")
            lh = size * 1.25 / MM  # mm
            blk = lh * len(lines)
            if (cy1 - cy0) - blk - 2.4 < 0.2 * (cy1 - cy0): vv = "MIDDLE"
            ytop = {"TOP": cy0 + 1.2, "MIDDLE": (cy0 + cy1) / 2 - blk / 2, "BOTTOM": cy1 - 1.2 - blk}[vv]
            for k, ln in enumerate(lines):
                tl = fnt[fn].text_length(ln, size) / MM
                xx = {"LEFT": cx0 + 1.5, "CENTER": (cx0 + cx1) / 2 - tl / 2, "RIGHT": cx1 - 1.5 - tl}[hh]
                page.insert_text((xx * MM, (ytop + k * lh) * MM + size * 0.92), ln, fontname=fn, fontsize=size)
        cells.append({"r": r, "c": c, "rs": rs, "cs": cs, "text": text, "h": hh, "v": vv, "size_pt": size,
                      "bold": bool(bold), "bg": _hex(bg) if bg else None, "wrap": True,
                      "src_bbox": [round(cx0 * MM, 2), round(cy0 * MM, 2), round(cx1 * MM, 2), round(cy1 * MM, 2)]})
    # 선
    def seg(p1, p2, style):
        if style == "NONE": return
        wmm = TH.get(style)
        e = 0
        if style == "DOUBLE":
            for off in (-0.45, 0.45):
                a = (p1[0] + (off if p1[0] == p2[0] else 0), p1[1] + (off if p1[1] == p2[1] else 0))
                b = (p2[0] + (off if p1[0] == p2[0] else 0), p2[1] + (off if p1[1] == p2[1] else 0))
                page.draw_line((a[0] * MM, a[1] * MM), (b[0] * MM, b[1] * MM), width=0.3 * MM, lineCap=2)
            return
        page.draw_line((p1[0] * MM, p1[1] * MM), (p2[0] * MM, p2[1] * MM), width=wmm * MM, lineCap=2)
    for i in range(R + 1):
        for c in range(C): seg((xs[c], ys[i]), (xs[c + 1], ys[i]), hb[i][c])
    for r in range(R):
        for j in range(C + 1): seg((xs[j], ys[r]), (xs[j], ys[r + 1]), vb[r][j])
    cum = lambda v: [int(round((a - v[0]) * PX_MM)) for a in v]
    cx, cy = cum(xs), cum(ys)
    gt = {"version": 1, "source": {"path": name + ".pdf", "kind": "pdf_vector", "page": 0}, "page_mm": [210, 297],
          "origin_mm": [round(x0, 2), round(y0, 2)],
          "columns": [cx[i + 1] - cx[i] for i in range(C)], "rows": [cy[i + 1] - cy[i] for i in range(R)],
          "cells": cells, "borders": {"h": hb, "v": vb}, "flags": []}
    os.makedirs(outdir, exist_ok=True)
    doc.save(os.path.join(outdir, name + ".pdf"))
    json.dump(gt, open(os.path.join(outdir, name + ".json"), "w"), ensure_ascii=False)
    fake_photo(os.path.join(outdir, name + ".pdf"), os.path.join(outdir, name + "_photo.jpg"), rng)
    return gt


def fake_photo(pdf, out, rng):
    page = fitz.open(pdf)[0]
    pix = page.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace=fitz.csRGB, alpha=False)
    a = cv2.cvtColor(np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3), cv2.COLOR_RGB2BGR)
    # 약간 누런 종이색
    a = (a.astype(np.float32) * np.array([0.93, 0.96, 0.98])).astype(np.uint8)
    H, W = 4300, 3200
    mx, my = rng.randint(250, 350), rng.randint(300, 450)
    bg = np.full((H, W, 3), (70, 95, 120), np.uint8)
    bg = (bg.astype(np.float32) + np.random.RandomState(rng.randint(0, 9999)).randn(H, W, 1) * 6).clip(0, 255).astype(np.uint8)
    ph, pw = a.shape[:2]
    ox, oy = mx, my
    bg[oy:oy + ph, ox:ox + pw] = a
    src = np.float32([[0, 0], [W, 0], [W, H], [0, H]])
    j = lambda: rng.uniform(-0.035, 0.035)
    ang = np.deg2rad(rng.uniform(-2.5, 2.5))
    dst = np.float32([[0 + j() * W, 0 + j() * H], [W + j() * W, j() * H], [W + j() * W, H + j() * H], [j() * W, H + j() * H]])
    c = np.array([W / 2, H / 2])
    Rm = np.array([[np.cos(ang), -np.sin(ang)], [np.sin(ang), np.cos(ang)]])
    dst = ((dst - c) @ Rm.T + c).astype(np.float32)
    M = cv2.getPerspectiveTransform(src, dst)
    o = cv2.warpPerspective(bg, M, (W, H), borderValue=(60, 80, 100))
    # 조명 기울기
    gx = np.linspace(rng.uniform(0.82, 1.0), rng.uniform(0.9, 1.05), W)[None, :, None]
    gy = np.linspace(rng.uniform(0.85, 1.0), rng.uniform(0.9, 1.05), H)[:, None, None]
    o = (o.astype(np.float32) * gx * gy)
    o = cv2.GaussianBlur(o, (0, 0), rng.uniform(1.0, 1.8))
    o += np.random.RandomState(rng.randint(0, 9999)).randn(H, W, 1).astype(np.float32) * 4
    o = cv2.resize(o.clip(0, 255).astype(np.uint8), (2400, int(2400 * H / W)), interpolation=cv2.INTER_AREA)
    cv2.imwrite(out, o, [cv2.IMWRITE_JPEG_QUALITY, 88])


def synth(outdir, n=12, seed=7):
    for i in range(n):
        make_one(seed * 1000 + i, outdir, "s%02d" % i)
