#!/bin/sh
# elgrim 에서 sheetparser:bro 이미지로 실행 (모델은 ~/bro 마운트): tools/browserocr/dk.sh <python args...>
ssh elgrim "cd ~/sheetparser && docker run --rm -u \$(id -u):\$(id -g) --network host -v \$PWD:/w -v \$HOME/bro:/bro -w /w -e PYTHONPATH=/w -e HOME=/tmp sheetparser:bro $*"
