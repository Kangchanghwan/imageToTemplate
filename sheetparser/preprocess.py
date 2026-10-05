"""용지 검출 + 원근 보정 + 선 마스크."""
import cv2
import numpy as np

PPM = 10  # px/mm


def _order(pts):
    pts = np.array(pts, dtype=np.float32).reshape(4, 2)
    s = pts.sum(1)
    d = np.diff(pts, axis=1).ravel()
    return np.array([pts[np.argmin(s)], pts[np.argmin(d)], pts[np.argmax(s)], pts[np.argmax(d)]], np.float32)


def find_paper(img):
    h, w = img.shape[:2]
    sc = 1000.0 / max(h, w)
    small = cv2.resize(img, None, fx=sc, fy=sc, interpolation=cv2.INTER_AREA)
    g = cv2.GaussianBlur(cv2.cvtColor(small, cv2.COLOR_BGR2GRAY), (9, 9), 0)
    _, th = cv2.threshold(g, 0, 255, cv2.THRESH_BINARY + cv2.THRESH_OTSU)
    th = cv2.morphologyEx(th, cv2.MORPH_CLOSE, np.ones((15, 15), np.uint8))
    # 격자선/글자 구멍 메우기
    cnts, _ = cv2.findContours(th, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    if not cnts:
        return None
    c = max(cnts, key=cv2.contourArea)
    if cv2.contourArea(c) < 0.2 * small.shape[0] * small.shape[1]:
        return None
    hull = cv2.convexHull(c)
    quad = None
    peri = cv2.arcLength(hull, True)
    for eps in np.arange(0.01, 0.1, 0.005):
        ap = cv2.approxPolyDP(hull, eps * peri, True)
        if len(ap) == 4:
            quad = ap.reshape(4, 2)
            break
    if quad is None:
        quad = cv2.boxPoints(cv2.minAreaRect(hull))
    quad = _order(quad) / sc
    # 너무 이상한 사각형 / 사진 밖으로 잘림 검사
    m = 0.01 * max(h, w)
    touch = sum([(quad[:, 0] < m).any(), (quad[:, 0] > w - m).any(), (quad[:, 1] < m).any(), (quad[:, 1] > h - m).any()])
    return quad, touch


def rectify(img, force_fullframe=False):
    """반환: (보정 이미지, page_mm, flags, 변환 정보)"""
    flags = []
    res = None if force_fullframe else find_paper(img)
    if res is not None:
        quad, touch = res
        w_ = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
        h_ = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
        ratio = max(w_, h_) / max(1.0, min(w_, h_))
        if touch >= 3:
            flags.append({"reason": "paper_clipped"})
            res = None
        elif abs(ratio - 1.414) > 0.12:
            flags.append({"reason": "paper_not_a4_ratio:%.2f" % ratio})
            res = None
    if res is None:
        flags.append({"reason": "no_paper_assume_width_210mm"})
        h, w = img.shape[:2]
        s = 2100.0 / w
        out = cv2.resize(img, None, fx=s, fy=s, interpolation=cv2.INTER_AREA if s < 1 else cv2.INTER_CUBIC)
        return out, [210, round(out.shape[0] / PPM, 1)], flags
    w_ = (np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2
    h_ = (np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2
    if w_ > h_:
        W, H, pg = 2970, 2100, [297, 210]
        flags.append({"reason": "landscape_page"})
    else:
        W, H, pg = 2100, 2970, [210, 297]
    dst = np.array([[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]], np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    out = cv2.warpPerspective(img, M, (W, H), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    return out, pg, flags


def line_mask(img, ppm=PPM):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    bg = cv2.medianBlur(cv2.dilate(g, np.ones((5, 5), np.uint8)), 4 * ppm + 1)
    diff = cv2.subtract(bg, g)
    mask = (diff > 40).astype(np.uint8) * 255
    mg = int(1.5 * ppm)  # 용지 가장자리 제외
    mask[:mg] = 0; mask[-mg:] = 0; mask[:, :mg] = 0; mask[:, -mg:] = 0
    return mask


def table_rectify(img):
    """용지 외곽을 못 쓸 때: 가장 큰 선 덩어리(표)의 외곽 4점을 직사각형으로 편다.
    img는 이미 폭 2100px(=210mm 가정)로 스케일된 상태. 반환 (img2, origin_mm, ok)"""
    m = line_mask(img)
    comb = cv2.dilate(m, np.ones((5, 5), np.uint8))
    n, lab, st, _ = cv2.connectedComponentsWithStats(comb, connectivity=8)
    if n < 2:
        return img, None, False
    main = 1 + int(np.argmax(st[1:, cv2.CC_STAT_AREA]))
    ys, xs = np.nonzero(lab == main)
    pts = np.stack([xs, ys], 1).astype(np.int32)
    hull = cv2.convexHull(pts)
    peri = cv2.arcLength(hull, True)
    quad = None
    for eps in np.arange(0.01, 0.12, 0.005):
        ap = cv2.approxPolyDP(hull, eps * peri, True)
        if len(ap) == 4:
            quad = ap.reshape(4, 2)
            break
    if quad is None:
        quad = cv2.boxPoints(cv2.minAreaRect(hull))
    quad = _order(quad)
    W = int((np.linalg.norm(quad[1] - quad[0]) + np.linalg.norm(quad[2] - quad[3])) / 2)
    H = int((np.linalg.norm(quad[3] - quad[0]) + np.linalg.norm(quad[2] - quad[1])) / 2)
    pad = 60
    dst = np.array([[pad, pad], [pad + W, pad], [pad + W, pad + H], [pad, pad + H]], np.float32)
    M = cv2.getPerspectiveTransform(quad, dst)
    out = cv2.warpPerspective(img, M, (W + 2 * pad, H + 2 * pad), flags=cv2.INTER_CUBIC, borderValue=(255, 255, 255))
    return out, [round(float(quad[0][0]) / PPM, 1), round(float(quad[0][1]) / PPM, 1)], True
