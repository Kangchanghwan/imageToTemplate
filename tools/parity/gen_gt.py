"""칸 단위 정답 텍스트: PDF 3종은 pdf_vector 경로 결과, 합성은 data/synth/sNN.json. out/gt/<name>.json = [[r,c,rs,cs,text],...]"""
import json, os, sys
sys.path.insert(0, ".")
from sheetparser import pipeline, score
out = sys.argv[1]
os.makedirs(os.path.join(out, "gt"), exist_ok=True)
for n in ("activity", "attendance", "meal"):
    gt = pipeline.run_pdf_page("data/pdfs/%s_09.pdf" % n)
    v = score.table_view(gt)
    for nm in (n + "_300dpi", "scan_" + n):
        json.dump([list(c) for c in v["cells"]], open(os.path.join(out, "gt", nm + ".json"), "w"), ensure_ascii=False)
for i in range(12):
    nm = "s%02d_photo" % i
    g = json.load(open("data/synth/s%02d.json" % i))   # v1 spec(meta 없음): 칸을 직접 읽는다
    json.dump([[c["r"], c["c"], c["rs"], c["cs"], c.get("text", "")] for c in g["cells"]], open(os.path.join(out, "gt", nm + ".json"), "w"), ensure_ascii=False)
print("ok")
