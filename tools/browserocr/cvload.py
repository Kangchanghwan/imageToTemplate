"""서버가 격자 검출(CV)만 할 때(OCR 호출 없음)의 단독 시간과 동시 처리량. photopage.run_page(ocr=False).
  python tools/browserocr/cvload.py --n 8 --reqs 32 --tag cv8
결과: runs/bro/cvload_<tag>.json (load.py 와 같은 닫힌 루프, 프로세스 풀)"""
import argparse, glob, json, os, sys, time
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor
sys.path.insert(0, os.getcwd())
import cv2, numpy as np
from sheetparser import photopage, convert as CV, preprocess as PP

FILES = sorted(glob.glob("data/photos/*.jpg")) + ["data/pdfs/activity_09_300dpi.png"]
SCANS = ["data/pdfs/scan_attendance_09.pdf", "data/pdfs/scan_meal_09.pdf"]


def work(p):
    t = time.time()
    if p.endswith(".pdf"):
        os.makedirs("/tmp/cvl", exist_ok=True)
        img = CV._render_scan(p, "/tmp/cvl", os.path.basename(p)[:-4])
        sp = photopage.run_page("x.png", ocr=False, img0=img, kind="pdf_scan")
    else:
        sp = photopage.run_page(p, ocr=False)
    n = sum(1 for c in sp["cells"] if not c.get("_empty", False) and c.get("role", "table") == "table")
    return {"path": p, "lat": time.time() - t, "cells": len(sp["cells"])}


def pct(v, q):
    v = sorted(v); k = (len(v) - 1) * q; f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--n", type=int, default=1); ap.add_argument("--reqs", type=int, default=16)
    ap.add_argument("--tag", default="cv"); ap.add_argument("--scan", action="store_true"); a = ap.parse_args()
    files = SCANS if a.scan else FILES
    jobs = [files[i % len(files)] for i in range(a.reqs)]
    sys.stdout = open(os.devnull, "w") if False else sys.stdout
    with ProcessPoolExecutor(a.n, mp_context=mp.get_context("fork")) as ex:
        t0 = time.time(); res = list(ex.map(work, jobs)); wall = time.time() - t0
    lat = [r["lat"] for r in res]
    per = {}
    for r in res:
        per.setdefault(os.path.basename(r["path"]), []).append(r["lat"])
    out = {"n": a.n, "reqs": a.reqs, "wall": round(wall, 2), "per_min": round(60 * a.reqs / wall, 1), "p50": round(pct(lat, .5), 2),
           "p95": round(pct(lat, .95), 2), "max": round(max(lat), 2), "per_file_mean": {k: round(sum(v) / len(v), 2) for k, v in per.items()}}
    os.makedirs("runs/bro", exist_ok=True)
    json.dump(out, open("runs/bro/cvload_%s.json" % a.tag, "w"), ensure_ascii=False)
    print("CVLOAD", json.dumps(out, ensure_ascii=False))
