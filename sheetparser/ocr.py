"""elgrim vlm(OpenAI 호환)에 셀/행 크롭을 보내 글자 채우기."""
import base64
import json
import os
import time
import urllib.request

import cv2
import numpy as np

URL = os.environ.get("VLM_URL", "http://127.0.0.1:18001/v1/chat/completions")
MODEL = os.environ.get("VLM_MODEL", "vlm")


def _png(img):
    ok, buf = cv2.imencode(".png", img)
    return base64.b64encode(buf.tobytes()).decode()


def read_cells(crop, n, bgr=(255, 255, 255)):
    """크롭 안의 글자 칸 n개를 왼쪽→오른쪽 순서로 읽어 문자열 n개 반환."""
    h, w = crop.shape[:2]
    ph, pw = max(0, 64 - h, int(w / 4) - h), max(0, 64 - w, int(h / 4) - w)  # vlm 크래시 방지: 4:1 이내, 짧은 변 64px 이상 (패딩만)
    if ph or pw:
        crop = cv2.copyMakeBorder(crop, ph // 2 + 8, ph - ph // 2 + 8, pw // 2 + 8, pw - pw // 2 + 8,
                                  cv2.BORDER_CONSTANT, value=[int(v) for v in bgr])
    prompt = ("표의 일부를 잘라낸 이미지다. 글자가 적힌 칸이 정확히 %d개 있다. 왼쪽에서 오른쪽, 위에서 아래 순서로 "
              "각 칸의 글자를 보이는 그대로 받아 적어라. 빈 칸은 건너뛴다. 한 칸 안에서 줄이 바뀌면 \\n 으로 잇는다. "
              "JSON {\"cells\": [...]} 로만 답한다." % n)
    schema = {"type": "object", "properties": {"cells": {"type": "array", "minItems": n, "maxItems": n,
                                                          "items": {"type": "string"}}},
              "required": ["cells"]}
    body = {"model": MODEL, "temperature": 0, "max_tokens": 80 + 60 * n,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _png(crop)}},
                {"type": "text", "text": prompt}]}],
            "response_format": {"type": "json_schema", "json_schema": {"name": "cells", "schema": schema}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=300))
    try:
        out = json.loads(r["choices"][0]["message"]["content"])["cells"]
        return [str(s).replace("\\n", "\n") for s in out]
    except Exception:
        return None


def fill_text(img, cells, ys, xs, px_per_mm_img=10):
    """cells: [{'r','c','rs','cs','_rect':(x0,y0,x1,y1),'_empty':bool,'_bgr':..}] 에 'text' 채움. 반환 meta."""
    t0 = time.time()
    calls = 0
    todo = [c for c in cells if not c["_empty"]]
    rows = {}
    singles = []
    for c in todo:
        singles.append(c)  # 셀 단위 호출 (행 단위는 가로 비율이 커서 vlm 크래시 유발)
    units = []
    for r, cs in []:
        cs.sort(key=lambda c: c["c"])
        x0 = min(c["_rect"][0] for c in cs); x1 = max(c["_rect"][2] for c in cs)
        y0 = min(c["_rect"][1] for c in cs); y1 = max(c["_rect"][3] for c in cs)
        units.append((cs, (x0, y0, x1, y1)))
    for c in singles:
        units.append(([c], c["_rect"]))
    H, W = img.shape[:2]
    for cs, (x0, y0, x1, y1) in units:
        x0, y0, x1, y1 = max(int(x0) - 2, 0), max(int(y0) - 2, 0), min(int(x1) + 2, W), min(int(y1) + 2, H)
        crop = img[y0:y1, x0:x1]
        bgr = cs[0].get("_bgr")
        bgr = (255, 255, 255) if bgr is None else bgr
        res = read_cells(crop, len(cs), bgr)
        calls += 1
        if res is None or len(res) != len(cs):
            for c in cs:
                c["text"] = ""
                c.setdefault("_flag", "low_ocr_conf")
            continue
        for c, t in zip(cs, res):
            c["text"] = t
    return {"calls": calls, "sec": round(time.time() - t0, 1)}
