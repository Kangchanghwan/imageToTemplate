"""셀 단위 서식 분석: 배경색, 잉크 bbox, 정렬, 글자 크기, 굵기."""
import cv2
import numpy as np

PPM = 10


def style_name(info):
    """info=None | (두께mm, 이중선) -> SPEC 열거값"""
    if info is None:
        return "NONE"
    t, dbl = info
    if dbl:
        return "DOUBLE"
    if t < 0.35:
        return "SOLID"
    if t < 0.7:
        return "SOLID_MEDIUM"
    return "SOLID_THICK"


def _runs(mask1d, gap):
    idx = np.nonzero(mask1d)[0]
    if len(idx) == 0:
        return []
    out, s, p = [], idx[0], idx[0]
    for i in idx[1:]:
        if i - p > gap:
            out.append((s, p)); s = i
        p = i
    out.append((s, p))
    return out


def _line_bands(rows, y0, gap=4):
    """행 투영 -> 글줄 띠 [(ya, yb)] (절대 y). 틈 gap px 미만은 같은 줄, 가장 큰 띠 높이의 45% 미만 조각(점, 괄호 끝)은 이웃 줄에 붙인다."""
    runs = _runs(rows, gap - 1)
    if not runs:
        return []
    mh = max(b - a + 1 for a, b in runs)
    out = []
    for a, b in runs:
        if out and (b - a + 1) < 0.45 * mh:
            out[-1] = (out[-1][0], b)
        elif (b - a + 1) < 0.45 * mh and not out:
            out.append((a, b))
        else:
            out.append((a, b))
    if len(out) > 1 and (out[0][1] - out[0][0] + 1) < 0.45 * mh:   # 맨 앞 조각이 작으면 다음 줄에 붙인다
        out[1] = (out[0][0], out[1][1]); out = out[1:]
    return [(a + y0, b + y0) for a, b in out]


def hangul_thickness(g, inkmask=None):
    """한글 음절 크기(높이가 가장 큰 덩어리의 70% 이상, 너비/높이 0.75 이상)의 덩어리만 4배 확대해 획 두께(원 해상도 px)의 중앙값을 잰다.
    숫자/기호/괄호는 글꼴이 달라 두께가 다르게 나오므로 뺀다. 반환 (두께 px, 덩어리 수) 또는 None."""
    big = cv2.resize(g, None, fx=4, fy=4, interpolation=cv2.INTER_CUBIC).astype(np.float32)
    bg = np.percentile(big, 85); ink = np.percentile(big, 1.0)
    if bg - ink < 60:
        return None
    m = (big < (bg + ink) / 2).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(m, connectivity=8)
    if n < 2:
        return None
    ih = st[1:, 3].max()
    keep = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if h >= 0.7 * ih and w >= 0.75 * h and a > 40 and x > 0 and y > 0 and x + w < m.shape[1] and y + h < m.shape[0]:
            keep[i] = True
    if keep.sum() < 1:
        return None
    k = keep[lab].astype(np.uint8)
    dt = cv2.distanceTransform(k, cv2.DIST_L2, cv2.DIST_MASK_PRECISE)
    mx = cv2.dilate(dt, np.ones((3, 3), np.uint8))
    ridge = (dt >= mx - 1e-3) & (dt >= 2.0)
    if ridge.sum() < 10:
        return None
    return float(np.median(2 * dt[ridge] / 4.0)), int(keep.sum())


def analyze(img, gray, rect, inset=7):
    x0, y0, x1, y1 = [int(round(v)) for v in rect]
    x0 += inset; y0 += inset; x1 -= inset; y1 -= inset
    H, W = gray.shape
    x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, W), min(y1, H)
    res = {"empty": True, "bgr": None}
    if x1 - x0 < 8 or y1 - y0 < 8:
        return res
    g = gray[y0:y1, x0:x1]
    crop = img[y0:y1, x0:x1]
    med = float(np.median(g))
    res["med"] = med
    gf = g.astype(np.float32)
    res["uni"] = float(((np.abs(gf - med) <= 12) | (gf < med - 40)).mean())
    near = np.abs(g.astype(np.float32) - med) <= 20
    if near.sum() > 10:
        res["bgr"] = np.median(crop[near], axis=0)
    ink = (g < med - 55).astype(np.uint8)
    n, lab, st, _ = cv2.connectedComponentsWithStats(ink, connectivity=8)
    ch, cw = g.shape
    ok = np.zeros(n, bool)
    for i in range(1, n):
        x, y, w, h, a = st[i]
        if x == 0 or y == 0 or x + w >= cw or y + h >= ch or a < 4:
            continue
        # 긴 가로/세로 줄(어긋난 선 잔여)은 제외
        if (w > 0.9 * cw and h < 6) or (h > 0.9 * ch and w < 6):
            continue
        ok[i] = True
    keep = ok[lab]
    if keep.sum() < 15:
        return res
    ys, xs = np.nonzero(keep)
    res["empty"] = False
    gl, gr = xs.min(), cw - 1 - xs.max()
    gt, gb = ys.min(), ch - 1 - ys.max()
    d = gr - gl
    res["h"] = "CENTER" if abs(d) < 0.24 * cw else ("LEFT" if d > 0 else "RIGHT")
    d = gb - gt
    res["v"] = "MIDDLE" if abs(d) < 0.12 * ch else ("TOP" if d > 0 else "BOTTOM")
    rows = keep.any(1)
    runs = _runs(rows, 2)
    res["lbands"] = _line_bands(rows, y0)
    res["lbx"] = []
    for (ya, yb) in res["lbands"]:
        cols = np.nonzero(keep[ya - y0:yb - y0 + 1].any(0))[0]
        if len(cols):
            res["lbx"].append((int(cols.min()), int(cols.max())))
    res["gl"], res["gr"], res["cw"] = int(gl), int(gr), int(cw)
    res["fill"] = float((xs.max() - xs.min() + 1) / cw)
    res["hth"] = hangul_thickness(g, ink)
    hs = [b - a + 1 for a, b in runs]
    lh = float(np.median(hs)) if hs else 0
    res["nlines"] = len(runs)
    res["size_pt"] = round(lh / PPM * (72 / 25.4) / 0.85 * 2) / 2 if lh else 10
    cnts, _ = cv2.findContours(keep.astype(np.uint8), cv2.RETR_LIST, cv2.CHAIN_APPROX_NONE)
    per = sum(cv2.arcLength(c, True) for c in cnts)
    stroke = 2.0 * keep.sum() / per if per else 0
    res["bold"] = bool(lh and stroke / lh > 0.135)
    res["stroke_ratio"] = float(stroke / lh) if lh else 0
    res["ink_h"] = int(ys.max() - ys.min() + 1)
    res["ink_bbox"] = [int(xs.min() + x0), int(ys.min() + y0), int(xs.max() + x0), int(ys.max() + y0)]
    return res


HANGUL_RATIO, LATIN_RATIO, LEAD = 0.88, 0.72, 1.2


def size_from_ink(ink_h_px, text, ppm=PPM, nlines=None):
    """잉크 bbox 높이(px)와 글 내용(줄 수, 한글 포함 여부)으로 글자 크기(pt) 추정."""
    n = max(1, len((text or "").strip("\n").split("\n")), nlines or 1)   # nlines: 이미지에서 센 글줄 수(칸 안에서 자동 줄바꿈된 글은 text 에 개행이 없다)
    hangul = any("\uac00" <= ch <= "\ud7a3" for ch in text or "")
    ratio = HANGUL_RATIO if hangul else LATIN_RATIO
    em_mm = ink_h_px / ppm / (ratio + LEAD * (n - 1))
    return em_mm * 72 / 25.4


def unify_sizes(items, rel=0.12):
    """items: [{'size','col','row_kind'}] 형태가 아니라 호출부에서 열/행 최빈값을 적용한 뒤,
    페이지 전체 크기 단계 클러스터링: 정렬 후 인접 값이 rel 이내면 한 단계로 묶고 중앙값(0.5pt 반올림)을 쓴다."""
    vals = sorted(set(items))
    groups = []
    for v in vals:
        if groups and v <= groups[-1][-1] * (1 + rel):
            groups[-1].append(v)
        else:
            groups.append([v])
    m = {}
    for g in groups:
        c = round(float(np.median(g)) * 2) / 2
        for v in g:
            m[v] = c
    return m
