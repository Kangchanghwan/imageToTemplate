"""대조용 Python 덤프: 입력별 중간 산출물을 JSON + PNG 로 저장한다 (OCR 없음).

사용: python tools/parity/dump_py.py <outdir>      (elgrim docker 에서 실행, 맥 cv2 없음)
  <outdir>/inputs/<name>.png   JS 입력(파이썬이 디코드한 BGR 을 무손실 PNG 로. scan 은 300dpi 렌더 PNG)
  <outdir>/py/<name>.json      단계별 덤프
  <outdir>/py/<name>_rect.png  원근 보정 후 이미지(table_rectify 포함), _flat.png 평탄화 후
  <outdir>/manifest.json

오케스트레이션은 photopage._run_page 앞부분(입력 -> 보정 -> 격자 -> 칸 생성)과 같은 순서로 같은 함수만 호출한다.
교차 확인용으로 photopage.run_page(ocr=False) 결과(spec)의 src_bbox/병합/flags 도 같이 덤프한다.
"""
import glob
import hashlib
import json
import os
import sys
import time

import cv2
import fitz
import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from sheetparser import grid as G, photopage as PPG, preprocess as PP, style as ST  # noqa: E402
from sheetparser.convert import SCAN_DPI  # noqa: E402

PPM = PP.PPM
if os.environ.get('PARITY_NOOPT') == '1':   # 대조 실험 전용(기본 꺼짐): cv2 SIMD 디스패치 끄기. 운영 경로와 다르므로 원인 분석에만 쓴다
    cv2.setUseOptimized(False)


def sha(a):
    return hashlib.sha256(np.ascontiguousarray(a).tobytes()).hexdigest()


def jn(o):
    if isinstance(o, dict):
        return {str(k): jn(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jn(v) for v in o]
    if isinstance(o, np.ndarray):
        return jn(o.tolist())
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    return o


def grid_dump(g):
    return {"xs": g["xs"], "ys": g["ys"], "h": g["h"], "v": g["v"], "cells": [list(c) for c in g["cells"]],
            "extras": g["extras"], "ext_left": bool(g.get("ext_left", False))}


def groups_dump(grid_mask, ppm):
    hb, vb = G.line_masks(grid_mask, ppm)
    return hb, vb


def inputs():
    out = []
    for n in ("sched_09", "sched_10", "sched_11", "sched_12", "form_activity", "form_attendance", "form_meal"):
        out.append((n, "photo", "data/photos/%s.jpg" % n))
    for n in ("activity", "attendance", "meal"):
        out.append((n + "_300dpi", "photo", "data/pdfs/%s_09_300dpi.png" % n))
        out.append(("scan_" + n, "pdf_scan", "data/pdfs/scan_%s_09.pdf" % n))
    for p in sorted(glob.glob("data/synth/s*_photo.jpg")):
        out.append((os.path.basename(p)[:-4], "photo", p))
    return out


def load(kind, path, outdir, name):
    """반환 (img0 = 파이프라인 입력, JS 입력 PNG 경로)"""
    ip = os.path.join(outdir, "inputs", name + ".png")
    if kind == "photo":
        img = cv2.imread(path)
        cv2.imwrite(ip, img)
        return img, ip
    page = fitz.open(path)[0]
    s = SCAN_DPI / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), colorspace=fitz.csRGB, alpha=False)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3)
    big = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    cv2.imwrite(ip, big)
    k = PP.PPM / (SCAN_DPI / 25.4)
    return cv2.resize(big, None, fx=k, fy=k, interpolation=cv2.INTER_AREA), ip


def dump_one(name, kind, path, outdir):
    t0 = time.time()
    img0, ip = load(kind, path, outdir, name)
    d = {"name": name, "kind": kind, "src": path, "input_shape": list(img0.shape), "input_sha": sha(img0)}
    if kind == "pdf_scan":
        # JS 는 300dpi PNG 를 읽어 같은 resize 를 한다. resize 결과 대조용
        d["input300_shape"] = list(cv2.imread(ip).shape)
    if kind == "photo":
        fp = PP.find_paper(img0)
        d["find_paper"] = None if fp is None else {"quad": fp[0].tolist(), "touch": int(fp[1])}
        img, pg_mm, flags = PP.rectify(img0)
    else:
        img, pg_mm, flags = img0, [round(img0.shape[1] / PPM, 1), round(img0.shape[0] / PPM, 1)], [{"reason": "pdf_scan_no_perspective"}]
    d["rectify"] = {"shape": list(img.shape), "pg_mm": pg_mm, "flags": [dict(f) for f in flags], "sha": sha(img)}
    if kind != "pdf_scan" and any(f["reason"].startswith(("no_paper", "paper_")) for f in flags):
        img, org, ok = PP.table_rectify(img, keep_frame=True)
        flags.append({"reason": "table_quad_rectified" if ok else "table_quad_failed"})
        flags.append({"reason": "mm_scale_from_table_estimate"})
        pg_mm = [210, round(img.shape[0] / PPM, 1)]
        d["table_rectify"] = {"ok": bool(ok), "origin": org, "shape": list(img.shape), "sha": sha(img)}
    d["rect_shape"] = list(img.shape)
    d["rect_sha"] = sha(img)
    d["pg_mm"] = pg_mm
    cv2.imwrite(os.path.join(outdir, "py", name + "_rect.png"), img)
    mask = PP.line_mask(img)
    hb, vb = G.line_masks(mask, PPM)
    d["mask"] = {"nz": int(np.count_nonzero(mask)), "sha": sha(mask), "hb_nz": int(np.count_nonzero(hb)), "hb_sha": sha(hb),
                 "vb_nz": int(np.count_nonzero(vb)), "vb_sha": sha(vb)}
    try:
        grid = G.build_grid(mask, PPM)
    except RuntimeError as e:
        d["error"] = "grid_failed:%s" % e
        json.dump(jn(d), open(os.path.join(outdir, "py", name + ".json"), "w"), ensure_ascii=False)
        return d
    d["grid_raw"] = grid_dump(grid)
    grid, trimmed = G.trim_outer(grid)
    d["trim"] = {"removed": trimmed, "grid": grid_dump(grid)}
    if any(trimmed.values()):
        flags.append({"reason": "outer_rows_cols_trimmed:" + ",".join("%s=%d" % kv for kv in trimmed.items() if kv[1])})
    grid = PPG._extend_left(grid, mask)
    if grid.get("ext_left"):
        flags.append({"reason": "table_clipped_left_column_added"})
    d["grid"] = grid_dump(grid)
    d["flags"] = flags
    xs_mm = [x / PPM for x in grid["xs"]]
    ys_mm = [y / PPM for y in grid["ys"]]
    tb = (grid["xs"][0], grid["ys"][0], grid["xs"][-1], grid["ys"][-1])
    flat = PP.flatten(img, tb)
    d["flat_sha"] = sha(flat)
    cv2.imwrite(os.path.join(outdir, "py", name + "_flat.png"), flat)
    fgray = cv2.cvtColor(flat, cv2.COLOR_BGR2GRAY)
    cells = []
    for (r, c, rs, cs) in grid["cells"]:
        rect = (xs_mm[c] * PPM, ys_mm[r] * PPM, xs_mm[c + cs] * PPM, ys_mm[r + rs] * PPM)
        info = ST.analyze(flat, fgray, rect)
        cells.append({"r": r, "c": c, "rs": rs, "cs": cs, "_rect": rect, "_empty": bool(info["empty"]),
                      "info": {k: v for k, v in info.items() if k != "empty"}})
    d["cells"] = cells
    d["merges"] = [[c["r"], c["c"], c["rs"], c["cs"]] for c in cells if c["rs"] > 1 or c["cs"] > 1]
    # 교차 확인: 실제 run_page(ocr=False) 결과
    try:
        spec = PPG.run_page(path, ocr=False, source_path=path, img0=img0, kind=kind)
        d["spec_check"] = {"src_bbox": [c["src_bbox"] for c in spec["cells"]] if "cells" in spec else None,
                           "flags": spec.get("flags"), "keys": list(spec.keys())}
        tbl = spec.get("table") or {}
        d["spec_check"]["ncells"] = len(spec.get("cells", tbl.get("cells", [])))
    except Exception as e:  # noqa: BLE001
        d["spec_check"] = {"error": repr(e)}
    d["sec"] = round(time.time() - t0, 2)
    json.dump(jn(d), open(os.path.join(outdir, "py", name + ".json"), "w"), ensure_ascii=False)
    return d


def main():
    outdir = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(os.path.join(outdir, "inputs"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "py"), exist_ok=True)
    man = []
    for name, kind, path in inputs():
        if only and name not in only:
            continue
        if not os.path.exists(path):
            print("skip (없음):", path)
            continue
        d = dump_one(name, kind, path, outdir)
        man.append({"name": name, "kind": kind, "file": "inputs/%s.png" % name})
        print(name, kind, d.get("rect_shape"), d.get("error", ""), d.get("sec"), flush=True)
    json.dump({"cv2": cv2.__version__, "numpy": np.__version__, "inputs": man}, open(os.path.join(outdir, "manifest.json"), "w"), indent=1)


if __name__ == "__main__":
    main()
