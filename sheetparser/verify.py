"""SPEC 7단계: 시트 업로드 -> A4 PDF -> 래스터화 -> 보정 원본과 격자선 위치 비교."""
import difflib
import json
import math
import os

import cv2
import fitz
import numpy as np

from . import grid as G, pdfvec as PV, preprocess as PP, upload as UP, pipeline as PL


def _grid_of_image(img):
    return G.build_grid(PP.line_mask(img), PP.PPM)


def main_v1(spec_path, outdir):
    spec = json.load(open(spec_path))
    name = os.path.splitext(os.path.basename(spec_path))[0]
    os.makedirs(outdir, exist_ok=True)
    kind = spec["source"]["kind"]
    rect = spec.get("meta", {}).get("rectified")
    if rect and os.path.exists(rect):
        orig = cv2.imread(rect)
    elif kind == "pdf_vector":
        orig = PV.render(fitz.open(spec["source"]["path"])[0], 10)
    else:
        raise SystemExit("보정 원본 이미지를 찾을 수 없음 (--debug-dir 로 run 한 spec 필요)")
    r = UP.upload(spec, name)
    if not r.get("ok"):
        raise SystemExit("upload failed: %s" % r)
    pdf = UP.export_pdf(r["id"], r["gid"])
    open(os.path.join(outdir, name + "_sheet.pdf"), "wb").write(pdf)
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    sheet = PV.render(page, 10)
    go = _grid_of_image(orig)
    gs = G.build_grid(PV.vec_mask(page), PV.MASK_PPM)
    # 시트 표의 첫 선 중심은 PDF (0,0) 이라 절반이 잘려 검출되지 않는다 -> 0 으로 보충
    if gs["xs"][0] / PV.MASK_PPM > 1.0:
        gs["xs"].insert(0, 0.0)
    if gs["ys"][0] / PV.MASK_PPM > 1.0:
        gs["ys"].insert(0, 0.0)
    ox, oy = go["xs"][0] / 10.0, go["ys"][0] / 10.0     # mm (보정 원본)
    sx, sy = gs["xs"][0] / PV.MASK_PPM, gs["ys"][0] / PV.MASK_PPM
    res = {"name": name, "url": r.get("url"), "orig_cols": len(go["xs"]) - 1, "orig_rows": len(go["ys"]) - 1,
           "sheet_cols": len(gs["xs"]) - 1, "sheet_rows": len(gs["ys"]) - 1}
    errs = []
    if res["orig_cols"] == res["sheet_cols"] and res["orig_rows"] == res["sheet_rows"]:
        for a, b in zip(go["xs"], gs["xs"]):
            errs.append(abs((a / 10.0 - ox) - (b / PV.MASK_PPM - sx)))
        for a, b in zip(go["ys"], gs["ys"]):
            errs.append(abs((a / 10.0 - oy) - (b / PV.MASK_PPM - sy)))
        e = np.array(errs)
        res.update({"median_mm": round(float(np.median(e)), 3), "max_mm": round(float(e.max()), 3),
                    "mean_mm": round(float(e.mean()), 3)})
    else:
        res["note"] = "격자 선 개수 불일치로 선 위치 비교 불가 (판독 결과 행/열이 시트 재검출과 다름)"
    # 겹친 비교 (원본=빨강 계열, 시트=청록 계열), 시트 표 좌상단을 원본 표 좌상단에 맞춤
    H, W = orig.shape[:2]
    shifted = np.full((H, W), 255, np.uint8)
    sg = cv2.cvtColor(sheet, cv2.COLOR_BGR2GRAY)
    dx, dy = int(round((ox - sx) * 10)), int(round((oy - sy) * 10))
    xa, ya = max(dx, 0), max(dy, 0)
    xb, yb = max(-dx, 0), max(-dy, 0)
    w_, h_ = min(W - xa, sg.shape[1] - xb), min(H - ya, sg.shape[0] - yb)
    if w_ > 0 and h_ > 0:
        shifted[ya:ya + h_, xa:xa + w_] = sg[yb:yb + h_, xb:xb + w_]
    og = cv2.cvtColor(orig, cv2.COLOR_BGR2GRAY)
    ov = np.dstack([shifted, shifted, og])  # BGR: 원본 선=파랑/초록 사라짐 -> 빨강, 시트 선=청록
    x0, y0 = int(go["xs"][0]) - 40, int(go["ys"][0]) - 40
    x1, y1 = int(go["xs"][-1]) + 40, int(go["ys"][-1]) + 40
    x0, y0 = max(x0, 0), max(y0, 0)
    cv2.imwrite(os.path.join(outdir, name + "_overlay_cmp.png"), ov[y0:y1, x0:x1])
    side = np.hstack([orig[y0:y1, x0:x1], cv2.cvtColor(shifted[y0:y1, x0:x1], cv2.COLOR_GRAY2BGR)])
    cv2.imwrite(os.path.join(outdir, name + "_side.png"), side)
    json.dump(res, open(os.path.join(outdir, name + "_verify.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))


# ------------------------------------------------------------------ v2 페이지 모드
def _chars(page):
    out = []
    for b in page.get_text("rawdict")["blocks"]:
        for l in b.get("lines", []):
            for sp in l["spans"]:
                for ch in sp["chars"]:
                    if ch["c"].strip():
                        out.append((ch["c"], ch["bbox"], ch["origin"], sp["size"]))
    return out


def _find(chars, text, near_mm):
    """정규화 텍스트가 연속으로 나타나는 위치 중 near_mm(x,y) 에 가장 가까운 것 -> dict | None"""
    t = "".join(text.split())
    if not t:
        return None
    s = "".join(c[0] for c in chars)
    best, i = None, s.find(t)
    while i >= 0:
        seg = chars[i:i + len(t)]
        x0 = min(c[1][0] for c in seg); x1 = max(c[1][2] for c in seg)
        by = sum(c[2][1] for c in seg) / len(seg)
        cx, cy = (x0 + x1) / 2 * PV.PT_MM, by * PV.PT_MM
        d = math.hypot(cx - near_mm[0], cy - near_mm[1]) if near_mm else 0
        if best is None or d < best[0]:
            sizes = sorted(c[3] for c in seg)
            best = (d, {"cx": cx, "by": by * PV.PT_MM, "size": sizes[len(sizes) // 2], "x0": x0 * PV.PT_MM, "x1": x1 * PV.PT_MM})
        i = s.find(t, i + 1)
    return best[1] if best else None


def _ink(img):
    g = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    return g < 140


def _match_lines(a, b, tol=3.0):
    """a(원본 선, mm) 각각에 가장 가까운 b(시트 선) 오차"""
    errs, miss = [], 0
    for v in a:
        d = min((abs(v - w) for w in b), default=None)
        if d is None or d > tol:
            miss += 1
        else:
            errs.append(d)
    return errs, miss


def main_v2(spec_path, outdir, delete=False):
    spec = json.load(open(spec_path))
    name = os.path.splitext(os.path.basename(spec_path))[0]
    os.makedirs(outdir, exist_ok=True)
    odoc = fitz.open(spec["source"]["path"])
    opage = odoc[spec["source"].get("page", 0)]
    pdf_path = os.path.join(outdir, name + "_sheet.pdf")
    r = UP.upload(spec, name)
    if not r.get("ok"):
        raise SystemExit("upload failed: %s" % r)
    pdf = UP.export_pdf(r["id"], r["gid"])
    open(pdf_path, "wb").write(pdf)
    sdoc = fitz.open(stream=pdf, filetype="pdf")
    spage = sdoc[0]
    res = {"name": name, "url": r.get("url"), "id": r["id"], "sheet_pages": len(sdoc)}
    oimg, simg = PV.render(opage, 10), PV.render(spage, 10)
    H, W = oimg.shape[:2]
    canvas = np.full((H, W, 3), 255, np.uint8)
    h_, w_ = min(H, simg.shape[0]), min(W, simg.shape[1])
    canvas[:h_, :w_] = simg[:h_, :w_]
    simg = canvas
    # 1) 표 선 위치
    lines_o = PV.text_lines(opage)
    skip, _ = PV.underline_segs(opage, lines_o)
    go = G.build_grid(PV.mask_v2(opage, skip), PV.MASK_PPM)
    try:
        gs = G.build_grid(PV.vec_mask(spage), PV.MASK_PPM)
    except RuntimeError as e:
        gs = None
        res["grid_sheet"] = "fail:%s" % e
    if gs:
        ex, mx = _match_lines([x / PV.MASK_PPM for x in go["xs"]], [x / PV.MASK_PPM for x in gs["xs"]])
        ey, my = _match_lines([y / PV.MASK_PPM for y in go["ys"]], [y / PV.MASK_PPM for y in gs["ys"]])
        e = np.array(ex + ey) if ex + ey else np.array([99.0])
        res.update({"orig_lines": [len(go["xs"]), len(go["ys"])], "sheet_lines": [len(gs["xs"]), len(gs["ys"])],
                    "line_median_mm": round(float(np.median(e)), 3), "line_max_mm": round(float(e.max()), 3),
                    "line_unmatched": mx + my})
    # 2) 텍스트
    co, cs = _chars(opage), _chars(spage)
    to, ts = "".join(c[0] for c in co), "".join(c[0] for c in cs)
    res["text_ratio"] = round(difflib.SequenceMatcher(None, to, ts, autojunk=False).ratio(), 4)
    items, blocks = [], []
    for c in spec["cells"]:
        t = c.get("text") or ""
        if not t.strip():
            continue
        sb = c.get("src_bbox")
        near = ((sb[0] + sb[2]) / 2, (sb[1] + sb[3]) / 2) if sb else None
        a = _find(co, t, near)
        b = _find(cs, t, (a["cx"], a["by"]) if a else near)
        it = {"text": t.replace("\n", " ")[:24], "role": c.get("role", "table"), "found": b is not None}
        if a and b:
            it.update({"dx": b["cx"] - a["cx"], "dy": b["by"] - a["by"], "dsize": b["size"] - a["size"]})
        items.append(it)
    nf = sum(i["found"] for i in items)
    res["text_items"] = len(items)
    res["text_found_pct"] = round(100 * nf / max(1, len(items)), 1)
    for role in ("text", "table"):
        sel = [i for i in items if i["role"] == role and "dx" in i]
        if sel:
            d = [math.hypot(i["dx"], i["dy"]) for i in sel]
            res[role + "_center_err_mm"] = {"median": round(float(np.median(d)), 2), "max": round(max(d), 2),
                                            "dx_med": round(float(np.median([i["dx"] for i in sel])), 2),
                                            "dy_med": round(float(np.median([i["dy"] for i in sel])), 2)}
            ds = [abs(i["dsize"]) for i in sel]
            res[role + "_size_err_pt"] = {"mean": round(float(np.mean(ds)), 2), "max": round(max(ds), 2)}
    res["items"] = [{k: (round(v, 2) if isinstance(v, float) else v) for k, v in i.items()} for i in items]
    # 3) 잉크 IoU
    ko = np.ones((5, 5), np.uint8)  # 2px 팽창
    a, b = _ink(oimg), _ink(simg)
    ad, bd = cv2.dilate(a.astype(np.uint8), ko) > 0, cv2.dilate(b.astype(np.uint8), ko) > 0
    res["ink_iou_dilated"] = round(float((ad & bd).sum() / max(1, (ad | bd).sum())), 4)
    res["ink_iou_raw"] = round(float((a & b).sum() / max(1, (a | b).sum())), 4)
    res["ink_recall_dilated"] = round(float((a & bd).sum() / max(1, a.sum())), 4)
    # 4) 이미지
    ov = np.full((H, W, 3), 255, np.uint8)
    ov[b] = (255, 0, 0)
    ov[a] = (0, 0, 255)
    ov[a & b] = (0, 0, 0)
    cv2.imwrite(os.path.join(outdir, name + "_overlay_cmp.png"), ov)
    cv2.imwrite(os.path.join(outdir, name + "_side.png"), np.hstack([oimg, simg]))
    json.dump(res, open(os.path.join(outdir, name + "_verify.json"), "w"), ensure_ascii=False, indent=1)
    if delete:
        UP.call("delete", id=r["id"])
    s = {k: v for k, v in res.items() if k != "items"}
    print(json.dumps(s, ensure_ascii=False))
    return res


def main(spec_path, outdir, delete=False):
    spec = json.load(open(spec_path))
    if spec.get("version") == 2:
        return main_v2(spec_path, outdir, delete)
    return main_v1(spec_path, outdir)
