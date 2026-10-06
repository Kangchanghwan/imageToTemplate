#!/bin/sh
# 10라운드 회귀. elgrim docker 안에서 실행. 사용: run_r10.sh <접두> [--sheets]
# 기본: 시트를 만들지 않고 spec 단계에서만 채점(Apps Script 일일 생성 한도 절약). 구조/내용/서식 지표 전부 오프라인.
# --sheets: 위 채점 뒤 대표 2개(v6_activity_photo, v7_sched_09)만 실제 시트 생성 + PDF 검증(--verify --keep).
O=${1:-r10}; SHEETS=$2
for n in attendance_09 activity_09 meal_09; do
  for k in photo:${n}_300dpi.png scan:scan_${n}.pdf; do
    kind=${k%%:*}; f=data/pdfs/${k#*:}
    python -m sheetparser convert $f -o runs/$O/${n}_$kind --title r9_${n}_$kind --no-upload | grep -E "^==|auto_fallback"
    python tools/accuracy.py pdf runs/$O/${n}_$kind/r9_${n}_$kind.json data/pdfs/$n.pdf
    python tools/struct_eval.py runs/$O/${n}_$kind/r9_${n}_$kind.json data/pdfs/$n.pdf
    python tools/style_eval.py runs/$O/${n}_$kind/r9_${n}_$kind.json data/pdfs/$n.pdf
  done
done
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  python -m sheetparser convert data/photos/$n.jpg -o runs/$O/$n --title r9_$n --no-upload | grep -E "^=="
  python tools/accuracy.py photo runs/$O/$n/r9_$n.json $n
  python - <<PY
import json;s=json.load(open("runs/$O/$n/r9_$n.json"));print("SHAPE $n rows",len(s["rows"]),"cols",len(s["columns"]),"merges",sum(1 for c in s["cells"] if c.get("role")=="table" and (c["rs"]>1 or c["cs"]>1)),"flags",[f["reason"] for f in s["flags"] if "trim" in f["reason"]])
PY
done
python -m sheetparser bench data/synth -o runs/$O/bench --modes vector,photo | grep -E '"mode"' | python -c "
import sys,json
for l in sys.stdin:
    s=json.loads(l); print('BENCH',s['name'],s['mode'],s.get('rows_ok'),s.get('cols_ok'),round(s.get('merge_f1',0),2),s.get('fail'))"
if [ "$SHEETS" = "--sheets" ]; then
  python -m sheetparser convert data/pdfs/activity_09_300dpi.png -o runs/v6 --title v6_activity_photo --verify --keep | grep -E "^==|URL|side|bold_match|text_found"
  python -m sheetparser convert data/photos/sched_09.jpg -o runs/v7 --title v7_sched_09 --verify --keep | grep -E "^==|URL|side|bold_match|text_found"
  python tools/cleanup.py --keep-prefix v
fi
