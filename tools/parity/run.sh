#!/bin/sh
# 대조 전체 실행(맥에서): elgrim 동기화 -> 파이썬 덤프(docker) -> 맥으로 가져오기 -> JS 덤프 -> 비교표
# 사용: tools/parity/run.sh [이름...]     결과: tools/parity/out/compare.md, compare.json
# 사전: (cd web && npm install), elgrim 에 data/synth 가 있어야 한다(맥에는 rsync 로 data/synth 를 가져와 둔다: jpegdiff 용)
set -e
cd "$(dirname "$0")/../.."
rsync -a --exclude .git --exclude runs --exclude data/synth --exclude tmp --exclude node_modules --exclude 'tools/parity/out*' ./ elgrim:~/sheetparser/
ssh elgrim "cd ~/sheetparser && docker run --rm -u \$(id -u):\$(id -g) --network host -v \$HOME/sheetparser:/w -w /w -e PYTHONPATH=/w sheetparser python tools/parity/dump_py.py tools/parity/out $*"
rsync -a elgrim:~/sheetparser/tools/parity/out/ tools/parity/out/
(cd tools/parity && REPS=3 node dump_js.mjs out $* && node compare.mjs out --md out/compare.md)
