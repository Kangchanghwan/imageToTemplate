#!/bin/sh
# 7라운드: 긴 칸 잘림 회귀. 컨테이너 안에서 실행(elgrim docker). 사용: run_r7.sh <out접두> [act]  (act: 활동일지 2건만)
# 통과선: activity 사진/스캔 >=931/940 & extra<=5, 근무일정표 290/290, 머리글 18/18, scan_attendance_09 664/664
O=${1:-r7}; MODE=$2
for f in "activity_photo data/pdfs/activity_09_300dpi.png" "activity_scan data/pdfs/scan_activity_09.pdf"; do
  set -- $f
  python -m sheetparser convert "$2" -o runs/$O/$1 --title r7_$1 --delete | grep -E "^==|sec_spec|auto_fallback|trunc"
  python tools/accuracy.py pdf runs/$O/$1/r7_$1.json data/pdfs/activity_09.pdf
  python - <<PY
import json;m=json.load(open("runs/$O/$1/r7_$1.json"))["meta"];print("META",m.get("ocr_backend"),m.get("auto_fallback"),m.get("trunc"),m.get("vlm"))
PY
done
[ "$MODE" = act ] && exit 0
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  python -m sheetparser convert data/photos/$n.jpg -o runs/$O/$n --title r7_$n --delete | grep -E "^=="
  python tools/accuracy.py photo runs/$O/$n/r7_$n.json $n
done
python -m sheetparser convert data/pdfs/scan_attendance_09.pdf -o runs/$O/scan --title r7_scan --delete | grep -E "^=="
python tools/accuracy.py pdf runs/$O/scan/r7_scan.json data/pdfs/attendance_09.pdf
