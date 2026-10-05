#!/bin/sh
# 4라운드 측정: 검증 끈 convert, 직렬. sched_09 만 v4_sched_09 로 남기고 나머지는 --delete. 사용: run_r4.sh <out접두>
O=${1:-r4}
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  if [ $n = sched_09 ]; then T="--title v4_sched_09"; else T="--title r4_$n --delete"; fi
  python -m sheetparser convert data/photos/$n.jpg -o runs/$O/$n $T
done
python -m sheetparser convert data/pdfs/scan_attendance_09.pdf -o runs/$O/scan --title r4_scan --delete
