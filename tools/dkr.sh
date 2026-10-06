#!/bin/sh
# elgrim 도커에서 명령 실행 (rsync 포함): tools/dkr.sh <python args...>
rsync -aq --exclude .git --exclude runs --exclude data/synth --exclude tmp ./ elgrim:~/sheetparser/
ssh elgrim "cd ~/sheetparser && docker run --rm -u \$(id -u):\$(id -g) --network host -v \$HOME/sheetparser:/w -w /w -e PYTHONPATH=/w -v /tmp:/tmp sheetparser $*"
