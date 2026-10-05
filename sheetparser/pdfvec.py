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


# ---------------------------------------------------------------- v2: 페이지 전체
import base64


def _rgb_hex(c):
    if isinstance(c, int):
        return "#%06x" % c
    return "#%02x%02x%02x" % tuple(int(round(v * 255)) for v in c)


def text_lines(page):
    """rawdict -> 줄 목록. 각 줄: spans, chars(공백 포함 [(ch, x0, x1, size, bold, color)]), bbox, origin_y."""
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            chars, sizes = [], []
            y0, y1 = 1e9, -1e9
            oy = None
            for sp in l["spans"]:
                f = sp["font"].lower()
                bold = bool(sp["flags"] & 16) or "bold" in f
                for ch in sp["chars"]:
                    chars.append((ch["c"], ch["bbox"][0], ch["bbox"][2], sp["size"], bold, sp["color"], sp["font"]))
                if any(c["c"].strip() for c in sp["chars"]):
                    y0, y1 = min(y0, sp["bbox"][1]), max(y1, sp["bbox"][3])
                    oy = sp["origin"][1] if oy is None else oy
            if not any(c[0].strip() for c in chars):
                continue
            out.append({"chars": chars, "y0": y0, "y1": y1, "oy": oy})
    return out


def _seg(chars, y0, y1, oy):
    ink = [c for c in chars if c[0].strip()]
    txt = "".join(c[0] for c in chars).strip()
    nb = sum(c[4] for c in ink)
    fonts = {}
    for c in ink:
        fonts[c[6]] = fonts.get(c[6], 0) + 1
    col = max(set(c[5] for c in ink), key=lambda k: sum(1 for c in ink if c[5] == k))
    return {"text": txt, "x0": min(c[1] for c in ink), "x1": max(c[2] for c in ink), "y0": y0, "y1": y1, "oy": oy,
            "size": max(c[3] for c in ink), "bold": nb * 2 > len(ink), "color": _rgb_hex(col),
            "fonts": fonts}


def split_segments(line, min_spaces=3):
    """한 줄을 공백 3개 이상(또는 큰 간격)에서 나눈다."""
    segs, cur, sp = [], [], 0
    for c in line["chars"]:
        if c[0] == " ":
            sp += 1
            cur.append(c)
            continue
        if cur and sp >= min_spaces:
            seg = [x for x in cur]
            while seg and seg[-1][0] == " ":
                seg.pop()
            if any(x[0].strip() for x in seg):
                segs.append(_seg(seg, line["y0"], line["y1"], line["oy"]))
            cur = []
        sp = 0
        cur.append(c)
    if any(x[0].strip() for x in cur):
        segs.append(_seg(cur, line["y0"], line["y1"], line["oy"]))
    return segs


def whole_line(line):
    return _seg(line["chars"], line["y0"], line["y1"], line["oy"])


def underline_segs(page, lines):
    """텍스트 아래에 그려진 단일 가로선 -> 밑줄. 반환: (밑줄 드로잉 id 집합, [(x0,x1,y)])"""
    ids, ul = set(), []
    for i, d in enumerate(page.get_drawings()):
        if d.get("color") is None or len(d["items"]) != 1 or d["items"][0][0] != "l":
            continue
        p, q = d["items"][0][1], d["items"][0][2]
        if abs(p.y - q.y) > 0.5:
            continue
        x0, x1, y = min(p.x, q.x), max(p.x, q.x), p.y
        for l in lines:
            h = l["y1"] - l["y0"]
            lx0 = min(c[1] for c in l["chars"] if c[0].strip())
            lx1 = max(c[2] for c in l["chars"] if c[0].strip())
            if l["y0"] + 0.6 * h <= y <= l["y1"] + 1.5 and x1 > lx0 - 1 and x0 < lx1 + 1:
                ids.add(i)
                ul.append((x0, x1, y))
                break
    return ids, ul


def is_underlined(seg, ul):
    cov = 0.0
    for x0, x1, y in ul:
        if seg["y0"] + 0.6 * (seg["y1"] - seg["y0"]) <= y <= seg["y1"] + 1.5:
            cov += max(0, min(x1, seg["x1"]) - max(x0, seg["x0"]))
    return cov >= 0.6 * (seg["x1"] - seg["x0"])


def mask_v2(page, skip_ids, ppm=MASK_PPM):
    """vec_mask 와 같되 밑줄 드로잉은 제외."""
    s = ppm * PT_MM
    W, H = int(round(page.rect.width * s)), int(round(page.rect.height * s))
    m = np.zeros((H, W), np.uint8)
    P = lambda p: (int(round(p.x * s)), int(round(p.y * s)))
    for i, d in enumerate(page.get_drawings()):
        if i in skip_ids:
            continue
        w = d.get("width") or 0
        stroke, fill = d.get("color"), d.get("fill")
        th = max(1, int(round(w * s)) - 2)
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


def fills(page):
    """흰색이 아닌 채움: [(x0,y0,x1,y1,hex)]"""
    out = []
    for d in page.get_drawings():
        f = d.get("fill")
        if f is None or min(f) > 0.985 or d.get("color") is not None:
            continue
        r = d["rect"]
        out.append((r.x0, r.y0, r.x1, r.y1, _rgb_hex(f)))
    return out


def images(page):
    """[{bbox(pt), png_b64}] smask 있으면 투명 PNG."""
    doc = page.parent
    out = []
    for info in page.get_image_info(xrefs=True):
        xref = info.get("xref")
        if not xref:
            continue
        pix = fitz.Pixmap(doc, xref)
        try:
            sm = doc.xref_get_key(xref, "SMask")
            if sm[0] == "xref":
                mxref = int(sm[1].split()[0])
                mask = fitz.Pixmap(doc, mxref)
                if pix.colorspace.n != 3 or pix.alpha:
                    pix = fitz.Pixmap(fitz.csRGB, pix)
                pix = fitz.Pixmap(pix, mask)
            elif pix.colorspace is not None and pix.colorspace.n != 3:
                pix = fitz.Pixmap(fitz.csRGB, pix)
        except Exception:
            pass
        out.append({"bbox": list(info["bbox"]), "png_b64": base64.b64encode(pix.tobytes("png")).decode()})
    return out
