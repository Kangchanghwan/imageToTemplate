"""칸 하나의 정답/예측 전체 문자열 비교: celldiff.py <pred spec> <원본 pdf> <행> <열>"""
import json, sys
sys.path.insert(0, ".")
from sheetparser import pipeline, score
pred, pdf, r, c = sys.argv[1], sys.argv[2], int(sys.argv[3]), int(sys.argv[4])
p = score.table_view(json.load(open(pred))); g = score.table_view(pipeline.run_pdf_page(pdf))
for name, v in (("정답", g), ("예측", p)):
    for (rr, cc, rs, cs, t) in v["cells"]:
        if rr == r and cc == c:
            print(name, repr(t))
