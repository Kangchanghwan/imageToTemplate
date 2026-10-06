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


# ---- v2: 표 전체 1회 호출 ----
# 호출 통계 (장당 합계: 호출 수, 프롬프트/생성 토큰, 초). photopage.run_page 가 시작할 때 reset 한다.
STATS = {"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "sec": 0.0, "bad_rows": 0, "trunc": 0, "retry": 0, "split": 0, "trunc_final": 0}
CALL_LOG = []   # 호출마다 [이미지 h, w, prompt_tokens, completion_tokens, 한도, finish_reason] (이미지 토큰 추정식 보정용)
CTX = 8192      # 32B 서버 -c (설정 변경 금지)
CTX_FRAC = 0.9


def stats_reset():
    STATS.update({"calls": 0, "prompt_tokens": 0, "completion_tokens": 0, "sec": 0.0, "bad_rows": 0, "trunc": 0, "retry": 0, "split": 0, "trunc_final": 0})
    del CALL_LOG[:]


class Overflow(Exception):
    """32B 요청이 출력 한도에서 잘렸거나(truncated), 컨텍스트에 안 들어갈 것 같아 보내지 않았다(too_big). 호출자는 행을 나눠 다시 보낸다."""
    def __init__(self, kind, partial=None):
        super().__init__(kind)
        self.kind, self.partial = kind, partial


IMG_TOK_DIV = 32.0   # Qwen3-VL: 이미지 토큰 = (h/32) x (w/32) (+ 특수 토큰). tools/ 실측 보정은 docs/RESULTS.md 7라운드
IMG_TOK_ADD = 8


def img_tokens(h, w):
    return int(((h + IMG_TOK_DIV - 1) // IMG_TOK_DIV) * ((w + IMG_TOK_DIV - 1) // IMG_TOK_DIV)) + IMG_TOK_ADD


def fits(shape, prompt, limit):
    """(이미지 예상 토큰 + 프롬프트 + 출력 한도) <= 8192 x 0.9 이면 True. 프롬프트는 한글 1글자 약 1토큰으로 어림."""
    return img_tokens(shape[0], shape[1]) + len(prompt) + 40 + limit <= CTX * CTX_FRAC


CELL_MAX = 160
# GBNF: 칸 내용 = '|' 와 줄바꿈과 '<' '>' (HTML/특수 토큰 조각), 이모지/딩뱃(U+2600-27BF, U+1F000-1FAFF)을 뺀 글자 0~160자
CELL = r"[^|\n<>\u2600-\u27bf\U0001f000-\U0001faff]{0,%d}" % CELL_MAX


def est_tokens(crop, per_char=1.3, margin=1.5, floor=8, cap=512):
    """칸 크롭의 CV 추정: 글줄 수와 잉크 폭(10px/mm 기준 px)으로 예상 글자 수 -> 출력 토큰 한도(여유 margin 배).
    글자 폭은 높이의 0.45배(숫자/기호까지 넉넉히 잡는 비관적 값), 줄 수는 행 투영 덩어리 수와 잉크 높이/(1.25 x 글자 높이) 중 큰 값."""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY) if crop.ndim == 3 else crop
    if g.size == 0:
        return floor
    bg = float(np.percentile(g, 80))
    m = ((bg - g) > 60).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    boxes = [st[i] for i in range(1, n) if st[i][4] >= 8 and st[i][3] >= 5]
    if not boxes:
        return floor
    x0 = min(b[0] for b in boxes); x1 = max(b[0] + b[2] for b in boxes)
    y0 = min(b[1] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    hs = np.array([b[3] for b in boxes], float)
    gh = max(float(np.percentile(hs, 80)), 6.0)
    rows = (m[y0:y1, x0:x1].sum(axis=1) > 0).astype(np.int8)
    runs = int(((rows[1:] == 1) & (rows[:-1] == 0)).sum() + rows[0])
    lines = max(runs, int(round((y1 - y0) / (1.25 * gh))), 1)
    chars = lines * (x1 - x0) / (0.45 * gh)
    return int(max(floor, min(cap, np.ceil(chars * per_char * margin))))


def _gbnf(lines):
    """lines: 줄마다 (고정 접두 문자열, 칸 수). 줄 수, 줄마다 구분자 개수, 행번호를 문법으로 강제한다."""
    rules = []
    for k, (prefix, n) in enumerate(lines):
        body = ('"%s" ' % prefix if prefix else "") + ' "|" '.join(["cell"] * n)
        # 마지막 줄의 줄바꿈은 선택: 모델이 줄바꿈 대신 종료 토큰으로 끝내려 할 때 문법이 막으면 잔글자(</tool_call> 조각, 되풀이)를 지어낸다
        rules.append("l%d ::= %s %s" % (k, body, "\"\\n\"?" if k == len(lines) - 1 else "\"\\n\""))
    root = "root ::= " + " ".join("l%d" % k for k in range(len(lines)))
    return root + "\n" + "\n".join(rules) + "\ncell ::= " + CELL + "\n"


def _ask(img, prompt, grammar, max_tokens, strict=True):
    """압축 출력(grammar 로 형식 강제). 반환: 응답 텍스트 또는 None. 사용량은 STATS 에 누적.
    컨텍스트에 안 들어가면 보내지 않고, 출력이 한도에서 잘리면(finish_reason=length) strict 일 때 Overflow 를 던진다."""
    if not fits(img.shape, prompt, max_tokens):
        raise Overflow("too_big")
    body = {"model": MODEL, "temperature": 0, "max_tokens": max_tokens, "grammar": grammar,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _png(img)}},
                {"type": "text", "text": prompt}]}]}
    req = urllib.request.Request(URL, data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    for k in range(3):  # vlm 이 재시작 중일 수 있어 간격을 두고 재시도 (서버는 건드리지 않는다)
        try:
            t0 = time.time()
            r = json.load(urllib.request.urlopen(req, timeout=300))
            u = r.get("usage", {})
            STATS["calls"] += 1
            STATS["prompt_tokens"] += u.get("prompt_tokens", 0)
            STATS["completion_tokens"] += u.get("completion_tokens", 0)
            STATS["sec"] += time.time() - t0
            fin = r["choices"][0].get("finish_reason")
            CALL_LOG.append([int(img.shape[0]), int(img.shape[1]), u.get("prompt_tokens", 0), u.get("completion_tokens", 0), max_tokens, fin])
            txt = r["choices"][0]["message"]["content"]
            if fin == "length":
                STATS["trunc"] += 1
                if strict:
                    raise Overflow("truncated", txt)
            return txt
        except Overflow:
            raise
        except Exception:
            time.sleep(20)
    return None


def _ask_retry(img, prompt, grammar, max_tokens):
    """단일 칸/줄 호출: 잘리면 한도를 2배로 1회 재요청(컨텍스트가 허용하는 만큼). 그래도 잘리면 잘린 글자를 그대로 쓰고 trunc_final 에 센다."""
    try:
        return _ask(img, prompt, grammar, max_tokens)
    except Overflow as e:
        if e.kind == "too_big":
            return None
        STATS["retry"] += 1
        try:
            return _ask(img, prompt, grammar, max_tokens * 2)
        except Overflow as e2:
            STATS["trunc_final"] += 1
            return e2.partial if e2.partial is not None else e.partial


def _lines(txt):
    return None if txt is None else txt.rstrip("\n").split("\n")


def read_table(img, bbox, R, C, col_w, merges, header_rows=1, ink=None, part=None, est=None, mul=1.0):
    """보정된 표 이미지를 1회 보내 R x C 배열을 받는다. ink=[(r,c)] 잉크 있는 칸(0 기준)만 요청하고 완전히 빈 행은 요청하지 않는다.
    출력은 한 줄에 한 행 `행번호|칸|칸..` (요청 칸 순서). 반환 (R x C 문자열 리스트, 어긋난 행 집합) 또는 None."""
    H, W = img.shape[:2]
    m = 12
    x0, y0, x1, y1 = bbox
    crop = _pad43(img[max(int(y0) - m, 0):min(int(y1) + m, H), max(int(x0) - m, 0):min(int(x1) + m, W)])
    tot = float(sum(col_w))
    ratio = ",".join("%d" % round(100 * w / tot) for w in col_w)
    if ink is None:
        ink = [(r, c) for r in range(R) for c in range(C)]
    byrow = {}
    for r, c in sorted(ink):
        byrow.setdefault(r, []).append(c)
    rows = sorted(byrow)
    mat = [[""] * C for _ in range(R)]
    if not rows:
        return mat, set()
    want = "\n".join("%d: %s" % (r + 1, ",".join(str(c + 1) for c in byrow[r])) for r in rows)
    ptxt = " 큰 표의 일부(전체 %d행 중 %d~%d행), 행 번호는 이 이미지 기준." % part if part else ""
    prompt = ("표 사진이다.%s %d행 x %d열, 열 너비 비율(%%) %s. 아래는 '행번호: 글자가 있는 열번호' 목록이다.\n%s\n"
              "각 행을 한 줄로, `행번호|글자|글자` 형식으로 목록의 열 순서대로 보이는 그대로 적어라. 칸 안에서 줄이 바뀌면 공백 하나로 잇는다. "
              "병합된 칸은 목록의 열 하나에 해당한다. 비쳐 보이는 뒷면 글자와 표 바깥 글자는 무시한다." % (ptxt, R, C, ratio, want))
    gram = _gbnf([("%d|" % (r + 1), len(byrow[r])) for r in rows])
    # 출력 한도: 칸별 예상 토큰(est) 합 + 행번호/구분자 여유. est 가 없으면 예전 값. 잘리거나 컨텍스트 초과면 Overflow (호출자가 행을 나눈다)
    lim = int(mul * (200 + 25 * len(ink))) if not est else int(mul * (40 + 6 * len(rows) + sum(est.get(rc, 24) + 3 for rc in ink)))
    txt = _ask(crop, prompt, gram, lim)
    ls = _lines(txt)
    if ls is None:
        return None
    bad = set()
    for k, r in enumerate(rows):
        parts = ls[k].split("|") if k < len(ls) else []
        if len(parts) != len(byrow[r]) + 1 or parts[0] != str(r + 1):   # 문법이 막아 주지만 방어: 개수가 안 맞으면 그 행만 재질의
            bad.add(r)
            STATS["bad_rows"] += 1
            continue
        for c, t in zip(byrow[r], parts[1:]):
            mat[r][c] = t.strip()
    return mat, bad


def read_neighbors(img, rects, target, est=None):
    """이웃 칸을 포함한 크롭 재질의. rects: 가로로 이어진 칸 사각형 목록(px), target: 읽을 칸 인덱스. 대상 칸 글자만 한 줄로 받는다."""
    H, W = img.shape[:2]
    x0 = max(int(min(r[0] for r in rects)) - 2, 0); x1 = min(int(max(r[2] for r in rects)) + 2, W)
    y0 = max(int(min(r[1] for r in rects)) - 2, 0); y1 = min(int(max(r[3] for r in rects)) + 2, H)
    n = len(rects)
    prompt = "표의 한 줄을 잘라낸 이미지다. 가로로 칸이 %d개 있다. 왼쪽에서 %d번째 칸의 글자만 보이는 그대로 한 줄로 적어라. 글자가 없으면 빈 줄. 비친 뒷면 글자는 무시한다." % (n, target + 1)
    txt = _ask_retry(_pad43(img[y0:y1, x0:x1]), prompt, _gbnf([("", 1)]), max(120, est or 0))
    return None if txt is None else txt.strip("\n").strip()


def read_line(img, bbox, band=None, est=None):
    """표 밖 텍스트 한 줄 읽기. 위아래/좌우에 여유 영역을 두어 가장자리 글자가 잘리지 않게 하고(축소 없음),
    클립 같은 물체가 글자를 가려도 보이지 않는 글자를 지어내지 않도록 지시한다."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    mx, my = 70, 30
    ya, yb = (band if band else (int(y0) - my, int(y1) + my))   # band: 이웃 글줄 잉크가 섞이지 않도록 이웃과의 중간선에서 자른 세로 범위
    crop = _pad43(img[max(int(ya), 0):min(int(yb), H), max(int(x0) - mx, 0):min(int(x1) + mx, W)])
    prompt = ("이미지 가운데 한 줄의 글자만 보이는 그대로 한 줄로 적어라(주변 선이나 물체는 무시). 클립 같은 물체가 글자 위를 지나가도 "
              "일부 획이 보이면 읽고, 전혀 안 보이는 글자는 지어내지 않는다. 괄호 안 빈칸은 공백. 글자가 없으면 빈 줄.")
    txt = _ask_retry(crop, prompt, _gbnf([("", 1)]), max(120, est or 0))
    return None if txt is None else txt.strip("\n")


def read_row(img, bbox, widths, want=None, est=None):
    """표 한 행 크롭에서 칸을 읽는다. widths: 칸 너비(상대값), want: 글자가 있는 칸 인덱스(0 기준, 기본 전부).
    출력은 `글자|글자` 한 줄. 반환: len(widths) 리스트(요청 안 한 칸은 "")."""
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    crop = _pad43(img[max(int(y0) - 3, 0):min(int(y1) + 3, H), max(int(x0) - 8, 0):min(int(x1) + 8, W)])
    n = len(widths)
    if want is None:
        want = list(range(n))
    tot = float(sum(widths))
    ratio = ",".join("%d" % round(100 * w / tot) for w in widths)
    prompt = ("표의 한 행 이미지다. 칸 %d개, 너비 비율(%%) %s. 글자가 있는 칸은 왼쪽에서 %s번째다. "
              "그 칸들의 글자만 왼쪽부터 `글자|글자` 형식 한 줄로 적어라. 칸 안 줄바꿈은 공백 하나. 비친 뒷면 글자는 무시한다."
              % (n, ratio, ",".join(str(i + 1) for i in want)))
    txt = _ask_retry(crop, prompt, _gbnf([("", len(want))]), (60 + 25 * len(want)) if not est else int(30 + sum(est)))
    ls = _lines(txt)
    if not ls or len(ls[0].split("|")) != len(want):
        return None
    out = [""] * n
    for i, t in zip(want, ls[0].split("|")):
        out[i] = t.strip()
    return out


# ---- 5라운드: 백엔드 선택 (paddle | qwen8b | qwen32b | hybrid) ----
BACKEND = os.environ.get("OCR_BACKEND", "auto")
URLS = {"qwen32b": os.environ.get("VLM_URL", "http://127.0.0.1:18001/v1/chat/completions"),
        "qwen8b": os.environ.get("VLM8_URL", "http://127.0.0.1:18002/v1/chat/completions"),
        "paddle": os.environ.get("PADDLE_URL", "http://127.0.0.1:18003/v1/chat/completions")}
PADDLE_STATS = {"calls": 0, "sec": 0.0, "suspect": 0, "requery": 0, "fail": 0, "empty": 0, "long": 0, "trunc": 0, "retry_ok": 0, "to32": 0, "max_prompt": 0, "max_out": 0}
PADDLE_MAX = 512


def paddle_reset():
    PADDLE_STATS.update({"calls": 0, "sec": 0.0, "suspect": 0, "requery": 0, "fail": 0, "empty": 0, "long": 0, "trunc": 0,
                         "retry_ok": 0, "to32": 0, "max_prompt": 0, "max_out": 0})
ACTIVE = BACKEND   # 이번 장에서 실제로 쓰는 백엔드 (auto 는 photopage.run_page 가 장마다 정한다)


def set_backend(name):
    """qwen8b 는 표 전체 호출 경로를 그대로 쓰되 서버 주소만 바꾼다. paddle 은 칸 단위 크롭 병렬 호출. hybrid 는 paddle + 의심 칸만 32B."""
    global BACKEND, URL, ACTIVE
    BACKEND = ACTIVE = name
    URL = URLS["qwen8b"] if name == "qwen8b" else URLS["qwen32b"]   # auto 의 32B 경로도 qwen32b 주소


def _paddle_one(crop, url=None, max_tokens=64, with_fin=False):
    """PaddleOCR-VL 에 "OCR:" 프롬프트로 크롭 1개. 반환 (텍스트, 최소 토큰 확률) (with_fin 이면 + finish_reason)."""
    h, w = crop.shape[:2]
    pd = int(os.environ.get("PADDLE_PAD", "0"))
    if pd:
        crop = cv2.copyMakeBorder(crop, pd, pd, pd, pd, cv2.BORDER_CONSTANT, value=[255, 255, 255])
    body = {"model": "paddle", "temperature": 0, "max_tokens": max_tokens, "logprobs": True,
            "messages": [{"role": "user", "content": [
                {"type": "image_url", "image_url": {"url": "data:image/png;base64," + _png(crop)}},
                {"type": "text", "text": "OCR:"}]}]}
    req = urllib.request.Request(url or URLS["paddle"], data=json.dumps(body).encode(), headers={"Content-Type": "application/json"})
    r = json.load(urllib.request.urlopen(req, timeout=120))
    ch = r["choices"][0]
    lp = [t["logprob"] for t in (ch.get("logprobs") or {}).get("content", []) if "logprob" in t]
    import math
    u = r.get("usage", {})
    PADDLE_STATS["max_prompt"] = max(PADDLE_STATS["max_prompt"], u.get("prompt_tokens", 0))
    PADDLE_STATS["max_out"] = max(PADDLE_STATS["max_out"], u.get("completion_tokens", 0))
    out = (" ".join(ch["message"]["content"].split()), (math.exp(min(lp)) if lp else 1.0))
    return out + (ch.get("finish_reason"),) if with_fin else out


def read_crop32(crop, limit):
    """칸/줄 크롭 1개를 32B 로 읽는다(paddle 이 두 번 잘렸을 때). 반환 텍스트 또는 None."""
    prompt = "이미지의 글자를 보이는 그대로 적어라. 줄이 바뀌면 공백 하나로 잇는다. 주변 선이나 물체는 무시한다. 글자가 없으면 빈 줄."
    txt = _ask_retry(_pad43(crop), prompt, _gbnf([("", 1)]), max(120, limit))
    return None if txt is None else " ".join(txt.split())


def paddle_read(crop, est=None):
    """paddle 1칸 읽기 + 잘림 처리. 한도는 CV 추정(칸 글줄 수 x 잉크 폭)으로 정한다(64~512).
    잘리면(finish_reason=length) 한도를 2배(최대 512)로 1회 재요청, 그래도 잘리면 그 칸만 32B. 반환 (텍스트, 최소 토큰 확률)."""
    mt = int(min(PADDLE_MAX, max(64, est if est is not None else est_tokens(crop))))
    t, p, fin = _paddle_one(crop, max_tokens=mt, with_fin=True)
    if fin != "length":
        return t, p
    PADDLE_STATS["trunc"] += 1
    if mt < PADDLE_MAX:
        t2, p2, fin2 = _paddle_one(crop, max_tokens=min(PADDLE_MAX, mt * 2), with_fin=True)
        if fin2 != "length":
            PADDLE_STATS["retry_ok"] += 1
            return t2, p2
    PADDLE_STATS["to32"] += 1
    t3 = read_crop32(crop, int(est_tokens(crop)))
    if t3:
        return t3, 1.0
    return t, p

def _ink_tight(crop, pad=14):
    """칸 크롭에서 진한 잉크 덩어리만 감싸는 사각형으로 조인다(옅은 비침/테두리 찌꺼기가 글자로 읽히는 것 방지)."""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    if g.size == 0:
        return crop
    bg = float(np.percentile(g, 80))
    m = ((bg - g) > 70).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    boxes = [st[i] for i in range(1, n) if st[i][4] >= 12 and st[i][3] >= 6]
    if not boxes:
        return crop
    x0 = min(b[0] for b in boxes); y0 = min(b[1] for b in boxes)
    x1 = max(b[0] + b[2] for b in boxes); y1 = max(b[1] + b[3] for b in boxes)
    H, W = g.shape
    return crop[max(y0 - pad, 0):min(y1 + pad, H), max(x0 - pad, 0):min(x1 + pad, W)]


def paddle_cells(img, cells, R, C, workers=int(os.environ.get("PADDLE_WORKERS", "4"))):
    """잉크 있는 칸마다 크롭해 병렬로 읽는다. 반환 (R x C 문자열 행렬, {(r,c): 최소 토큰 확률})."""
    from concurrent.futures import ThreadPoolExecutor
    H, W = img.shape[:2]
    todo = [c for c in cells if not c["_empty"]]

    def job(c):
        x0, y0, x1, y1 = [int(v) for v in c["_rect"]]
        crop = img[max(y0 + 3, 0):min(y1 - 3, H), max(x0 + 3, 0):min(x1 - 3, W)]
        crop = _ink_tight(crop)
        for k in range(2):
            try:
                return paddle_read(crop)
            except Exception:
                time.sleep(1)
        PADDLE_STATS["fail"] += 1
        return "", 0.0
    t0 = time.time()
    with ThreadPoolExecutor(workers) as ex:
        res = list(ex.map(job, todo))
    PADDLE_STATS["calls"] += len(todo)
    PADDLE_STATS["sec"] += time.time() - t0
    mat = [[""] * C for _ in range(R)]
    conf = {}
    for c, (t, p) in zip(todo, res):
        mat[c["r"]][c["c"]] = t
        conf[(c["r"], c["c"])] = p
        if not t:
            PADDLE_STATS["empty"] += 1
        elif len(t) > CELL_MAX:
            PADDLE_STATS["long"] += 1
    return mat, conf


def read_line_paddle(img, bbox, band=None):
    H, W = img.shape[:2]
    x0, y0, x1, y1 = bbox
    ya, yb = band if band else (int(y0) - 12, int(y1) + 12)   # band: 이웃 글줄과의 중간선으로 자른 세로 범위
    crop = img[max(int(ya), 0):min(int(yb), H), max(int(x0) - 20, 0):min(int(x1) + 20, W)]
    try:
        t, _ = paddle_read(crop)
        PADDLE_STATS["calls"] += 1
        return t
    except Exception:
        return ""


CONF_MIN = float(os.environ.get("HYBRID_CONF", "0.95"))


def hybrid_fix(img, cells, mat, pconf, xs_mm, C, meta):
    """paddle 결과 중 의심 칸(빈 글자, 낮은 토큰 확률)만 32B 에 이웃 포함 크롭으로 재질의."""
    PPM = 10
    n = 0
    for c in cells:
        if c["_empty"]:
            continue
        r, k = c["r"], c["c"]
        t = mat[r][k]
        if t and pconf.get((r, k), 0) >= CONF_MIN:
            continue
        PADDLE_STATS["suspect"] += 1
        cols = [j for j in (k - 1, k, k + 1) if 0 <= j < C]
        rects = [(xs_mm[j] * PPM, c["_rect"][1], xs_mm[j + 1] * PPM, c["_rect"][3]) for j in cols]
        a = read_neighbors(img, rects, cols.index(k))
        if a is not None:
            a = a.translate({ord(ch): None for ch in "\u2705\u2714\u2611"})
            if a.strip() and a.strip() != t:
                meta.setdefault("hybrid_changed", []).append([r, k, t, a.strip(), round(pconf.get((r, k), 0), 3)])
            mat[r][k] = a.strip() if a.strip() else t
        PADDLE_STATS["requery"] += 1
    return mat
