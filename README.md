# sheetparser

표가 있는 문서(PDF, 사진, 스캔 PDF)를 구글 시트로 옮긴다. 선 위치, 열 너비/행 높이, 병합, 배경색, 글자 크기, 굵게, 표 밖 제목/서명 줄까지 원본 페이지와 겹치도록 만드는 것이 목표다. 구조(격자)는 CV나 PDF 벡터로 먼저 확정하고, 글자는 PDF 텍스트 레이어 또는 비전 모델(vlm)로 채운다. 모델이 구조를 만들지 않는다.

## 구조

```
입력(pdf / jpg / png)
   |  convert.detect
   +-- pdf_vector (텍스트 레이어 + 벡터 선) --> pdfvec.py   텍스트 줄, 굵기(가짜 굵게 포함), 선/채움/이미지 추출
   |                                            pipeline.run_pdf_page --+
   +-- pdf_scan   (텍스트 없는 PDF)  -> 300dpi 렌더 -> 10px/mm 정규화 --+--> photopage.run_page(kind=pdf_scan, 원근 보정 생략)
   +-- photo      (jpg/png)          -> preprocess.rectify(원근 보정) --+--> photopage.run_page
                                         grid.py 격자 / style.py 서식 / ocr.py vlm 호출
                       v
                  layout.build_page_spec   표 + 표 밖 블록 + 이미지 -> 페이지 전체 격자 (PageSpec v2)
                       v
                  upload.py  -> Apps Script 웹앱(apps_script/Code.gs) -> 구글 시트 (create / pdf / delete / list)
                       v
                  verify.py (pdf_vector) / verify_photo.py (photo, pdf_scan)
                       시트를 A4 100% PDF로 내보내 원본과 겹쳐 채점, 나란히 PNG 저장
```

파일: `sheetparser/` 파이프라인 본체, `apps_script/` 시트 작성 웹앱, `tools/` 실행/정리/보고 스크립트, `docs/SPEC.md` 명세, `docs/RESULTS.md` 최신 결과.

## 설치와 실행

맥에는 numpy 등 C 확장이 막혀 있어 실행은 elgrim의 docker `sheetparser` 이미지(opencv, pymupdf, fonts-nanum)에서 한다. vlm 서버(`127.0.0.1:18001`, OpenAI 호환)는 같은 호스트에서 `--network host`로 접근한다.

```sh
# 맥: 동기화 + 실행 (60초 넘으면 tools/dkbg.sh 로 백그라운드 실행 후 로그 폴링)
tools/dk.sh -m sheetparser convert data/photos/sched_09.jpg -o runs/convert/sched_09 --title v3_sched_09
tools/pull.sh                      # elgrim runs/ 를 맥으로 가져오기
tools/dk.sh tools/cleanup.py --keep-prefix v3_   # sheetparser-poc 폴더에서 v3_ 로 시작하지 않는 시트 삭제
```

`.env` (git 제외)에 `SHEETS_WEBAPP_URL`, `SHEETS_WEBAPP_KEY`가 필요하다. Apps Script는 `apps_script/Code.gs`를 붙여 웹 앱으로 배포한다(실행 계정 본인, 접근 모든 사용자). 서비스는 Sheets(v4) 고급 서비스를 켠다.

```sh
python -m sheetparser convert <input.pdf|jpg|png> [-o runs/convert/<name>] [--title T] [--verify] [--keep|--delete]
python tools/accuracy.py photo <spec.json> <name>      # 검증 없이 만든 spec 의 정답 채점(오프라인)
```

입력 종류는 자동 판별한다. 기본 동작은 스펙 생성 -> 시트 업로드(create 1회) -> URL과 소요 시간/vlm 사용량(호출 수, 토큰) 출력이다. `-o` 폴더에 PageSpec JSON과 `convert.json`을 저장한다. `--verify`를 주면 시트를 A4 PDF로 내보내 원본과 겹쳐 채점하고(시트 PDF, 나란히 PNG `*_side.png` 저장) 사진은 정답(`gt_content.json`) 채점도 한다. 시트는 기본으로 남기고 `--delete`를 주면 끝에 지운다(검증 안 해도 동작). 이전 서브명령 `run / upload / verify / score / synth / bench`도 그대로 쓸 수 있다.

vlm 호출은 llama.cpp `grammar`(GBNF)로 형식을 강제한 압축 텍스트(`행번호|칸|칸`, 한 줄에 한 행)를 쓰고, CV가 잉크 있다고 본 칸만 요청한다. 속도 측정은 `tools/run_r4.sh`.

## 단위 규칙과 실측 보정값

- 시트 px = mm x 96/25.4 (A4 폭 210mm = 794px), PDF pt -> px = pt x 96/72. 사진은 용지 외곽으로 mm를 구하고, 검출 실패 시 표 폭을 근거로 한 추정(`mm_scale_from_table_estimate` 플래그).
- 내부 래스터는 10px/mm(2100x2970). PDF 선 마스크는 20px/mm. 스캔 PDF는 300dpi로 렌더한 뒤 10px/mm로 줄인다.
- 열 너비: 시트는 (px+1)x0.75pt로 그리므로 업로드 직전에 각 열에서 1px를 뺀다.
- 글자 크기: 시트 PDF 내보내기는 글자를 0.975배로 그린다. 시트에 보내는 정수 pt = round(원본 pt / 0.975), 칸 폭에 안 들어가면 한 단계 내린다.
- 글자 기준선: 시트 글자가 원본보다 pt당 0.082mm 내려가므로 표 밖 블록 bbox를 그만큼 올린다.
- 래스터 선 두께: 이진화/블러로 선이 0.2mm 굵게 측정되어 두께 판정 전에 뺀다. 두께 기준 <0.35mm SOLID, <0.7 MEDIUM, 이상 THICK.
- 표 밖 블록 행 높이: 시트 글줄 높이 = 글자 px x 1.3. 원본 행이 이보다 낮으면 위아래 빈 공간으로 넓힌다(표 선, 다른 블록과 겹치지 않게). 병합 칸은 넘친 글자를 자르므로 정렬 방향으로 가로 여유(굵으면 14%, 아니면 7%, +1mm)를 둔다.
- 굵기: 굴림 같은 폰트는 이름에 Bold가 없고 텍스트를 fill + stroke(렌더 모드 2, `get_texttrace()`의 type=1, linewidth>0)로 한 번 더 그려 굵게 만든다. `pdfvec.fake_bold_keys`가 stroke로 그려진 글자 원점을 모아 굵게로 판정한다. 사진은 잉크 두께/높이 비율(>0.135)을 쓰고, 머리글은 행 단위, 본문은 열 단위 다수결로 통일한다.

## 운영 (elgrim 컨테이너 2개 상주)

`convert` 기본 OCR 백엔드는 `auto`다. 사진은 paddle(PaddleOCR-VL-1.6), 스캔 PDF와 paddle 결과에 이상(요청 실패, 잉크 있는 칸이 빈 글자, 80자 초과 칸, 표 OCR 실패)이 있는 장은 32B(Qwen3-VL)로 읽는다. `--ocr-backend qwen32b` 등으로 고정할 수 있다.

| 컨테이너 | 모델 | 포트 | GPU | 메모리 |
|---|---|---|---|---|
| vlm | Qwen3-VL-32B Q4_K_M + mmproj f16 | 127.0.0.1:18001 | A4000 + TITAN Xp (`-ts 14,14`) | A4000 약 12.9GB, TITAN 약 10.2GB (부하 시 A4000 약 +1.2GB) |
| paddle | PaddleOCR-VL-1.6 + mmproj | 127.0.0.1:18003 | A4000 | 약 2.0GB |

합계(부하 중 최대): A4000 14,973 / 16,376MiB (여유 약 1.4GB), TITAN Xp 10,243 / 12,288MiB, GTX 1050은 미사용.

재기동 명령(둘 다 `--restart on-failure:5`):

```
docker run -d --name vlm --gpus all -e CUDA_VISIBLE_DEVICES=0,1 -v /home/elgrim/models/qwen3vl:/m -p 127.0.0.1:18001:8080 --restart on-failure:5 ghcr.io/ggml-org/llama.cpp:server-cuda -m /m/qwen3vl-32b-q4_k_m.gguf --mmproj /m/mmproj-32b-f16.gguf -ngl 99 -ts 14,14 -c 8192 -ctk q8_0 -ctv q8_0 -fa on --jinja --parallel 1 --host 0.0.0.0 --port 8080 -a qwen3-vl-32b
docker run -d --name paddle --gpus all -e CUDA_VISIBLE_DEVICES=0 -v /home/elgrim/models/paddle:/m -p 127.0.0.1:18003:8080 --restart on-failure:5 ghcr.io/ggml-org/llama.cpp:server-cuda -m /m/gguf/PaddleOCR-VL-1.6-GGUF.gguf --mmproj /m/gguf/PaddleOCR-VL-1.6-GGUF-mmproj.gguf -ngl 99 -c 8192 --parallel 4 --host 0.0.0.0 --port 8080 --jinja -a paddle
```

주의: 실측은 vlm을 먼저, paddle을 나중에 올린 순서다(반대 순서는 시험하지 않았다). 32B 컨텍스트는 8192이고 가장 긴 요청은 약 4,300 프롬프트 + 약 870 생성 토큰이다. 복구(예전 단독 설정)는 `-c 16384`, KV 옵션 제거, paddle 컨테이너 제거.

## 한계

- 사진은 paddle로 장당 약 10초(변환 2초 + 업로드 8초), 스캔 PDF는 32B 표 호출이 필요해 약 60초다. paddle이 내려가 있으면 auto는 장마다 32B로 되돌아간다(장당 40~55초).
- pdf_scan/photo는 서명 같은 떠 있는 이미지를 시트에 재현하지 않는다(PDF 벡터만 재현). 서명 줄은 글자만 남는다.
- 사진/스캔의 굵기 판정은 잉크 두께 기반이라 저해상도에서 머리글 굵기를 놓치거나 숫자 열을 굵게 오판할 수 있다. 제목은 "표 가운데의 본문보다 1.2배 이상 큰 글줄은 굵게" 규칙을 쓴다.
- 시트 쪽 글꼴(Calibri/Nanum Gothic 대체)이 원본(굴림 등)과 달라 글줄 폭이 조금 다르다. 좁은 열의 머리글은 한글이 줄바꿈될 수 있다.
- 병합 셀 안 글자는 넘치지 않고 잘리므로 가로 여유를 추정으로 둔다. 회색 계열 배경 외의 복잡한 배경, 이중선 일부, 여러 표가 있는 페이지는 미지원(`extra_table_ignored`).
- Apps Script 웹앱이 가끔 404/상태 메시지로 응답한다. `upload.call`이 재시도하지만 create가 중복 생성될 수 있어 `tools/cleanup.py`가 같은 이름 중 최신만 남긴다.
