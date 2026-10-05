"""입력 -> TableSpec. photo / pdf_scan / pdf_vector 분기."""
import json
import os
import time

import cv2
import fitz
import numpy as np

from . import grid as G, layout as LY, ocr as OCR, pdfvec as PV, preprocess as PP, style as ST

PX_MM = 96 / 25.4
PT_MM = 25.4 / 72
THICK_BIAS_MM = 0.2


def _hex(bgr):
    b, g, r = [int(max(0, min(255, round(v)))) for v in bgr]
    return "#%02x%02x%02x" % (r, g, b)


def _assemble(grid, img, kind, source_path, page_mm, flags, page_no=0, spans=None, ocr=False):
    ppm_g = grid["ppm"]
    xs_mm = [x / ppm_g for x in grid["xs"]]
    ys_mm = [y / ppm_g for y in grid["ys"]]
    R, C = len(ys_mm) - 1, len(xs_mm) - 1
    cum = lambda v: [int(round((a - v[0]) * PX_MM)) for a in v]
    cx, cy = cum(xs_mm), cum(ys_mm)
    columns = [cx[i + 1] - cx[i] for i in range(C)]
    rows = [cy[i + 1] - cy[i] for i in range(R)]
    bias = 0.0 if kind == "pdf_vector" else THICK_BIAS_MM  # 래스터 이진화/블러로 선이 굵게 측정되는 만큼 보정
    sn = lambda i: ST.style_name(None if i is None else (max(i[0] - bias, 0), i[1]))
    h = [[sn(grid["h"][i][c]) for c in range(C)] for i in range(R + 1)]
    v = [[sn(grid["v"][r][j]) for j in range(C + 1)] for r in range(R)]

    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    cells, infos = [], []
    for (r, c, rs, cs) in grid["cells"]:
        rect = (xs_mm[c] * PP.PPM, ys_mm[r] * PP.PPM, xs_mm[c + cs] * PP.PPM, ys_mm[r + rs] * PP.PPM)
        info = ST.analyze(img, gray, rect)
        infos.append(info)
        cells.append({"r": r, "c": c, "rs": rs, "cs": cs, "_rect": rect})
    bgs = [i["bgr"] for i in infos if i.get("bgr") is not None]
    ref = np.median(np.array(bgs), axis=0) if bgs else np.array([255, 255, 255.0])
    ref = np.maximum(ref, 1)
    for cell, info in zip(cells, infos):
        cell["_empty"] = info["empty"]
        cell["_bgr"] = info["bgr"] if info.get("bgr") is not None else None
        bg = None
        if info.get("bgr") is not None and np.abs(info["bgr"] - ref).max() > 18:
            bg = _hex(np.minimum(info["bgr"] * 255.0 / ref, 255))
        cell.update({"text": "", "h": info.get("h", "LEFT"), "v": info.get("v", "MIDDLE"),
                     "size_pt": info.get("size_pt", 10), "bold": info.get("bold", False), "bg": bg, "wrap": True})
        r0, c0, rs, cs = cell["r"], cell["c"], cell["rs"], cell["cs"]
        x0, y0, x1, y1 = cell["_rect"]
        if kind == "pdf_vector":
            cell["src_bbox"] = [round(a * PT_MM ** -1 / 10, 2) for a in (x0, y0, x1, y1)]
        else:
            cell["src_bbox"] = [int(round(a)) for a in (x0, y0, x1, y1)]
    meta = {}
    if spans is not None:  # pdf_vector 텍스트 레이어
        owner = {}
        for cell in cells:
            for rr in range(cell["r"], cell["r"] + cell["rs"]):
                for cc in range(cell["c"], cell["c"] + cell["cs"]):
                    owner[(rr, cc)] = cell
        per = {}
        for sp in spans:
            cx_ = (sp["bbox"][0] + sp["bbox"][2]) / 2 * PT_MM
            cy_ = (sp["bbox"][1] + sp["bbox"][3]) / 2 * PT_MM
            cc = int(np.searchsorted(xs_mm, cx_) - 1)
            rr = int(np.searchsorted(ys_mm, cy_) - 1)
            if (rr, cc) in owner:
                per.setdefault(id(owner[(rr, cc)]), (owner[(rr, cc)], []))[1].append(sp)
        for cell, sps in per.values():
            lines = {}
            for sp in sps:
                lines.setdefault(round(sp["origin"][1]), []).append(sp)
            txt = []
            for k in sorted(lines):
                txt.append("".join(s["text"] for s in sorted(lines[k], key=lambda s: s["origin"][0])))
            cell["text"] = "\n".join(txt)
            cell["size_pt"] = round(max(s["size"] for s in sps) * 2) / 2
            cell["bold"] = sum(s["bold"] for s in sps) * 2 > len(sps)
            cell["_empty"] = False
    elif ocr:
        meta["ocr"] = OCR.fill_text(img, cells, None, None)
    fl = list(flags)
    for cell in cells:
        if cell.pop("_flag", None):
            fl.append({"r": cell["r"], "c": cell["c"], "reason": "low_ocr_conf"})
        cell.pop("_rect"); cell.pop("_empty"); cell.pop("_bgr", None)
    for e in grid["extras"]:
        fl.append({"reason": "extra_table_ignored", "bbox": [int(a / ppm_g * 10) for a in e]})
    spec = {
        "version": 1,
        "source": {"path": source_path, "kind": kind, "page": page_no},
        "page_mm": page_mm,
        "origin_mm": [round(xs_mm[0], 2), round(ys_mm[0], 2)],
        "columns": columns, "rows": rows, "cells": cells,
        "borders": {"h": h, "v": v}, "flags": fl,
    }
    if meta:
        spec["meta"] = meta
    return spec


def run_pdf(path, ocr=True, debug_dir=None, page_no=0):
    doc = fitz.open(path)
    page = doc[page_no]
    t0 = time.time()
    pg_mm = [round(page.rect.width * PT_MM, 1), round(page.rect.height * PT_MM, 1)]
    if PV.is_vector(page):
        mask = PV.vec_mask(page)
        img = PV.render(page, PP.PPM)
        grid = G.build_grid(mask, PV.MASK_PPM)
        spec = _assemble(grid, img, "pdf_vector", path, pg_mm, [], page_no, spans=PV.spans(page))
    else:
        img = PV.render(page, PP.PPM)
        return run_image(None, path, ocr, debug_dir, kind="pdf_scan", img=img)
    spec.setdefault("meta", {})["sec_geom"] = round(time.time() - t0, 2)
    if debug_dir:
        _debug(img, grid, spec, debug_dir, path)
    return spec


def run_image(path, source_path=None, ocr=True, debug_dir=None, kind="photo", img=None):
    t0 = time.time()
    if img is None:
        img = cv2.imread(path)
        if img is None:
            raise RuntimeError("cannot read " + str(path))
    flags = []
    pad_origin = None
    if kind == "photo":
        img, pg_mm, flags = PP.rectify(img)
        if any(f["reason"].startswith(("no_paper", "paper_")) for f in flags):
            img, org, ok = PP.table_rectify(img)
            flags.append({"reason": "table_quad_rectified" if ok else "table_quad_failed"})
            if ok:
                pad_origin = org
    else:
        pg_mm = [round(img.shape[1] / 10, 1), round(img.shape[0] / 10, 1)]
    mask = PP.line_mask(img)
    try:
        grid = G.build_grid(mask, PP.PPM)
    except RuntimeError as e:
        raise RuntimeError("grid_failed:%s" % e)
    spec = _assemble(grid, img, kind, source_path or path, pg_mm, flags, 0, spans=None, ocr=ocr)
    if pad_origin is not None:
        # 보정 이미지는 표 외곽 기준(여백 60px)이므로 용지상 위치는 추정값
        spec["origin_mm"] = [round(pad_origin[0] + spec["origin_mm"][0] - 6.0, 2), round(pad_origin[1] + spec["origin_mm"][1] - 6.0, 2)]
    spec.setdefault("meta", {})["sec_total"] = round(time.time() - t0, 2)
    if debug_dir:
        _debug(img, grid, spec, debug_dir, source_path or path)
    return spec


def run(path, ocr=True, debug_dir=None, v1=False):
    if path.lower().endswith(".pdf"):
        if v1:
            return run_pdf(path, ocr, debug_dir)
        return run_pdf_page(path, debug_dir)
    return run_image(path, path, ocr, debug_dir)


def _debug(img, grid, spec, d, src):
    os.makedirs(d, exist_ok=True)
    out = img.copy()
    ov = out.copy()
    k = grid["ppm"] / PP.PPM
    xs = [x / k for x in grid["xs"]]
    ys = [y / k for y in grid["ys"]]
    for (r, c, rs, cs) in grid["cells"]:
        if rs > 1 or cs > 1:
            cv2.rectangle(ov, (int(xs[c]), int(ys[r])), (int(xs[c + cs]), int(ys[r + rs])), (255, 120, 0), -1)
    out = cv2.addWeighted(ov, 0.3, out, 0.7, 0)
    for r in range(len(ys) - 1):
        for j in range(len(xs)):
            if grid["v"][r][j] is not None:
                cv2.line(out, (int(xs[j]), int(ys[r])), (int(xs[j]), int(ys[r + 1])), (0, 0, 255), 2)
    for i in range(len(ys)):
        for c in range(len(xs) - 1):
            if grid["h"][i][c] is not None:
                cv2.line(out, (int(xs[c]), int(ys[i])), (int(xs[c + 1]), int(ys[i])), (0, 0, 255), 2)
    name = os.path.splitext(os.path.basename(src))[0]
    spec.setdefault("meta", {})["rectified"] = os.path.join(d, name + "_rectified.jpg")
    cv2.imwrite(os.path.join(d, name + "_overlay.png"), out)
    cv2.imwrite(os.path.join(d, name + "_rectified.jpg"), img, [cv2.IMWRITE_JPEG_QUALITY, 90])


# ------------------------------------------------------------------ v2: PDF 페이지 전체
def _cell_align(tb, rect):
    """tb=(x0,y0,x1,y1) 글자 영역, rect=셀 (pt). -> (h, v)"""
    L, Rm = tb[0] - rect[0], rect[2] - tb[2]
    T, B = tb[1] - rect[1], rect[3] - tb[3]
    cw, ch = rect[2] - rect[0], rect[3] - rect[1]
    if abs(L - Rm) <= max(3.0, 0.08 * cw):
        h = "CENTER"
    else:
        h = "LEFT" if L < Rm else "RIGHT"
    if abs(T - B) <= max(2.5, 0.2 * ch):
        v = "MIDDLE"
    else:
        v = "TOP" if T < B else "BOTTOM"
    return h, v


BASE_DY_MM_PER_PT = 0.082  # 시트 글자 기준선이 원본보다 내려가는 정도 (측정값)


def run_pdf_page(path, debug_dir=None, page_no=0, font="Calibri"):
    doc = fitz.open(path)
    page = doc[page_no]
    t0 = time.time()
    W_mm, H_mm = round(page.rect.width * PT_MM, 1), round(page.rect.height * PT_MM, 1)
    lines = PV.text_lines(page)
    skip, ul = PV.underline_segs(page, lines)
    mask = PV.mask_v2(page, skip)
    table, tb_pt = None, None
    flags = []
    try:
        grid = G.build_grid(mask, PV.MASK_PPM)
    except RuntimeError:
        grid = None
    fl = PV.fills(page)
    if grid is not None:
        ppm = grid["ppm"]
        xs = [x / ppm for x in grid["xs"]]
        ys = [y / ppm for y in grid["ys"]]
        xs_pt = [v / PT_MM for v in xs]
        ys_pt = [v / PT_MM for v in ys]
        tb_pt = (xs_pt[0], ys_pt[0], xs_pt[-1], ys_pt[-1])
        sn = lambda i: ST.style_name(i)
        R, C = len(ys) - 1, len(xs) - 1
        bh = [[sn(grid["h"][i][c]) for c in range(C)] for i in range(R + 1)]
        bv = [[sn(grid["v"][r][j]) for j in range(C + 1)] for r in range(R)]
        cells, owner = [], {}
        for (r, c, rs, cs) in grid["cells"]:
            cell = {"r": r, "c": c, "rs": rs, "cs": cs, "text": "", "h": "CENTER", "v": "MIDDLE", "size_pt": 10,
                    "bold": False, "wrap": False, "bg": None, "font": font, "underline": False, "italic": False,
                    "color": "#000000", "_lines": []}
            rect = (xs_pt[c], ys_pt[r], xs_pt[c + cs], ys_pt[r + rs])
            cell["_rect"] = rect
            cell["src_bbox"] = [round(v * PT_MM, 2) for v in rect]
            cx_, cy_ = (rect[0] + rect[2]) / 2, (rect[1] + rect[3]) / 2
            for f in fl:  # 마지막(위에 그려진) 채움 우선
                if f[0] - 0.5 <= cx_ <= f[2] + 0.5 and f[1] - 0.5 <= cy_ <= f[3] + 0.5:
                    cell["bg"] = f[4]
            if cell["bg"] and cell["bg"].lower() in ("#ffffff", "#fefefe"):
                cell["bg"] = None
            for rr in range(r, r + rs):
                for cc in range(c, c + cs):
                    owner[(rr, cc)] = cell
            cells.append(cell)
    blocks = []
    last_h = None
    for l in lines:
        whole = PV.whole_line(l)
        cx_, cy_ = (whole["x0"] + whole["x1"]) / 2, (whole["y0"] + whole["y1"]) / 2
        inside = tb_pt and tb_pt[0] - 1 <= cx_ <= tb_pt[2] + 1 and tb_pt[1] - 1 <= cy_ <= tb_pt[3] + 1
        if inside:
            cc = int(np.searchsorted(xs_pt, cx_) - 1)
            rr = int(np.searchsorted(ys_pt, cy_) - 1)
            cell = owner.get((min(max(rr, 0), R - 1), min(max(cc, 0), C - 1)))
            if cell is not None:
                whole["ul"] = PV.is_underlined(whole, ul)
                cell["_lines"].append(whole)
            continue
        for sg in PV.split_segments(l):
            sg["ul"] = PV.is_underlined(sg, ul)
            blocks.append((l, sg))
    if grid is not None:
        for cell in cells:
            ls = sorted(cell.pop("_lines"), key=lambda s: (round(s["oy"] / 2), s["x0"]))
            rect = cell.pop("_rect")
            if not ls:
                continue
            merged = []
            for s_ in ls:  # 같은 기준선의 조각은 한 줄로
                if merged and abs(merged[-1]["oy"] - s_["oy"]) < 2:
                    merged[-1]["text"] += " " + s_["text"]
                    merged[-1]["x1"] = max(merged[-1]["x1"], s_["x1"])
                else:
                    merged.append(dict(s_))
            cell["text"] = "\n".join(m["text"] for m in merged)
            cell["wrap"] = len(merged) > 1
            cell["size_pt"] = max(m["size"] for m in merged)
            cell["bold"] = sum(m["bold"] for m in merged) * 2 > len(merged)
            cell["underline"] = all(m["ul"] for m in merged)
            cell["color"] = merged[0]["color"]
            tb = (min(m["x0"] for m in merged), min(m["y0"] for m in merged),
                  max(m["x1"] for m in merged), max(m["y1"] for m in merged))
            cell["h"], cell["v"] = _cell_align(tb, rect)
            # 시트 글자 크기는 정수(PDF에서 0.975배): 칸 폭에 안 들어가면 한 단계 내린다
            pt = max(1, int(cell["size_pt"] / 0.975 + 0.5))
            tw = max(m["x1"] - m["x0"] for m in merged)
            if tw * pt * 0.975 / cell["size_pt"] > (rect[2] - rect[0]) - 3.5 and pt > 1:
                pt -= 1
            cell["sheet_pt"] = pt
        for cell in cells:
            cell.pop("_lines", None)
            cell.pop("_rect", None)
        table = {"x_mm": xs, "y_mm": ys, "cells": cells, "borders": {"h": bh, "v": bv}}
    # 블록: 정렬 추정 (표/페이지 중앙 가까우면 CENTER, 표 오른쪽 끝 가까우면 RIGHT)
    ref_l = tb_pt[0] if tb_pt else 36.0
    ref_r = tb_pt[2] if tb_pt else page.rect.width - 36.0
    pc = (ref_l + ref_r) / 2
    bl = []
    # 한 줄의 마지막 조각 판별을 위해 줄별로 묶음
    by_line = {}
    for l, sg in blocks:
        by_line.setdefault(id(l), []).append(sg)
    for segs in by_line.values():
        segs.sort(key=lambda s: s["x0"])
        for k, sg in enumerate(segs):
            cx_ = (sg["x0"] + sg["x1"]) / 2
            if len(segs) == 1 and abs(cx_ - pc) < 8:
                h = "CENTER"
            elif k == len(segs) - 1 and abs(sg["x1"] - ref_r) < 14 and sg["x0"] > pc:
                h = "RIGHT"
            else:
                h = "LEFT"
            dy = -BASE_DY_MM_PER_PT * sg["size"]
            bl.append({"bbox_mm": [sg["x0"] * PT_MM, sg["y0"] * PT_MM + dy, sg["x1"] * PT_MM, sg["y1"] * PT_MM + dy],
                       "text": sg["text"], "size_pt": sg["size"], "bold": sg["bold"], "underline": sg["ul"],
                       "font": font, "h": h, "color": sg["color"], "italic": False, "v": "MIDDLE"})
    ims = [{"bbox_mm": [v * PT_MM for v in im["bbox"]], "png_b64": im["png_b64"]} for im in PV.images(page)]
    spec = LY.build_page_spec([W_mm, H_mm], table, bl, ims, {"path": path, "kind": "pdf_vector", "page": page_no})
    for c in spec["cells"]:
        c["size_pt"] = round(c["size_pt"] * 2) / 2
        if "sheet_pt" in c:  # 시트에 실제 보낼 정수 크기 (upload 가 우선 사용)
            pass
    spec["flags"] += flags
    spec["meta"]["sec_geom"] = round(time.time() - t0, 2)
    if debug_dir:
        os.makedirs(debug_dir, exist_ok=True)
    return spec
