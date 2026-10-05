#!/bin/sh
# 10개 최종 실행 (elgrim 컨테이너 안에서 실행): 직렬, 실패해도 계속
cd /w
mkdir -p data/scan runs/convert
for n in attendance_09 activity_09 meal_09; do
  python -m sheetparser convert data/pdfs/$n.pdf -o runs/convert/$n --title v3_$n 2>&1 | grep -v deprecat
done
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  python -m sheetparser convert data/photos/$n.jpg -o runs/convert/$n --title v3_$n 2>&1 | grep -v deprecat
done
python tools/make_scan.py data/pdfs/attendance_09.pdf data/scan/attendance_09_scan.pdf 2>&1 | grep -v deprecat
python -m sheetparser convert data/scan/attendance_09_scan.pdf -o runs/convert/attendance_09_scan --title scan_attendance_09 --delete 2>&1 | grep -v deprecat
echo ALLDONE
