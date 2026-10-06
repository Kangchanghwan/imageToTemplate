"""구조/칸 채점: struct_eval.py <pred_spec.json> <원본 PDF>  (정답 = pdf_vector 경로 결과, 캐시: /tmp/gt_<stem>.json)"""
import json, os, sys
sys.path.insert(0, ".")
from sheetparser import pipeline, score
pred, pdf = sys.argv[1:3]
cache = "/tmp/gt_%s.json" % os.path.splitext(os.path.basename(pdf))[0]
if os.path.exists(cache):
    gt = json.load(open(cache))
else:
    gt = pipeline.run_pdf_page(pdf)
    json.dump(gt, open(cache, "w"), ensure_ascii=False)
r = score.struct_score(json.load(open(pred)), gt)
print("STRUCT", json.dumps(r, ensure_ascii=False))
