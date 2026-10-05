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


# ---- v2: 표 전체 1회 호출 ----
def _pad43(img, bgr=(255, 255, 255), minside=64):
    """vlm 크래시 방지: 4:1 이내 + 짧은 변 minside 이상 (흰색 패딩만, 축소 없음)."""
    h, w = img.shape[:2]
    nh, nw = max(h, minside, (w + 3) // 4), max(w, minside, (h + 3) // 4)
    if (nh, nw) == (h, w):
        return img
    t, l = (nh - h) // 2, (nw - w) // 2
    return cv2.copyMakeBorder(img, t, nh - h - t, l, nw - w - l, cv2.BORDER_CONSTANT, value=[int(v) for v in bgr])


def _ask(img, prompt, schema, max_tokens, name="out"):
    body = {"model": MODEL, "temperature": 0, "max_tokens": max_tokens,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _png(img)}},
                {"type": "text", "text": prompt}]}],
            "response_format": {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for k in range(3):  # vlm 이 재시작 중일 수 있어 간격을 두고 재시도 (서버는 건드리지 않는다)
        try:
            r = json.load(urllib.request.urlopen(req, timeout=300))
            return json.loads(r["choices"][0]["message"]["content"])
        except Exception:
            time.sleep(20)
    return None


def read_table(img, bbox, R, C, col_w, merges, header_rows=1, ink=None, part=None):
    """보정된 표 이미지 전체를 1회 보내 R x C 배열을 받는다. 반환 R x C 문자열 리스트 또는 None.
    bbox=(x0,y0,x1,y1) px, col_w=열 너비 비율 리스트, merges=[(r,c,rs,cs)] (0 기준)"""
    H, W = img.shape[:2]
    m = 12
    x0, y0, x1, y1 = bbox
    crop = _pad43(img[max(int(y0) - m, 0):min(int(y1) + m, H), max(int(x0) - m, 0):min(int(x1) + m, W)])
    tot = float(sum(col_w))
    ratio = ", ".join("%d%%" % round(100 * w / tot) for w in col_w)
    mtxt = ""
    if merges:
        mtxt = " 병합된 칸: " + "; ".join("%d행%d열부터 %d행x%d열 크기" % (r + 1, c + 1, rs, cs) for r, c, rs, cs in merges) + "."
    extra = ""
    if part:
        extra += " 이 이미지는 더 큰 표의 일부(전체 %d행 중 %d행~%d행)이고 아래 행 번호는 이 이미지 기준이다." % part
    if ink is not None:
        extra += " 글자가 있는 칸(행,열)은 다음과 같다: %s. 다른 칸에 글자가 없으면 \"\" 로 둔다." % (
            ", ".join("(%d,%d)" % (r + 1, c + 1) for r, c in ink) if ink else "없음")
    prompt = ("사진으로 찍은 표 이미지다.%s 표는 정확히 %d행 x %d열이고 첫 %d행은 머리글이다. 열 너비 비율은 왼쪽부터 %s 이다.%s "
              "모든 칸의 글자를 위에서 아래, 왼쪽에서 오른쪽 순서로 cells[행][열] 이차원 배열에 보이는 그대로 적어라. "
              "빈 칸은 \"\" 로 둔다. 병합된 칸은 왼쪽 위 칸에만 쓰고 나머지 칸은 \"\" 로 둔다. "
              "한 칸 안에서 줄이 바뀌면 \\n 으로 잇는다. 종이 뒷면이 비쳐 흐릿하게 보이는 글자와 표 바깥 글자는 무시한다. "
              "JSON {\"cells\": [[...], ...]} 로만 답한다." % (extra, R, C, header_rows, ratio, mtxt))
    schema = {"type": "object", "properties": {"cells": {"type": "array", "minItems": R, "maxItems": R, "items": {
        "type": "array", "minItems": C, "maxItems": C, "items": {"type": "string"}}}}, "required": ["cells"]}
    o = _ask(crop, prompt, schema, 300 + 40 * R * C, "grid")
    if not o:
        return None
    return [[str(s).replace("\\n", "\n") for s in row] for row in o["cells"]]


def read_neighbors(img, rects, target):
    """이웃 칸을 포함한 크롭 재질의. rects: 가로로 이어진 칸 사각형 목록(px), target: 읽을 칸 인덱스."""
    H, W = img.shape[:2]
    x0 = max(int(min(r[0] for r in rects)) - 2, 0); x1 = min(int(max(r[2] for r in rects)) + 2, W)
    y0 = max(int(min(r[1] for r in rects)) - 2, 0); y1 = min(int(max(r[3] for r in rects)) + 2, H)
    n = len(rects)
    prompt = ("표의 한 줄을 잘라낸 이미지다. 가로로 칸이 정확히 %d개 있다. 왼쪽부터 각 칸의 글자를 보이는 그대로 적어라. "
              "빈 칸은 \"\". 흐릿하게 비친 뒷면 글자는 무시한다. JSON {\"cells\": [...]} 로만 답한다." % n)
    schema = {"type": "object", "properties": {"cells": {"type": "array", "minItems": n, "maxItems": n,
                                                          "items": {"type": "string"}}}, "required": ["cells"]}
    o = _ask(_pad43(img[y0:y1, x0:x1]), prompt, schema, 80 + 60 * n, "nb")
    if not o:
        return None
    return str(o["cells"][target]).replace("\\n", "\n")


def read_line(img, bbox):
    """표 밖 텍스트 한 줄 읽기."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    m = 14
    crop = _pad43(img[max(int(y0) - m, 0):min(int(y1) + m, H), max(int(x0) - m, 0):min(int(x1) + m, W)])
    prompt = ("한 줄의 글자가 있는 이미지다. 보이는 그대로 받아 적어라. 괄호 안 빈칸은 공백으로 둔다. "
              "글자가 없으면 \"\". JSON {\"text\": \"...\"} 로만 답한다.")
    schema = {"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]}
    o = _ask(crop, prompt, schema, 200, "line")
    return None if not o else str(o["text"])


def read_row(img, bbox, widths):
    """표 한 행 크롭을 보내 칸 n개를 읽는다. widths: 칸 너비(상대값)."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    crop = _pad43(img[max(int(y0) - 3, 0):min(int(y1) + 3, H), max(int(x0) - 8, 0):min(int(x1) + 8, W)])
    n = len(widths)
    tot = float(sum(widths))
    ratio = ", ".join("%d%%" % round(100 * w / tot) for w in widths)
    prompt = ("표의 한 행을 잘라낸 이미지다. 이 행에는 칸이 정확히 %d개 있고 너비 비율은 왼쪽부터 %s 이다. "
              "왼쪽부터 각 칸의 글자를 보이는 그대로 적어라. 빈 칸은 \"\". 한 칸 안에서 줄이 바뀌면 \\n 으로 잇는다. "
              "흐릿하게 비친 뒷면 글자는 무시한다. JSON {\"cells\": [...]} 로만 답한다." % (n, ratio))
    schema = {"type": "object", "properties": {"cells": {"type": "array", "minItems": n, "maxItems": n,
                                                          "items": {"type": "string"}}}, "required": ["cells"]}
    o = _ask(crop, prompt, schema, 100 + 60 * n, "row")
    if not o:
        return None
    return [str(s).replace("\\n", "\n") for s in o["cells"]]
