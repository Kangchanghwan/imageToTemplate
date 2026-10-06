#!/bin/sh
# 맥에서: rsync 후 elgrim 에서 nohup 으로 run_r9.sh 실행. 사용: r9_elgrim.sh <접두> [six]. 로그 elgrim ~/sheetparser/runs/<접두>.log
O=${1:-r9}
rsync -aq --exclude .git --exclude runs --exclude data/synth ./ elgrim:~/sheetparser/
ssh elgrim "cd ~/sheetparser && mkdir -p runs && nohup docker run --rm -u \$(id -u):\$(id -g) --network host -v \$HOME/sheetparser:/w -w /w -e PYTHONPATH=/w -v /tmp:/tmp sheetparser sh tools/run_r9.sh $O $2 > runs/$O.log 2>&1 &"
