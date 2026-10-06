"""2단계 대조용: 현행 Python 파이프라인(paddle 백엔드, 업로드 없음)의 최종 spec 과 OCR 입출력 기록.
사용(elgrim docker): python tools/parity/dump_spec_py.py <outdir> [이름...]
  <outdir>/spec_py/<name>.json   최종 spec (photopage.run_page(ocr=True), OCR_BACKEND=paddle 고정: auto 의 32B 폴백 없음)
  <outdir>/spec_py/<name>_ocr.json  paddle_cells 결과(r,c,text,conf), 블록 줄 읽기(순서대로), break_pass 줄 읽기((text, lines))
Python 소스는 바꾸지 않고 함수 래핑으로만 기록한다."""
import json
import os
import sys
import time

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("OCR_BACKEND", "paddle")
import cv2  # noqa: E402
from sheetparser import ocr as OCR, photopage as PPG  # noqa: E402
import dump_py  # noqa: E402

REC = {}


def wrap():
    o_pc, o_rl, o_cut = OCR.paddle_cells, OCR.read_line_paddle, PPG._cut

    def pc(img, cells, R, C, workers=4):
        mat, conf = o_pc(img, cells, R, C, workers)
        REC["cells"] = [[c["r"], c["c"], mat[c["r"]][c["c"]], conf.get((c["r"], c["c"]))] for c in cells if not c["_empty"]]
        return mat, conf

    def rl(img, bbox, band=None):
        t = o_rl(img, bbox, band)
        REC["blocks"].append({"bbox": [float(v) for v in bbox], "band": None if band is None else [float(v) for v in band], "text": t})
        return t

    def cut(text, lines):
        r = o_cut(text, lines)
        REC["breaks"].append({"text": text, "lines": lines[:-1], "result": r})
        return r
    OCR.paddle_cells, OCR.read_line_paddle, PPG._cut = pc, rl, cut


def main():
    outdir = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(os.path.join(outdir, "spec_py"), exist_ok=True)
    os.makedirs(os.path.join(outdir, "inputs"), exist_ok=True)
    wrap()
    for name, kind, path in dump_py.inputs():
        if only and name not in only:
            continue
        REC.clear(); REC.update({"cells": [], "blocks": [], "breaks": []})
        img0, ip = dump_py.load(kind, path, outdir, name)
        t0 = time.time()
        spec = PPG.run_page(path, ocr=True, source_path=path, img0=img0, kind=kind)
        sec = time.time() - t0
        spec["source"]["kind"] = kind
        json.dump(spec, open(os.path.join(outdir, "spec_py", name + ".json"), "w"), ensure_ascii=False)
        json.dump(dict(REC, sec=round(sec, 1)), open(os.path.join(outdir, "spec_py", name + "_ocr.json"), "w"), ensure_ascii=False)
        print(name, kind, "cells", len(spec["cells"]), "sec", round(sec, 1), spec["meta"].get("ocr_backend"), flush=True)


if __name__ == "__main__":
    main()
