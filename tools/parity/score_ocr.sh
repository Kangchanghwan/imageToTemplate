#!/bin/sh
# elgrim docker 안에서 실행: tools/parity/score_ocr.sh <spec 폴더> [접미사]   (접미사: 파일명 뒤 붙는 것, spec_py 는 "" )
# 회귀셋 13개는 tools/accuracy.py, tools/struct_eval.py 를 그대로 호출하고, 합성 12장은 score.struct_score(칸 텍스트) 로 채점한다.
D=$1
for n in attendance activity meal; do
  for nm in ${n}_300dpi scan_${n}; do
    echo "ACC $nm $(python tools/accuracy.py pdf $D/$nm.json data/pdfs/${n}_09.pdf)"
    python tools/struct_eval.py $D/$nm.json data/pdfs/${n}_09.pdf | sed "s/^/$nm /"
  done
done
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  echo "ACC $n $(python tools/accuracy.py photo $D/$n.json $n)"
done
python - <<PY
import json, sys
sys.path.insert(0, ".")
from sheetparser import score
ok = n = 0
bad = []
for i in range(12):
    nm = "s%02d_photo" % i
    pred = json.load(open("$D/" + nm + ".json"))
    g = json.load(open("data/synth/s%02d.json" % i))
    p, gg = score.table_view(pred), None
    # gt(v1)에는 meta 가 없어 칸 목록을 직접 만든다
    gcells = [(c["r"], c["c"], c["rs"], c["cs"], c.get("text", "")) for c in g["cells"]]
    import re
    norm = lambda s: re.sub(r"\s+", "", s or "")
    pm = {(r, c, rs, cs): t for (r, c, rs, cs, t) in p["cells"]}
    a = b = 0
    for (r, c, rs, cs, t) in gcells:
        if not norm(t): continue
        a += 1
        q = pm.get((r, c, rs, cs))
        if q is not None and norm(q) == norm(t): b += 1
        else: bad.append("%s r%d c%d 정답=%r 예측=%r" % (nm, r, c, norm(t), norm(q) if q is not None else None))
    ok += b; n += a
print("SYNTH text_ok %d/%d" % (ok, n))
for x in bad[:20]: print("SYNTH_WRONG", x)
PY
