#!/bin/sh
# elgrim 에서 실행: 모델/언어데이터 내려받기 (~/bro)
mkdir -p ~/bro/models ~/bro/tess && cd ~/bro/models
B=https://huggingface.co/monkt/paddleocr-onnx/resolve/main
curl -sL -o rec_ko.onnx $B/languages/korean/rec.onnx
curl -sL -o dict_ko.txt $B/languages/korean/dict.txt
curl -sL -o rec_ko_cfg.json $B/languages/korean/config.json
curl -sL -o det_v5.onnx $B/detection/v5/det.onnx
curl -sL -o det_cfg.json $B/detection/v5/config.json
ls -l; cat rec_ko_cfg.json det_cfg.json; head -3 dict_ko.txt; wc -l dict_ko.txt
curl -s https://huggingface.co/api/models/PaddlePaddle/PP-OCRv5_mobile_det | python3 -c 'import sys,json;print([s["rfilename"] for s in json.load(sys.stdin)["siblings"]])'
curl -s https://huggingface.co/api/models/PaddlePaddle/korean_PP-OCRv5_mobile_rec | python3 -c 'import sys,json;print([s["rfilename"] for s in json.load(sys.stdin)["siblings"]])'
cd ~/bro/tess
for t in best fast; do curl -sL -o kor_$t.traineddata https://github.com/tesseract-ocr/tessdata_$t/raw/main/kor.traineddata; done
ls -l; tesseract --version 2>&1 | head -2; tesseract --list-langs
