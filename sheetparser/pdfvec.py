"""PDF 벡터: drawings -> 선 마스크(20px/mm), 렌더링 이미지(10px/mm), span -> 셀 텍스트."""
import cv2
import fitz
import numpy as np

MASK_PPM = 20
PT_MM = 25.4 / 72


def is_vector(page):
    return len(page.get_drawings()) >= 4 and len(page.get_text("words")) >= 1


def vec_mask(page, ppm=MASK_PPM):
    s = ppm * PT_MM
    W, H = int(round(page.rect.width * s)), int(round(page.rect.height * s))
    m = np.zeros((H, W), np.uint8)
    P = lambda p: (int(round(p.x * s)), int(round(p.y * s)))
    for d in page.get_drawings():
        w = d.get("width") or 0
        stroke, fill = d.get("color"), d.get("fill")
        th = max(1, int(round(w * s)) - 2)  # cv2 선은 지정값보다 ~2px 굵게 그려짐
        for it in d["items"]:
            if it[0] == "l" and stroke is not None:
                cv2.line(m, P(it[1]), P(it[2]), 255, th)
            elif it[0] == "re":
                r = it[1]
                if stroke is not None:
                    cv2.rectangle(m, P(r.tl), P(r.br), 255, th)
                elif fill is not None and min(r.width, r.height) * PT_MM < 1.2:
                    cv2.rectangle(m, P(r.tl), P(r.br), 255, -1)
    return m


def render(page, ppm=10):
    s = ppm * PT_MM
    pix = page.get_pixmap(matrix=fitz.Matrix(s, s), colorspace=fitz.csRGB, alpha=False)
    a = np.frombuffer(pix.samples, np.uint8).reshape(pix.h, pix.w, 3)
    return cv2.cvtColor(a, cv2.COLOR_RGB2BGR)


def spans(page):
    out = []
    for b in page.get_text("dict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                if not sp["text"].strip():
                    continue
                bold = bool(sp["flags"] & 16) or "bold" in sp["font"].lower() or sp["font"].lower().endswith("b")
                out.append({"text": sp["text"], "bbox": sp["bbox"], "size": sp["size"], "bold": bold,
                            "origin": sp["origin"]})
    return out
