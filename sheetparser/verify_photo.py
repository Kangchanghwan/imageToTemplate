"""SPEC 7단계: 시트 업로드 -> A4 PDF -> 래스터화 -> 보정 원본과 격자선 위치 비교."""
import json
import os

import cv2
import fitz
import numpy as np

from . import grid as G, pdfvec as PV, preprocess as PP, upload as UP, pipeline as PL


def _grid_of_image(img):
    return G.build_grid(PP.line_mask(img), PP.PPM)


def main(spec_path, outdir):
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
    print('UPLOAD', {k: v for k, v in r.items() if k not in ('url',)} if not r.get('ok') else 'ok')
    if not r.get("ok"):
        raise SystemExit("upload failed: %s" % r)
    pdf = UP.export_pdf(r["id"], r["gid"])
    open(os.path.join(outdir, name + "_sheet.pdf"), "wb").write(pdf)
    page = fitz.open(stream=pdf, filetype="pdf")[0]
    sheet = PV.render(page, 10)
    go = _grid_of_image(orig)
    gs = G.build_grid(PV.vec_mask(page), PV.MASK_PPM)
    ox, oy = go["xs"][0] / 10.0, go["ys"][0] / 10.0     # mm (보정 원본)
    sx, sy = gs["xs"][0] / PV.MASK_PPM, gs["ys"][0] / PV.MASK_PPM
    res = {"name": name, "url": r.get("url"), "orig_cols": len(go["xs"]) - 1, "orig_rows": len(go["ys"]) - 1,
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
    json.dump(res, open(os.path.join(outdir, name + "_verify.json"), "w"), ensure_ascii=False, indent=1)
    print(json.dumps(res, ensure_ascii=False))
