"""SPEC 7단계: 시트 업로드 -> A4 PDF -> 래스터화 -> 보정 원본과 격자선 위치 비교."""
import json
import os

import cv2
import fitz
import numpy as np

import math

from . import grid as G, pdfvec as PV, preprocess as PP, upload as UP, pipeline as PL
from . import verify as VF


def _grid_of_image(img):
    return G.build_grid(PP.line_mask(img), PP.PPM)


def main(spec_path, outdir, delete=False):
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
    # 글자/굵기/블록 위치: 스펙의 칸 내용을 시트 PDF 글자에서 찾는다
    cs = VF._chars(page)
    items = []
    for c in spec["cells"]:
        t = (c.get("text") or "")
        if not t.strip():
            continue
        sb = c.get("src_bbox")
        near = None
        b = VF._find(cs, t, near)
        it = {"role": c.get("role", "table"), "found": b is not None, "bold_spec": bool(c.get("bold"))}
        if b:
            it["bold_s"] = b["bold"]
        items.append(it)
    ni = len(items)
    pres = {"text_items": ni, "text_found_pct": round(100 * sum(i["found"] for i in items) / max(1, ni), 1)}
    bi = [i for i in items if "bold_s" in i]
    if bi:  # 사진은 원본 PDF 가 없으므로 스펙에 정한 굵기가 시트 PDF 에 실제로 나왔는지
        pres["bold_match_pct"] = round(100 * sum(i["bold_spec"] == i["bold_s"] for i in bi) / len(bi), 1)
        pres["bold_spec_count"] = sum(i["bold_spec"] for i in bi)
    blk = []
    for c in spec["cells"]:
        if c.get("role") != "text" or not (c.get("text") or "").strip() or not c.get("src_bbox"):
            continue
        sx0, sy0, sx1, sy1 = c["src_bbox"]
        t = "".join(c["text"].split())
        sj = "".join(x[0] for x in cs)
        i = sj.find(t)
        if i >= 0:
            seg = cs[i:i + len(t)]
            x0_ = min(x[1][0] for x in seg) * PV.PT_MM; x1_ = max(x[1][2] for x in seg) * PV.PT_MM
            y0_ = min(x[1][1] for x in seg) * PV.PT_MM; y1_ = max(x[1][3] for x in seg) * PV.PT_MM
            hh = c.get("h", "LEFT")   # 칸 bbox 는 여유 폭이 더해져 있으므로 정렬 기준 변(왼쪽/오른쪽/가운데)으로 비교
            dx = (x0_ - sx0) if hh == "LEFT" else (x1_ - sx1) if hh == "RIGHT" else (x0_ + x1_) / 2 - (sx0 + sx1) / 2
            blk.append(math.hypot(dx, (y0_ + y1_) / 2 - (sy0 + sy1) / 2))
    if blk:
        pres["block_center_err_mm"] = {"median": round(float(np.median(blk)), 2), "max": round(float(max(blk)), 2), "n": len(blk)}
    go = _grid_of_image(orig)
    gs = G.build_grid(PV.vec_mask(page), PV.MASK_PPM)
    ox, oy = go["xs"][0] / 10.0, go["ys"][0] / 10.0     # mm (보정 원본)
    sx, sy = gs["xs"][0] / PV.MASK_PPM, gs["ys"][0] / PV.MASK_PPM
    res = {"name": name, "url": r.get("url"), "id": r["id"], **pres, "orig_cols": len(go["xs"]) - 1, "orig_rows": len(go["ys"]) - 1,
           "sheet_cols": len(gs["xs"]) - 1, "sheet_rows": len(gs["ys"]) - 1}
    errs = []
    # 사진에서 왼쪽 열이 잘려 선이 모자랄 수 있어 오른쪽/아래 끝 기준으로 맞춰 비교
    nx, ny = min(len(go["xs"]), len(gs["xs"])), min(len(go["ys"]), len(gs["ys"]))
    if nx >= 3 and ny >= 3 and abs(len(go["xs"]) - len(gs["xs"])) <= 1 and abs(len(go["ys"]) - len(gs["ys"])) <= 1:
        ox, sx = go["xs"][-nx] / 10.0, gs["xs"][-nx] / PV.MASK_PPM
        oy, sy = go["ys"][-ny] / 10.0, gs["ys"][-ny] / PV.MASK_PPM
        res["aligned_lines"] = [nx, ny]
        for a, b in zip(go["xs"][-nx:], gs["xs"][-nx:]):
            errs.append(abs((a / 10.0 - ox) - (b / PV.MASK_PPM - sx)))
        for a, b in zip(go["ys"][-ny:], gs["ys"][-ny:]):
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
    # 페이지 전체 나란히 (왼쪽 보정 원본, 오른쪽 시트 A4 렌더; 둘 다 용지 왼쪽 위 기준)
    Hh, Ww = min(orig.shape[0], sheet.shape[0]), 2100
    def _fit(a):
        out = np.full((Hh, Ww, 3), 255, np.uint8)
        h_, w_ = min(Hh, a.shape[0]), min(Ww, a.shape[1])
        out[:h_, :w_] = a[:h_, :w_]
        return out
    cv2.imwrite(os.path.join(outdir, name + "_page_side.png"), np.hstack([_fit(orig), _fit(sheet)]))
    json.dump(res, open(os.path.join(outdir, name + "_verify.json"), "w"), ensure_ascii=False, indent=1)
    if delete:
        UP.call("delete", id=r["id"])
    print(json.dumps(res, ensure_ascii=False))
    return res
