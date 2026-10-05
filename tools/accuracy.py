"""검증 끈 convert 결과(spec json)의 정확도만 오프라인 채점 (vlm/업로드 호출 없음).
  사진:    accuracy.py photo <spec.json> <name>      (data/photos/gt_content.json 대비 셀 일치)
  스캔PDF: accuracy.py scan  <spec.json> <원본 텍스트 PDF>   (원본 텍스트 레이어 글자 대비 글자 일치)"""
import collections
import json
import re
import sys

sys.path.insert(0, ".")
mode, sp, arg = sys.argv[1:4]
spec = json.load(open(sp))
if mode == "photo":
    from sheetparser import score
    c = score.content_score(spec, json.load(open("data/photos/gt_content.json")), arg)
    print(json.dumps({k: c[k] for k in c if k in ("cells_ok", "cells_total", "wrong", "block_ok", "need_ok", "need_total")}, ensure_ascii=False))
else:
    import fitz
    norm = lambda t: re.sub(r"\s+", "", t)
    gt = collections.Counter(norm(fitz.open(arg)[0].get_text()))
    got = collections.Counter(norm("".join(c.get("text", "") for c in spec["cells"])))
    ok = sum((gt & got).values())
    print(json.dumps({"chars_ok": ok, "chars_total": sum(gt.values()), "extra": sum((got - gt).values()),
                      "missing": dict((gt - got).most_common(10)), "extra_chars": dict((got - gt).most_common(10))}, ensure_ascii=False))
