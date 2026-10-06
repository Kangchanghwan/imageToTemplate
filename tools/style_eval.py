"""서식 채점: style_eval.py <pred_spec.json> <원본 PDF>  (정답 = pdf_vector 경로 결과, 캐시: /tmp/gt2_<stem>.json)"""
import json, os, sys
sys.path.insert(0, ".")
from sheetparser import pipeline, score
pred, pdf = sys.argv[1:3]
verbose = "-v" in sys.argv
cache = "/tmp/gt2_%s.json" % os.path.splitext(os.path.basename(pdf))[0]
if os.path.exists(cache) and "--fresh" not in sys.argv:
    gt = json.load(open(cache))
else:
    gt = pipeline.run_pdf_page(pdf)
    json.dump(gt, open(cache, "w"), ensure_ascii=False)
r = score.style_score(json.load(open(pred)), gt)
m = r.pop("miss"); bm = r.pop("blk_miss")
print("STYLE", json.dumps({k: (round(v, 4) if isinstance(v, float) else v) for k, v in r.items()}, ensure_ascii=False))
if verbose:
    for k, v in m.items():
        if v: print("  MISS", k, v)
    print("  BLKMISS", bm)
