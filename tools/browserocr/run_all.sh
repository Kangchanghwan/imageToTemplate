#!/bin/sh
# elgrim 도커(sheetparser:bro) 안에서 실행. 사용: run_all.sh <variant|base> [입력 필터]
# 입력 13개: 스캔 PDF 3 + 300dpi PNG 3 + 사진 7. 채점은 tools/accuracy.py, tools/struct_eval.py 그대로. 업로드 없음.
V=$1; F=$2
O=runs/bro/$V
run() {  # run <입력경로> <이름>
  if [ "$V" = base ]; then python -m sheetparser convert $1 -o $O/$2 --title $2 --no-upload | grep -E "^==" ; else
    BRO_NOCROP=${BRO_NOCROP:-1} python tools/browserocr/backend.py $V $1 $O/$2 $2 | grep -E "^BRO|^=="; fi
}
for n in attendance_09 activity_09 meal_09; do
  for k in photo:${n}_300dpi.png scan:scan_${n}.pdf; do
    kind=${k%%:*}; f=data/pdfs/${k#*:}; nm=${n}_$kind
    case "$nm" in *$F*) ;; *) continue;; esac
    run $f $nm
    echo "ACC $nm $(python tools/accuracy.py pdf $O/$nm/$nm.json data/pdfs/$n.pdf)"
    python tools/struct_eval.py $O/$nm/$nm.json data/pdfs/$n.pdf | sed "s/^/$nm /"
  done
done
for n in sched_09 sched_10 sched_11 sched_12 form_activity form_attendance form_meal; do
  case "$n" in *$F*) ;; *) continue;; esac
  run data/photos/$n.jpg $n
  echo "ACC $n $(python tools/accuracy.py photo $O/$n/$n.json $n)"
done
