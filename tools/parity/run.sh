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

# --- 2단계: 최종 spec 대조(A) + 브라우저 OCR 종단(B). 서버 재판독은 ssh -L 터널(18003, 18001)이 필요하다.
#   ssh -f -N -L 18003:127.0.0.1:18003 -L 18001:127.0.0.1:18001 elgrim
#   ssh elgrim "cd ~/sheetparser && docker run --rm -u \$(id -u):\$(id -g) --network host -v \$HOME/sheetparser:/w -w /w -e PYTHONPATH=/w sheetparser python tools/parity/dump_spec_py.py tools/parity/out"
#   ssh elgrim "cd ~/sheetparser && docker run ... python tools/parity/gen_gt.py tools/parity/out"      # 칸 단위 정답
#   rsync -a elgrim:~/sheetparser/tools/parity/out/{spec_py,gt} tools/parity/out/
#   (cd tools/parity && node spec_js.mjs out i && node compare_spec.mjs out i --md out/cmp_spec_i.md   # 모드 i
#                    && node spec_js.mjs out ii && node compare_spec.mjs out ii --md out/cmp_spec_ii.md # 모드 ii
#                    && node ocr_run.mjs out client0 && node suspect_eval.mjs out                       # 클라이언트 OCR 단독 + 규칙 평가
#                    && node ocr_run.mjs out srv --server && node summarize_ocr.mjs out srv)            # 서버 재판독 종단
#   채점: rsync ocr_srv 를 elgrim 으로 보낸 뒤 docker 안에서 sh tools/parity/score_ocr.sh tools/parity/out/ocr_srv
