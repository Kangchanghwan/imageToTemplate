"""브라우저 OCR 대리 측정용 백엔드 (opt-in, 기존 코드는 안 바꾼다).
ocr.paddle_read 를 PP-OCRv5 kor rec(onnxruntime) 또는 Tesseract(kor)로 바꿔 끼운 뒤 convert 를 돈다.
  python tools/browserocr/backend.py <variant> <input> <outdir> <name>
variant: pp_whole | pp_split | pp_det | tess_best6 | tess_fast6 | tess_best7 | tess_fast7 (+접미사 2=표선 제거, c=표선 제거+2배 확대, f=det 빈 결과 시 rec 폴백, m=최소 폭 패딩(악화))
환경변수 BRO_MODELS(기본 /w/../bro 가 아니라 /bro/models), BRO_TESS(/bro/tess), BRO_LOG(칸 로그 jsonl), BRO_CROPS(칸 크롭 저장 폴더)
paddle 서버 폴백(auto)은 쓰지 않고 OCR.BACKEND='paddle' 로 고정해 순수 백엔드 결과만 얻는다."""
import json, math, os, subprocess, sys, tempfile, time
import cv2, numpy as np
sys.path.insert(0, ".")
from sheetparser import ocr as OCR

MD = os.environ.get("BRO_MODELS", "/bro/models")
TD = os.environ.get("BRO_TESS", "/bro/tess")
LOG = []
DETF = "det_v5.onnx"   # 변형 이름이 _mob 로 끝나면 det_mobile.onnx (PP-OCRv5_mobile_det -> paddle2onnx 변환본)
_S = {}


def sess(name):
    if name not in _S:
        import onnxruntime as ort
        so = ort.SessionOptions()
        so.intra_op_num_threads = int(os.environ.get("BRO_THREADS", "4"))
        so.inter_op_num_threads = 1
        _S[name] = ort.InferenceSession(os.path.join(MD, name), so, providers=["CPUExecutionProvider"])
    return _S[name]


_DICT = None


def dct():
    global _DICT
    if _DICT is None:
        _DICT = ["blank"] + [l.rstrip("\n") for l in open(os.path.join(MD, "dict_ko.txt"), encoding="utf-8")] + [" "]
    return _DICT


PREP = False   # 변형 이름이 2 로 끝나면 전처리(표선 잔재 제거 + 최소 폭 패딩) 사용


def clean_rules(crop):
    """칸 크롭에 남은 표선 잔재(긴 가로선/세로선)를 흰색으로 지운다. 가로 >= 50px, 세로 >= 45px(크롭 높이의 80% 이상)만."""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bg = float(np.percentile(g, 80))
    m = ((bg - g) > 50).astype(np.uint8)
    hz = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((1, 50), np.uint8))
    vl = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((max(45, int(0.8 * g.shape[0])), 1), np.uint8)) if g.shape[0] >= 45 else np.zeros_like(m)
    r = cv2.dilate(hz | vl, np.ones((3, 3), np.uint8))
    if not r.any():
        return crop
    out = crop.copy()
    out[r > 0] = (255, 255, 255)
    return out


def minwide(img, ratio=3.0):
    """너무 좁은 크롭(예: '4.0')은 CTC 프레임이 모자라 빈 결과가 나오므로 높이의 ratio 배까지 흰 패딩."""
    h, w = img.shape[:2]
    need = int(h * ratio) - w
    if need <= 0:
        return img
    return cv2.copyMakeBorder(img, 0, 0, need // 2, need - need // 2, cv2.BORDER_CONSTANT, value=(255, 255, 255))


def rec_line(img, h=48):
    """한 줄 크롭 -> (텍스트, 평균 확률)"""
    if PREP and img.shape[0] >= 2 and img.shape[1] >= 2:
        img = cv2.copyMakeBorder(minwide(img), 6, 6, 6, 6, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    ih, iw = img.shape[:2]
    if ih < 2 or iw < 2:
        return "", 0.0
    w = max(int(math.ceil(h * iw / ih)), 8)
    w = min(w, 3200)
    x = cv2.resize(img, (w, h), interpolation=cv2.INTER_LINEAR).astype(np.float32)
    x = (x / 255.0 - 0.5) / 0.5
    x = x.transpose(2, 0, 1)[None]
    s = sess("rec_ko.onnx")
    out = s.run(None, {s.get_inputs()[0].name: x})[0][0]   # T x K
    idx = out.argmax(1)
    pr = out.max(1)
    D = dct()
    txt, ps, prev = [], [], 0
    for i, p in zip(idx, pr):
        if i != 0 and i != prev:
            if i < len(D):
                txt.append(D[i]); ps.append(float(p))
        prev = i
    return "".join(txt), (sum(ps) / len(ps) if ps else 0.0)


def split_lines(crop):
    """CV 가로 투영으로 줄 분할 -> 줄 크롭 목록 (위 -> 아래)"""
    g = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    bg = float(np.percentile(g, 80))
    m = ((bg - g) > 50).astype(np.uint8)
    m = cv2.morphologyEx(m, cv2.MORPH_OPEN, np.ones((2, 2), np.uint8))
    rows = np.where(m.sum(1) > 0)[0]
    if len(rows) == 0:
        return [crop]
    runs, s, p = [], rows[0], rows[0]
    for r in rows[1:]:
        if r != p + 1:
            runs.append([s, p]); s = r
        p = r
    runs.append([s, p])
    mh = max(b - a + 1 for a, b in runs)
    mg = []
    for a, b in runs:
        if mg and a - mg[-1][1] - 1 < 0.25 * mh:
            mg[-1][1] = b
        else:
            mg.append([a, b])
    mg = [(a, b) for a, b in mg if b - a + 1 >= 3]
    H = crop.shape[0]
    pad = 4
    return [crop[max(a - pad, 0):min(b + pad + 1, H)] for a, b in mg] or [crop]


def det_boxes(crop):
    """PP-OCRv5 det(DB) -> (x0,y0,x1,y1) 목록. 후처리는 이진화 + 외접 사각형 + unclip 근사."""
    h, w = crop.shape[:2]
    sc = 1.0
    if min(h, w) < 64:
        sc = 64.0 / min(h, w)
    if max(h, w) * sc > 960:
        sc = 960.0 / max(h, w)
    nh, nw = max(32, int(round(h * sc / 32)) * 32), max(32, int(round(w * sc / 32)) * 32)
    x = cv2.resize(crop, (nw, nh)).astype(np.float32) / 255.0
    x = (x - np.array([0.485, 0.456, 0.406], np.float32)) / np.array([0.229, 0.224, 0.225], np.float32)
    s = sess(DETF)
    pm = s.run(None, {s.get_inputs()[0].name: x.transpose(2, 0, 1)[None]})[0][0, 0]
    b = (pm > 0.3).astype(np.uint8)
    cs, _ = cv2.findContours(b, cv2.RETR_LIST, cv2.CHAIN_APPROX_SIMPLE)
    out = []
    for c in cs:
        x0, y0, bw, bh = cv2.boundingRect(c)
        if bw < 3 or bh < 3 or pm[y0:y0 + bh, x0:x0 + bw].mean() < 0.5:
            continue
        d = int(round(bw * bh * 1.5 / (2 * (bw + bh))))
        a0, b0, a1, b1 = x0 - d, y0 - d, x0 + bw + d, y0 + bh + d
        out.append((max(int(a0 / nw * w), 0), max(int(b0 / nh * h), 0), min(int(a1 / nw * w), w), min(int(b1 / nh * h), h)))
    return out


def det_rec(crop):
    bx = det_boxes(crop)
    if not bx:
        return "", 0.0
    bx.sort(key=lambda b: (b[1] + b[3]) / 2)
    lines = []
    for b in bx:
        for L in lines:
            ly0, ly1 = L[0][1], L[0][3]
            ov = min(ly1, b[3]) - max(ly0, b[1])
            if ov > 0.5 * min(ly1 - ly0, b[3] - b[1]):
                L.append(b); break
        else:
            lines.append([b])
    txt, ps = [], []
    for L in sorted(lines, key=lambda L: L[0][1]):
        parts = []
        for b in sorted(L, key=lambda b: b[0]):
            t, p = rec_line(crop[b[1]:b[3], b[0]:b[2]])
            if t:
                parts.append(t); ps.append(p)
        txt.append(" ".join(parts))
    return " ".join(txt), (min(ps) if ps else 0.0)


def tess(img, best, psm):
    """tesseract CLI (Tesseract.js 와 같은 LSTM 엔진). 흰 테두리 10px."""
    img = cv2.copyMakeBorder(img, 10, 10, 10, 10, cv2.BORDER_CONSTANT, value=(255, 255, 255))
    d = os.path.join(TD, "best" if best else "fast")
    with tempfile.NamedTemporaryFile(suffix=".png") as f:
        cv2.imwrite(f.name, img)
        r = subprocess.run(["tesseract", f.name, "stdout", "--tessdata-dir", d, "-l", "kor", "--psm", str(psm)],
                           capture_output=True, text=True, env=dict(os.environ, OMP_THREAD_LIMIT="1"))
    return " ".join(r.stdout.split()), 1.0


def make_read(variant):
    def read(crop, est=None):
        t0 = time.time()
        if variant[-1] in "2cmf":
            crop = clean_rules(crop)
        if variant.startswith("pp_whole"):
            t, p = rec_line(crop)
        elif variant.startswith("pp_split"):
            ts, ps = [], []
            for L in split_lines(crop):
                t, p = rec_line(L); ts.append(t); ps.append(p)
            t, p = " ".join(x for x in ts if x), (min(ps) if ps else 0.0)
        elif variant.startswith("pp_det"):
            t, p = det_rec(crop)
            if not t and variant.endswith("f"):   # det 가 아무것도 못 찾은 칸(짧은 한 글자 등)은 칸 전체를 줄 분할 rec 로 다시 읽는다
                ts = [rec_line(L)[0] for L in split_lines(crop)]
                t = " ".join(x for x in ts if x)
        elif variant.startswith("tess"):
            best = "best" in variant
            if variant.endswith("c"):   # 표선 제거 + 2배 확대 (Tesseract 는 작은 글자에 약함)
                crop = cv2.resize(crop, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
            if "7" in variant:
                ts = [tess(L, best, 7)[0] for L in split_lines(crop)]
                t, p = " ".join(x for x in ts if x), 1.0
            else:
                t, p = tess(crop, best, 6)
        else:
            raise SystemExit("variant?")
        t = " ".join(t.split())
        LOG.append({"h": int(crop.shape[0]), "w": int(crop.shape[1]), "ms": round(1000 * (time.time() - t0), 1), "text": t})
        cd = os.environ.get("BRO_CROPS")
        if cd and variant == os.environ.get("BRO_CROPS_VARIANT", variant) and not os.environ.get("BRO_NOCROP"):
            os.makedirs(cd, exist_ok=True)
            cv2.imwrite(os.path.join(cd, "%03d.png" % (len(LOG) - 1)), crop)
        return t, p
    return read


def main():
    variant, inp, outdir, name = sys.argv[1:5]
    global PREP, DETF
    full = variant
    if variant.endswith("_mob"):
        DETF = "det_mobile.onnx"; variant = variant[:-4]
    PREP = variant.startswith("pp_") and variant.endswith("m")   # 시도1(최소 폭 패딩)은 악화돼 접미사 m 으로만 남김
    OCR.paddle_read = make_read(variant)
    OCR.BACKEND = "paddle"
    from sheetparser import convert
    t0 = time.time()
    convert.convert(inp, outdir, title=name, no_upload=True)
    tot = time.time() - t0
    json.dump({"variant": full, "input": inp, "total_s": round(tot, 2), "cells": LOG}, open(os.path.join(outdir, name + "_cells.json"), "w"), ensure_ascii=False)
    ms = [c["ms"] for c in LOG]
    print("BRO", full, name, "cells", len(ms), "ocr_ms_total", round(sum(ms)), "mean", round(sum(ms) / max(len(ms), 1), 1), "total_s", round(tot, 1))


if __name__ == "__main__":
    main()
