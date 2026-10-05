#!/bin/sh
# 맥에서 elgrim docker 로 파이썬 실행: tools/dk.sh <python args...>  (먼저 rsync)
# 사용: tools/dk.sh -m sheetparser convert data/photos/sched_09.jpg
rsync -aq --exclude .git --exclude runs --exclude data/synth ./ elgrim:~/sheetparser/
ssh elgrim "cd ~/sheetparser && docker run --rm -u \$(id -u):\$(id -g) --network host -v \$PWD:/w sheetparser python $*"
