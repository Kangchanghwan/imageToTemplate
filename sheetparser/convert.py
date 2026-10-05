"""단일 진입점: 입력(pdf/jpg/png) 자동 판별 -> PageSpec v2 -> 시트 업로드 -> 검증 -> 요약.

  python -m sheetparser convert <input> [-o runs/convert/<name>] [--title T] [--verify] [--keep|--delete]

판별: PDF 에 텍스트 레이어 + 벡터 선이 있으면 pdf_vector, PDF 인데 없으면(스캔) pdf_scan(300dpi 렌더 후 사진 경로, 원근 보정 생략),
이미지(jpg/png)면 photo. 기본은 스펙 생성 + 업로드(URL 반환)까지만 한다. --verify 를 주면 시트를 PDF 로 내보내 원본과 겹쳐
채점하고 정답 채점(content_score)도 한다. 검증 시 사진 경로는 verify_photo, PDF 벡터는 verify 로 검증한다.
"""
import json
import os
import shutil
import time

import cv2
import fitz
import numpy as np

from . import pdfvec as PV, preprocess as PP

SCAN_DPI = 300


def detect(path):
    if path.lower().endswith(".pdf"):
        return "pdf_vector" if PV.is_vector(fitz.open(path)[0]) else "pdf_scan"
    return "photo"


def _render_scan(path, outdir, name):
    """pdf_scan: 300dpi 렌더 -> 10px/mm 로 정규화 (용지 외곽이 곧 페이지이므로 원근 보정은 하지 않는다)."""
    page = fitz.open(path)[0]
    s = SCAN_DPI / 72
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), colorspace=fitz.csRGB, alpha=False)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3)
    img = cv2.cvtColor(a, cv2.COLOR_RGB2BGR)
    cv2.imwrite(os.path.join(outdir, name + "_300dpi.png"), img)
    k = PP.PPM / (SCAN_DPI / 25.4)
    return cv2.resize(img, None, fx=k, fy=k, interpolation=cv2.INTER_AREA)


def convert(path, outdir=None, title=None, delete=False, verify_on=False):
    from . import pipeline, photopage, score, verify, upload as UP
    t0 = time.time()
    stem = os.path.splitext(os.path.basename(path))[0]
    title = title or "v3_" + stem
    outdir = outdir or os.path.join("runs", "convert", stem)
    os.makedirs(outdir, exist_ok=True)
    kind = detect(path)
    if kind == "pdf_vector":
        spec = pipeline.run_pdf_page(path, debug_dir=outdir)
    elif kind == "pdf_scan":
        img = _render_scan(path, outdir, stem)
        spec = photopage.run_page(os.path.join(outdir, stem + "_300dpi.png"), debug_dir=outdir, source_path=path, img0=img, kind="pdf_scan")
    else:
        spec = photopage.run_page(path, debug_dir=outdir)
    spec["source"]["kind"] = kind
    t_spec = time.time() - t0
    spec_path = os.path.join(outdir, title + ".json")
    json.dump(spec, open(spec_path, "w"), ensure_ascii=False, indent=1)
    if verify_on:
        res = verify.main(spec_path, outdir, delete)
    else:   # 업로드 1회(create)만. 시트 PDF 내보내기/겹쳐 채점 없음
        r = UP.upload(spec, title)
        if not r.get("ok"):
            raise SystemExit("upload failed: %s" % r)
        res = {"url": r.get("url"), "id": r.get("id")}
        if delete:
            UP.call("delete", id=r["id"])
    summ = {"input": path, "kind": kind, "title": title, "url": res.get("url"), "sec_spec": round(t_spec, 1),
            "sec_total": round(time.time() - t0, 1), "spec": spec_path,
            "sheet_pdf": os.path.join(outdir, title + "_sheet.pdf"), "side_png": os.path.join(outdir, title + "_side.png"),
            "deleted": bool(delete), "verified": bool(verify_on),
            "sec_upload": round(time.time() - t0 - t_spec, 1), "vlm": spec.get("meta", {}).get("vlm"),
            "calls": spec.get("meta", {}).get("calls")}
    gtp = os.path.join(os.path.dirname(os.path.abspath(path)), "gt_content.json")
    if verify_on and kind == "photo" and os.path.exists(gtp):
        c = score.content_score(spec, json.load(open(gtp)), stem)
        if "cells_total" in c:
            summ["cells_ok"], summ["cells_total"] = c["cells_ok"], c["cells_total"]
            summ["cell_acc"] = round(100 * c["acc"], 1)
            summ["content_wrong"] = c.get("wrong", [])[:6]
        summ["block_text_ok"] = c.get("block_ok")
    keys = ("text_ratio", "text_found_pct", "line_median_mm", "line_max_mm", "median_mm", "max_mm", "text_center_err_mm",
            "table_center_err_mm", "text_size_err_pt", "block_center_err_mm", "bold_match_pct", "bold_orig_count",
            "bold_spec_count", "bold_spec_vs_orig_pct", "ink_iou_dilated", "ink_recall_dilated", "note")
    summ["metrics"] = {k: res[k] for k in keys if k in res}
    json.dump(summ, open(os.path.join(outdir, "convert.json"), "w"), ensure_ascii=False, indent=1)
    print("== %s [%s] %.1fs" % (title, kind, summ["sec_total"]))
    print("URL:", summ["url"])
    for k, v in summ["metrics"].items():
        print("  %s: %s" % (k, v))
    for k in ("cell_acc", "cells_ok", "cells_total", "content_wrong", "block_text_ok"):
        if k in summ:
            print("  %s: %s" % (k, summ[k]))
    if verify_on:
        print("  side:", summ["side_png"])
    print("  sec_spec: %s sec_upload: %s vlm: %s" % (summ["sec_spec"], summ["sec_upload"], summ["vlm"]))
    return summ
