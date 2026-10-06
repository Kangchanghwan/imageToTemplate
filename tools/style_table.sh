#!/bin/sh
# 한 실행 디렉터리(runs/<접두>)의 6개 입력 서식 채점을 한 줄씩. 사용: style_table.sh <접두> (컨테이너 안)
for n in attendance_09 activity_09 meal_09; do for k in photo scan; do
  printf "%s_%s " $n $k; python tools/style_eval.py runs/$1/${n}_$k/r9_${n}_$k.json data/pdfs/$n.pdf 2>&1 | grep STYLE
done; done
