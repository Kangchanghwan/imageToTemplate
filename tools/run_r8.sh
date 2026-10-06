#!/bin/sh
# 8라운드: 구조 채점 + 마지막 열 누락 회귀. elgrim docker 안에서 실행. 사용: run_r8.sh <out접두> [six]  (six: 6개 입력만)
# 통과선: 6개 입력 행/열/병합 일치 + 열폭 비율 오차 평균<=3%, 칸별 텍스트>=99%, 글자 다중집합>=99% & extra<=5,
#         근무일정표 290/290, 머리글 18/18(행/열/병합 수 이전과 동일), 합성 bench 행/열/병합 F1 1.0, 사진 auto <=20초
O=${1:-r8}; MODE=$2
for n in attendance_09 activity_09 meal_09; do
  for k in photo:${n}_300dpi.png scan:scan_${n}.pdf; do
    kind=${k%%:*}; f=data/pdfs/${k#*:}
    python -m sheetparser convert $f -o runs/$O/${n}_$kind --title r8_${n}_$kind --delete | grep -E "^==|auto_fallback"
    python tools/accuracy.py pdf runs/$O/${n}_$kind/r8_${n}_$kind.json data/pdfs/$n.pdf
    python tools/struct_eval.py runs/$O/${n}_$kind/r8_${n}_$kind.json data/pdfs/$n.pdf
  done
done
[ "$MODE" = six ] && exit 0
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  python -m sheetparser convert data/photos/$n.jpg -o runs/$O/$n --title r8_$n --delete | grep -E "^=="
  python tools/accuracy.py photo runs/$O/$n/r8_$n.json $n
  python - <<PY
import json;s=json.load(open("runs/$O/$n/r8_$n.json"));print("SHAPE $n rows",len(s["rows"]),"cols",len(s["columns"]),"merges",sum(1 for c in s["cells"] if c.get("role")=="table" and (c["rs"]>1 or c["cs"]>1)),"flags",[f["reason"] for f in s["flags"] if "trim" in f["reason"]])
PY
done
python -m sheetparser bench data/synth -o runs/$O/bench --modes vector,photo | grep -E '"mode"' | python -c "
import sys,json
for l in sys.stdin:
    s=json.loads(l); print('BENCH',s['name'],s['mode'],s.get('rows_ok'),s.get('cols_ok'),round(s.get('merge_f1',0),2),s.get('fail'))"
