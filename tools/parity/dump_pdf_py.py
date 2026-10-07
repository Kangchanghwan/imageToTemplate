"""3단계 대조용 Python 덤프(PDF 벡터 경로): 중간 산출물과 최종 spec 을 JSON 으로.
사용(elgrim docker): python tools/parity/dump_pdf_py.py <outdir> [이름...]
  <outdir>/pdf_py/<name>.json: info, drawings, rawlines(rawdict), texttrace1, text_lines, underline, mask(hash/nz), fills, images, spec(run_pdf_page), spec_v1(run_pdf)
  <outdir>/pdf_py/<name>_render10.png   PV.render(page, 10) (run_pdf v1 입력)
  <outdir>/pdf_py/<name>_img<k>.png      page.get_image_info 이미지의 PNG
"""
import base64, glob, hashlib, json, os, sys, time
import cv2, fitz, numpy as np
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", ".."))
from sheetparser import pdfvec as PV, pipeline  # noqa: E402


def sha(b):
    return hashlib.sha256(b).hexdigest()


def jn(o):
    if isinstance(o, dict):
        return {str(k): jn(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [jn(v) for v in o]
    if isinstance(o, set):
        return sorted(jn(v) for v in o)
    if isinstance(o, fitz.Rect) or isinstance(o, fitz.Point):
        return list(o)
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating,)):
        return float(o)
    return o


def drawings(page):
    out = []
    for d in page.get_drawings():
        items = []
        for it in d["items"]:
            if it[0] == "l":
                items.append(["l", it[1].x, it[1].y, it[2].x, it[2].y])
            elif it[0] == "re":
                r = it[1]
                items.append(["re", r.x0, r.y0, r.x1, r.y1])
            elif it[0] == "qu":
                q = it[1]
                items.append(["qu"] + [v for p in (q.ul, q.ur, q.ll, q.lr) for v in (p.x, p.y)])
            else:
                items.append([it[0]] + [v for p in it[1:] for v in ((p.x, p.y) if hasattr(p, "x") else (p,))])
        out.append({"type": d["type"], "color": d.get("color"), "fill": d.get("fill"), "width": d.get("width"), "rect": list(d["rect"]),
                    "closePath": d.get("closePath"), "even_odd": d.get("even_odd"), "items": items})
    return out


def rawlines(page):
    out = []
    for bi, b in enumerate(page.get_text("rawdict")["blocks"]):
        if b.get("type") != 0:
            continue
        for l in b["lines"]:
            sps = []
            for sp in l["spans"]:
                sps.append({"font": sp["font"], "size": sp["size"], "flags": sp["flags"], "color": sp["color"], "origin": list(sp["origin"]), "bbox": list(sp["bbox"]),
                            "asc": sp.get("ascender"), "desc": sp.get("descender"),
                            "chars": [[c["c"], list(c["origin"]), list(c["bbox"])] for c in sp["chars"]]})
            out.append({"block": bi, "dir": list(l["dir"]), "bbox": list(l["bbox"]), "spans": sps})
    return out


def dump(name, path, outdir):
    d = fitz.open(path)
    page = d[0]
    r = {"name": name, "src": path, "npages": len(d)}
    t0 = time.time()
    dr = page.get_drawings()
    r["info"] = {"rect": list(page.rect), "rotation": page.rotation, "mediabox": list(page.mediabox), "cropbox": list(page.cropbox),
                 "ndrawings": len(dr), "nwords": len(page.get_text("words")), "is_vector": PV.is_vector(page), "detect": pipeline_detect(path)}
    r["drawings"] = drawings(page)
    r["rawlines"] = rawlines(page)
    tt = page.get_texttrace()
    r["texttrace1"] = [[ch[2][0], ch[2][1]] for t in tt if t.get("type") == 1 for ch in t["chars"]]
    r["texttrace_types"] = {str(t.get("type")): sum(1 for u in tt if u.get("type") == t.get("type")) for t in tt}
    lines = PV.text_lines(page)
    r["text_lines"] = [{"chars": [list(c) for c in l["chars"]], "y0": l["y0"], "y1": l["y1"], "oy": l["oy"]} for l in lines]
    skip, ul = PV.underline_segs(page, lines)
    r["underline"] = {"ids": sorted(skip), "ul": [list(u) for u in ul]}
    m = PV.mask_v2(page, skip)
    r["mask"] = {"shape": list(m.shape), "nz": int(np.count_nonzero(m)), "sha": sha(m.tobytes())}
    np.save(os.path.join(outdir, "pdf_py", name + "_mask.npy"), m) if False else cv2.imwrite(os.path.join(outdir, "pdf_py", name + "_mask.png"), m)
    r["fills"] = [list(f) for f in PV.fills(page)]
    ims = PV.images(page)
    r["images"] = []
    for k, im in enumerate(ims):
        png = base64.b64decode(im["png_b64"])
        open(os.path.join(outdir, "pdf_py", "%s_img%d.png" % (name, k)), "wb").write(png)
        a = cv2.imdecode(np.frombuffer(png, np.uint8), cv2.IMREAD_UNCHANGED)
        r["images"].append({"bbox": list(im["bbox"]), "shape": list(a.shape), "pix_sha": sha(a.tobytes()), "png_len": len(png)})
    if r["info"]["is_vector"]:
        spec = pipeline.run_pdf_page(path)
        for im in spec["images"]:
            im["png_sha"] = sha(base64.b64decode(im["png_b64"]))
            im["png_b64"] = ""
        r["spec"] = spec
        try:
            s1 = pipeline.run_pdf(path, ocr=False)
            r["spec_v1"] = s1
            cv2.imwrite(os.path.join(outdir, "pdf_py", name + "_render10.png"), PV.render(page, 10))
        except Exception as e:  # noqa: BLE001
            r["spec_v1_error"] = repr(e)
    r["sec"] = round(time.time() - t0, 2)
    json.dump(jn(r), open(os.path.join(outdir, "pdf_py", name + ".json"), "w"), ensure_ascii=False)
    return r


def pipeline_detect(path):
    from sheetparser import convert
    return convert.detect(path)


def main():
    outdir = sys.argv[1]
    only = set(sys.argv[2:])
    os.makedirs(os.path.join(outdir, "pdf_py"), exist_ok=True)
    items = [("activity_09", "data/pdfs/activity_09.pdf"), ("attendance_09", "data/pdfs/attendance_09.pdf"), ("meal_09", "data/pdfs/meal_09.pdf"),
             ("scan_activity_09", "data/pdfs/scan_activity_09.pdf"), ("scan_attendance_09", "data/pdfs/scan_attendance_09.pdf"), ("scan_meal_09", "data/pdfs/scan_meal_09.pdf")]
    items += [("s%02d" % i, "data/synth/s%02d.pdf" % i) for i in range(12)]
    items += [(os.path.splitext(os.path.basename(p))[0], p) for p in sorted(glob.glob(os.path.join(outdir, "extra_pdfs", "x*.pdf")))]   # runs/ 의 구글 시트 내보내기 등(추가 입력)
    for name, p in items:
        if only and name not in only:
            continue
        if not os.path.exists(p):
            continue
        r = dump(name, p, outdir)
        print(name, r["info"]["detect"], "draw", r["info"]["ndrawings"], "lines", len(r["text_lines"]), "imgs", len(r["images"]), r["sec"], flush=True)


if __name__ == "__main__":
    main()
