"""사진 7장 run -> verify(업로드 포함) -> 지표. 사용: python tools/photo_round.py OUTDIR [names...] [--noverify]"""
import json, os, sys, time, io, contextlib
sys.path.insert(0, ".")
from sheetparser import photopage, score, verify_photo as verify
out = sys.argv[1]; args = [a for a in sys.argv[2:] if not a.startswith("--")]
names = args or ["sched_09", "sched_10", "sched_11", "sched_12", "form_activity", "form_attendance", "form_meal"]
os.makedirs(out, exist_ok=True)
gt = json.load(open("data/photos/gt_content.json"))
rows = []
for n in names:
    t = time.time()
    r = {"name": n}
    try:
        sp = photopage.run_page("data/photos/%s.jpg" % n, ocr="--noocr" not in sys.argv, debug_dir=out + "/dbg")
        r["sec"] = round(time.time() - t, 1)
        p = "%s/v2_%s.json" % (out, n)
        json.dump(sp, open(p, "w"), ensure_ascii=False, indent=1)
        r["content"] = score.content_score(sp, gt, n)
        m = sp["meta"]
        r.update({"bg_cells": m["bg_cells"], "col_size_std": m["col_size_std"], "calls": m["calls"], "flags": [f["reason"] for f in sp["flags"]]})
        sizes = sorted({c["size_pt"] for c in sp["cells"] if c.get("text")})
        r["sizes"] = sizes
        if "--noverify" not in sys.argv:
            try:
                buf = io.StringIO()
                with contextlib.redirect_stdout(buf):
                    verify.main(p, out + "/verify")
                r["verify"] = json.load(open("%s/verify/v2_%s_verify.json" % (out, n)))
            except BaseException as e:
                r["verify_err"] = repr(e)[:200]
    except Exception as e:
        r["err"] = repr(e)[:300]
    rows.append(r)
    print(json.dumps(r, ensure_ascii=False), flush=True)
json.dump(rows, open(out + "/round.json", "w"), ensure_ascii=False, indent=1)
