"""입력 -> TableSpec. photo / pdf_scan / pdf_vector 분기."""
import json
import os
import time

import cv2
import fitz
import numpy as np

from . import grid as G, ocr as OCR, pdfvec as PV, preprocess as PP, style as ST

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


def run(path, ocr=True, debug_dir=None):
    if path.lower().endswith(".pdf"):
        return run_pdf(path, ocr, debug_dir)
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
