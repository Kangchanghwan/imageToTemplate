#!/bin/sh
# 업로드(시트 생성) 없이 spec 만 만들어 채점. Apps Script 일일 생성 한도 초과 시 회귀용. 사용: run_r9_nu.sh <접두>
O=${1:-r9nu}
python - <<PY
import json, os, sys, time
sys.path.insert(0, ".")
from sheetparser import photopage
for n in "sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal".split():
    t = time.time()
    sp = photopage.run_page("data/photos/%s.jpg" % n)
    os.makedirs("runs/$O/%s" % n, exist_ok=True)
    json.dump(sp, open("runs/$O/%s/r9_%s.json" % (n, n), "w"), ensure_ascii=False)
    print("== %s %.1fs" % (n, time.time() - t))
PY
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  python tools/accuracy.py photo runs/$O/$n/r9_$n.json $n
  python - <<PY
import json;s=json.load(open("runs/$O/$n/r9_$n.json"));print("SHAPE $n rows",len(s["rows"]),"cols",len(s["columns"]),"merges",sum(1 for c in s["cells"] if c.get("role")=="table" and (c["rs"]>1 or c["cs"]>1)))
PY
done
python -m sheetparser bench data/synth -o runs/$O/bench --modes vector,photo | grep -E '"mode"' | python -c "
import sys,json
ok=n=0
for l in sys.stdin:
    s=json.loads(l); n+=1; ok+= bool(s.get('rows_ok') and s.get('cols_ok') and s.get('merge_f1',0)>=0.999)
print('BENCH ok',ok,'of',n)"
python tools/sched_consist.py runs/$O
