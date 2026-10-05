"""5라운드: OCR 백엔드별 정확도/시간 실측 (업로드 없음).
  python tools/r5.py <backend> <out_dir> [photos|forms|scan|all]
backend: paddle | qwen8b | qwen32b | hybrid. 서버 주소는 환경변수 VLM_URL / VLM8_URL / PADDLE_URL."""
import json
import os
import sys
import time

sys.path.insert(0, ".")
import cv2
from sheetparser import ocr as OCR, photopage, score

backend, out = sys.argv[1], sys.argv[2]
what = sys.argv[3] if len(sys.argv) > 3 else "all"
OCR.set_backend(backend)
os.makedirs(out, exist_ok=True)
gt = json.load(open("data/photos/gt_content.json"))
res = {}


def run(name, path, **kw):
    t = time.time()
    OCR.PADDLE_STATS.update({"calls": 0, "sec": 0.0, "suspect": 0, "requery": 0})
    sp = photopage.run_page(path, **kw)
    sec = time.time() - t
    json.dump(sp, open(os.path.join(out, name + ".json"), "w"), ensure_ascii=False)
    return sp, round(sec, 1)


if what in ("photos", "all"):
    for n in ("sched_09", "sched_10", "sched_11", "sched_12"):
        sp, sec = run(n, "data/photos/%s.jpg" % n)
        c = score.content_score(sp, gt, n)
        m = sp["meta"]
        res[n] = {"ok": c["cells_ok"], "total": c["cells_total"], "wrong": c["wrong"], "sec": sec, "ocr_sec": m.get("sec_table_ocr"),
                  "blocks": m.get("sec_blocks"), "vlm": m.get("vlm"), "paddle": dict(OCR.PADDLE_STATS), "hybrid_changed": m.get("hybrid_changed")}
        print(n, json.dumps(res[n], ensure_ascii=False), flush=True)
if what in ("forms", "all"):
    for n in ("form_activity", "form_attendance", "form_meal"):
        sp, sec = run(n, "data/photos/%s.jpg" % n)
        c = score.content_score(sp, gt, n)
        res[n] = {"head_ok": c["cells_ok"], "head_total": c["cells_total"], "wrong": c["wrong"], "block_ok": c.get("block_ok"), "block_missing": c.get("block_missing")}
        res[n].update({"sec": sec, "ocr_sec": sp["meta"].get("sec_table_ocr"), "paddle": dict(OCR.PADDLE_STATS)})
        print(n, json.dumps(res[n], ensure_ascii=False), flush=True)
if what in ("scan", "all"):
    from sheetparser import convert
    img = convert._render_scan('data/pdfs/scan_attendance_09.pdf', out, 'scan')
    sp, sec = run("scan", None, img0=img, kind="pdf_scan", source_path="scan_attendance_09.pdf")
    json.dump(sp, open(os.path.join(out, "scan.json"), "w"), ensure_ascii=False)
    res["scan"] = {"sec": sec, "ocr_sec": sp["meta"].get("sec_table_ocr"), "paddle": dict(OCR.PADDLE_STATS)}
    print("scan", json.dumps(res["scan"]), flush=True)
json.dump(res, open(os.path.join(out, "r5_%s.json" % backend), "w"), ensure_ascii=False, indent=1)
print("DONE")
