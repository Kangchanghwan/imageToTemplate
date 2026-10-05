#!/bin/sh
# 백그라운드 실행: tools/dkbg.sh <log명> <python args...>  -> elgrim ~/sheetparser/runs/<log명>.log 에 기록
rsync -aq --exclude .git --exclude runs --exclude data/synth ./ elgrim:~/sheetparser/
LOG=$1; shift
ssh elgrim "cd ~/sheetparser && mkdir -p runs && nohup docker run --rm -u \$(id -u):\$(id -g) --network host -v \$PWD:/w sheetparser python $* > runs/$LOG.log 2>&1 &"
