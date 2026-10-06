# 브라우저 OCR 가능성 실측 (2026-10-06)

질문: 브라우저(클라이언트)에서 OCR을 돌리고 서버(elgrim)는 격자 검출만 하는 구조가 되는가. 기존 파이프라인 코드는 바꾸지 않았다. 추가한 것은 `tools/browserocr/`(백엔드, 채점 스크립트, 테스트 페이지)와 `docker/Dockerfile.bro`(별도 이미지 태그 `sheetparser:bro`, 기존 `sheetparser` 이미지는 그대로)뿐이다. vlm/paddle 컨테이너는 건드리지 않았다. 시트 업로드 없음.

## 조건

- 입력 13개(12라운드 회귀셋): 스캔 PDF 3(attendance/activity/meal), 300dpi PNG 3, 근무일정표 사진 sched_09~12, 서식 사진 form_activity/attendance/meal.
- 칸 크롭은 현행 파이프라인(`photopage._run_page` -> `ocr.paddle_cells` -> `_ink_tight`) 그대로 만들고, 칸 읽기 함수 `ocr.paddle_read`만 바꿔 끼웠다(`tools/browserocr/backend.py`, `OCR.BACKEND='paddle'` 고정이라 32B 폴백/한자 재질의 없음, 순수 백엔드 결과). 채점은 `tools/accuracy.py`, `tools/struct_eval.py` 그대로(`tools/browserocr/run_all.sh`, 요약 `summarize.py`, 오류 분류 `errors.py`).
- 후보 1: `korean_PP-OCRv5_mobile_rec`(HF `monkt/paddleocr-onnx` languages/korean, 13.4MB, 사전 11,945자) + det. det는 HF의 `PP-OCRv5_server_det`(88MB) 와, 공식 `PaddlePaddle/PP-OCRv5_mobile_det`(inference.json)를 elgrim에서 paddle2onnx로 변환한 mobile det(4.8MB) 둘 다. onnxruntime(CPU)로 elgrim에서 실행.
- 후보 2: Tesseract 5.5 CLI(LSTM, kor), tessdata_best(12.5MB)/tessdata_fast(1.7MB). Tesseract.js와 같은 엔진이다(다만 바이너리와 정수/실수 모델 경로는 다르므로 대리지표).
- 여러 줄 칸 처리: (a) `split` = 가로 투영 줄 분할 후 줄마다 rec, (b) `det` = DB 검출 -> 줄 묶기 -> rec. 둘 다 시도.
- 개선 시도(후보당 최대 3회): PP-OCRv5는 (1) 좁은 칸 최소 폭 패딩(악화, `_m`), (2) 표선 잔재 제거 `clean_rules`(가로 50px 이상 선, 세로 선; 접미사 `2`), (3) det가 빈 결과면 줄 분할 rec로 폴백(`f`). Tesseract는 표선 제거 + 2배 확대(`c`, 악화), 표선 제거만(`2`), psm 6/7(줄 분할).
- 서버: elgrim EPYC 7642 48코어. 브라우저: Aside 브라우저(Chrome 153), Mac M5 Pro 24GB(hardwareConcurrency 15), onnxruntime-web 1.30.0, tesseract.js 7.0.0(CDN), 모델/크롭은 localhost 서빙.

## A. 정확도 (elgrim CPU, 가중치가 같아 브라우저 정확도의 대리지표)

"칸별"은 PDF 6건 400칸의 `struct_eval.text_ok`, "글자"는 `accuracy.py` 글자 일치(3,472자), 일정표는 `content_score` 칸, 서식은 필수 문구.

| 백엔드 | PDF 6건 칸별 | PDF 6건 글자 | 일정표 4장 | 서식 3장 | 합계(칸/문구 708) | 구조 일치 |
|---|---|---|---|---|---|---|
| 현행 PaddleOCR-VL (서버) | 400/400 | 3462/3472 (99.7%) | 290/290 | 18/18 | 708 (100%) | 6/6 |
| PP-OCRv5 kor rec + mobile det (det 경로, 표선 제거, 빈 결과 폴백) `pp_det2f_mob` | 389/400 | 3445/3472 (99.2%) | 289/290 | 18/18 | 696 (98.3%) | 6/6 |
| 같은, server det (88MB) `pp_det2f` | 389/400 | 3445/3472 | 289/290 | 18/18 | 696 | 6/6 |
| PP-OCRv5 kor rec, 줄 분할만(det 없음, 표선 제거) `pp_split2` | 394/400 | 3446/3472 | 286/290 | 16/18 | 696 (98.3%) | 6/6 |
| Tesseract kor best, 줄 분할 psm7, 표선 제거 `tess_best72` | 392/400 | 3441/3472 | 226/290 | 16/18 | 634 (89.5%) | 6/6 |
| Tesseract kor fast, 줄 분할 psm7, 표선 제거 `tess_fast72` | 373/400 | 3417/3472 | 218/290 | 13/18 | 604 (85.3%) | 6/6 |
| Tesseract kor fast, 칸 통째 psm6, 전처리 없음 `tess_fast6` (Tesseract.js 기본에 가장 가까움) | 364/400 | 3394/3472 | 163/290 | 11/18 | 538 (76.0%) | 6/6 |

개선 시도 전/중간 값(참고):

| 변형 | PDF 칸별 | 글자 | 일정표 | 서식 |
|---|---|---|---|---|
| pp_whole (줄 분할 없이 칸 통째 rec) | 377/400 | 2938/3472 | 275/290 | 13/18 |
| pp_split (표선 제거 전) | 394/400 | 3445/3472 | 266/290 | 16/18 |
| pp_split_m (최소 폭 패딩, 악화) | 385/400 | 3439/3472 | 273/290 | 18/18 |
| pp_det (server det, 전처리 없음) | 389/400 | 3439/3472 | 288/290 | 18/18 |
| tess_best6 / best7 / best7c(2배 확대) | 386 / 392 / 347 | 3428 / 3431 / 3387 | 168 / 157 / 205 | 13 / 16 / 12 |

- 구조(행/열/병합)는 서버 CV가 정하므로 모든 변형에서 6/6 일치(OCR과 무관).
- PP-OCRv5 kor는 현행 대비 칸 정확도 약 -1.7%p(708칸 중 12칸). 일정표(숫자/시각 중심)는 거의 같고, 손실은 활동일지/출근부의 긴 칸(40자 안팎, 숫자+한글 혼합 3줄)에 몰려 있다.
- Tesseract kor는 시각/날짜 숫자 칸에서 크게 무너진다(`09:00~14:30` -> `0900 ~ 14:30`, `09500`, `10/8` -> `1078`). 한글 단어 위주 PDF 칸은 쓸 만하다(392/400).
- 정확도 목표가 "현행 수준"이면 Tesseract는 탈락이고 PP-OCRv5 kor도 100%는 아니다. 12칸은 사람 확인 또는 서버 재질의 대상이다(아래).

## 오류 유형 (틀린 칸 수, 규칙 분류 `errors.py`)

| 변형 | 틀린 칸 | 한자 혼입 | 숫자/기호 | 줄바꿈 | 빈 칸 | 긴 칸(18자+) | 표선/기호 잔재 | 한글 오독 | 서식 문구 누락 |
|---|---|---|---|---|---|---|---|---|---|
| PaddleOCR-VL 현행 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 | 0 |
| pp_det2f_mob | 12 | 0 | 0 | 0 | 0 | 11 | 0 | 1 | 0 |
| pp_split2 | 12 | 0 | 1 | 0 | 1 | 7 | 0 | 1 | 2 |
| tess_best72 | 74 | 0 | 48 | 0 | 8 | 7 | 1 | 8 | 2 |
| tess_fast72 | 102 | 0 | 61 | 0 | 5 | 19 | 1 | 11 | 5 |
| tess_fast6 | 166 | 0 | 76 | 0 | 10 | 17 | 10 | 46 | 7 |

(줄바꿈은 정답 대조에서 공백을 지워 비교하므로 0. 한자 혼입은 PP-OCRv5 kor와 Tesseract kor 모두 0건: 현행에서 `paddle_read`가 32B로 재질의하던 한자 혼입 문제는 사전이 한글/영문/숫자 위주인 이 모델에는 해당 없음.)

- 긴 칸(PP): 활동일지 6, 7, 9, 10, 12번 행 마지막 열 5칸(사진/스캔 각각이라 10~11건). 원인은 숫자 한 글자 오독 두 종류다. `2-10` -> `2-1이`(0->이), `2-7` -> `2-기`(7->기). 현행 PaddleOCR-VL은 한 번도 안 틀린 칸이다. 같은 오독이 사진/스캔에서 똑같이 반복되므로 입력 노이즈가 아니라 모델 성향이다.
- 빈 칸: PP는 det가 못 잡거나 rec가 한 글자 짧은 칸에 빈 CTC 결과를 내는 경우(예: 머리글 `요일`, 숫자 `4.0`). det 빈 결과 시 줄 분할 rec 폴백으로 대부분 해결(`2f`).
- 표선/기호 잔재: `_ink_tight` 뒤에도 칸 밑줄/세로선이 남아 `날짜 __`, `-`, `|`가 붙는다(pp_split 12건, tess_best6 14건). 가로 50px 이상/세로선 제거로 PP는 0건(`clean_rules`, 순수 CV라 브라우저에서도 Canvas/typed array로 구현 가능, 이번 브라우저 페이지에는 아직 넣지 않았다).
- 숫자/기호(Tesseract): 시각 `HH:MM~HH:MM`에서 콜론 누락/오인(`0`->`5`,`2`), 날짜 `/` 누락(`11/5`->`1175`). 숫자 whitelist나 후처리 정규식으로 줄일 여지는 있으나 이번엔 시도하지 않았다.
- 여러 줄 칸(줄바꿈): 줄 분할/det 모두 줄 수는 맞았고 줄바꿈 오류는 없다. 줄 내부 글자 오독만 남는다.
- 칸이 좁을 때 최소 폭 패딩은 오히려 `4`, `목`, `화` 등 한 글자 칸을 빈 결과로 만든다(시도 1 악화 사례, 이유는 흰 여백이 늘면 rec 입력에서 글자 비율이 줄어서로 추정).

## B. 브라우저 속도 (맥, Aside 브라우저, CDN 라이브러리 + localhost 모델)

크롭은 현행 파이프라인의 칸 크롭을 PNG로 저장한 것(sched_09 62개 1.34MB, activity_09_300dpi 91개 0.73MB). 시간은 "칸 전체 처리(크롭 디코딩 제외, OCR만)", 2회 반복 중 빠른 쪽(첫 회는 워밍업 JIT 포함이라 느림). 모델 로드는 로컬 서빙 기준(네트워크 제외).

| 구성 | 백엔드/스레드 | sched_09 62칸 | activity 91칸 | 칸당 p50/p95 | 모델 다운로드 | 모델 로드(초기화) | Python 결과와 일치 |
|---|---|---|---|---|---|---|---|
| rec + 줄 분할 | wasm 4스레드 | 1.17s (첫 회 1.48s) | 1.90s (첫 회 3.43s) | 13~17 / 37~99ms | 13.4MB | 0.4~1.4s | 59/62, 86/91 |
| rec + mobile det | wasm 4스레드 | 0.99s (첫 회 2.26s) | 1.99s (첫 회 3.48s) | 12~14 / 31~80ms | 18.2MB | 0.4s | 60/62, 88/91 |
| rec + mobile det | wasm 2스레드(저사양 근사) | 1.30s (첫 회 2.71s) | 3.10s (첫 회 4.63s) | 16~21 / 38~140ms | 18.2MB | 0.4s | 60/62, 88/91 |
| rec + mobile det | wasm 1스레드 | 3.50s | - | 44 / 137ms | 18.2MB | 0.4s | 60/62 |
| rec + mobile det | WebGPU | 1.00s (첫 회 1.30s) | 2.22s | 15~19 / 24~64ms | 18.2MB | 0.65s (rec 세션 생성 0.47~1.9s) | 60/62, 88/91 |
| rec + server det(88MB) | wasm 4스레드 | 6.31s | 10.65s | 73~84 / 229~464ms | 101.4MB | 0.7s | 62/62, 91/91 |
| Tesseract.js fast (psm6, 칸 통째) | wasm 단일 워커 | 2.07s | 4.17s | 20~25 / 68~175ms | 1.7MB (+코어 wasm 수 MB) | 0.2s | 40/62, 76/91 |
| Tesseract.js best | - | 실행 실패 | 실행 실패 | - | 12.5MB | - | `missing function: DotProductSSE`(tesseract.js 7 기본 코어가 best(float) 모델 미지원) |

- ORT 런타임 자체(`ort-wasm-simd-threaded.wasm`) 3.07MB(CDN). 첫 로드 네트워크 시간 참고: HF에서 rec.onnx 13.4MB를 이 맥에서 받는 데 2.3초. 모델/런타임은 브라우저 캐시되므로 재방문은 0.
- 멀티스레드는 COOP/COEP(교차 출처 격리) 응답 헤더가 있어야 한다(`tools/browserocr/serve.py`가 붙임). 격리가 없으면 1스레드로 떨어져 3배 이상 느리다(위 1스레드 3.5s). 서비스 도메인(예: GitHub Pages)은 이 헤더를 못 붙이는 경우가 많다는 점이 배포 변수다.
- WebGPU는 이 작은 입력(칸당 50ms 미만)에서 wasm 4스레드보다 빠르지 않다(1.0s vs 1.0s, 줄이 짧고 텐서가 작아 전송/디스패치 오버헤드가 지배). 세션 생성이 길 수 있다.
- det 경로 mobile det: server det 대비 6배 빠르고 정확도 동일(둘 다 389/400, 289/290, 18/18). 브라우저에는 mobile det만 쓴다.
- 브라우저 페이지(JS)는 Python 구현과 `clean_rules`가 빠진 것을 제외하면 같은 전처리/후처리라 일치율이 높다(det 경로 server det 62/62, 91/91). 차이는 Canvas 리사이즈 vs cv2 보간이다.
- 사용자 체감(맥 M5 Pro 기준): 서버 CV 1.2초 + 크롭 전송(sched 1.3MB) + 브라우저 OCR 1~2초(워밍업 포함 2~3.5초) 이면 2~5초대. 현행 서버 전체 p50 2.8초(LOADTEST N=1)와 단건은 비슷하다. 차이는 동시 부하에서 난다(C).

## C. 서버 격자 검출(OCR 제외) 단독 (`tools/browserocr/cvload.py`, `photopage.run_page(ocr=False)`, 업로드 없음)

사진 8장(7 jpg + activity 300dpi png) 순환, 프로세스 풀 닫힌 루프, elgrim 48코어(paddle/vlm 유휴, GPU 사용 3%).

| 동시 | 요청 | 처리량(장/분) | 지연 p50 / p95 / max | CPU 평균(최대) | loadavg1 최대 |
|---|---|---|---|---|---|
| 1 | 16 | 52 | 1.25 / 1.43 / 1.44s | 20% (100%) | 7.6 |
| 8 | 48 | 249 | 1.98 / 2.41 / 2.59s | 78% (100%) | 18.4 |
| 32 | 96 | 367 | 4.74 / 6.60 / 6.81s | 94% (100%) | 50.2 |

스캔 PDF(300dpi 렌더 + 정규화 + CV): 동시 1 -> 58건/분(attendance 1.33s, meal 0.74s), 동시 8 -> 264건/분(2.17s / 1.14s).

- 비교(LOADTEST.md 사진 경로, OCR 포함): 동시 1 22장/분, 동시 4~32 약 55~60장/분(paddle 포화). CV만 하면 동시 8 에서 약 250, 동시 32 에서 약 370장/분으로 4~6배, 하루 환산 약 36만~53만장(24시간 포화 가정, 이론 상한). 스캔 PDF는 기존 12라운드 paddle 경로와 비교해 병목이 paddle/GPU에서 CPU로 옮겨 간다.
- CV는 CPU 바운드다. N=32에서 p50 4.7초, 로드 50(48코어 초과)이라 OpenCV 내부 스레드 오버섭스크립션이 있다(프로세스당 `cv2.setNumThreads(1)` 로 처리량이 더 오를 수 있으나 이번에 시도하지 않음).
- 업로드(Apps Script)는 별도 병목이다(LOADTEST E, 일 3,200개). 브라우저 OCR로 바꿔도 시트 생성 한도는 그대로이고, 클라이언트가 글자를 서버로 돌려 보내 업로드하는 왕복이 하나 더 생긴다.

## 주요 판단 근거 요약

1. 구현 가능성: 가능하다. onnxruntime-web으로 PP-OCRv5 kor rec(13.4MB) + mobile det(4.8MB)는 맥 브라우저에서 한 장 1~2초(wasm 4스레드, 워밍업 포함 2~3.5초)이고 2스레드로 줄여도 1.3~3.1초.
2. 정확도: 현행 PaddleOCR-VL 100% 대비 PP-OCRv5 kor는 98.3%(12칸 오류). 활동일지 긴 칸의 숫자/한글 한 글자 오독이 대부분이다. Tesseract kor는 85~90%(일정표 시각/날짜 숫자 무너짐)이고 tesseract.js에서는 tessdata_best가 실행되지도 않는다. Tesseract는 후보에서 제외가 타당하다.
3. 서버 이득: 서버는 CV만 하면 동시 처리량이 약 4~6배(55~60장/분 -> 약 250~370장/분)이고 paddle/GPU 의존이 사라진다. 대신 칸 크롭을 클라이언트로 내려보내야 한다(1~1.3MB/장, PNG 기준. JPEG/이진화/축소로 줄일 여지는 미측정).
4. 정확도를 더 올릴 후보: 확신도 낮은 칸(rec 평균 확률)이나 숫자+한글 혼합 긴 칸만 서버(paddle)에 재질의하는 하이브리드. 이번에는 rec 확률 기반 게이트를 측정하지 않았다.

## 한계

- 브라우저 정확도는 직접 채점하지 않고 elgrim CPU onnxruntime 결과로 대리했다(같은 가중치, JS 포팅의 Canvas 리사이즈가 cv2와 달라 칸 단위로 몇 칸 다를 수 있음. 일치율 det 경로 server det 62/62, 91/91, mobile det 60/62, 88/91).
- `@paddleocr/paddleocr-js` SDK 자체는 실행하지 않았다(OpenCV.js 번들/모델 호스팅 의존이라 CDN 단독 로드가 불안정해 보였음). 같은 ONNX를 onnxruntime-web으로 직접 돌려 같은 가중치/런타임 경로를 근사했다. SDK의 한국어 모델 지원 여부와 전처리 세부(박스 후처리 unclip/폴리곤)는 확인하지 않았다.
- Tesseract는 Python/CLI(5.5)와 tesseract.js 7의 코어/모델 형식이 달라 정확도는 대리지표일 뿐이다. 브라우저에서는 fast 모델만 돌았다.
- 속도는 한 대의 맥(M5 Pro, 15스레드), 단일 사용자, 로컬호스트 서빙 기준이다. 스레드 2개 제한은 저사양 폰/노트북의 대략적 근사일 뿐이며 실제 저가 기기, 모바일 브라우저, 메모리 압박은 측정하지 않았다. 반복은 2회다.
- 입력이 13건이고 다수가 같은 양식이라(스캔/PNG 6건은 같은 3문서의 복제) 일반화에는 한계가 있다. 12칸 오류도 사실상 활동일지 한 칸 유형의 반복이다.
- clean_rules(표선 제거)는 Python에서만 검증했고 브라우저 페이지에는 아직 없다. 그 효과(일정표 266->286)가 브라우저에서도 같다고 가정한다.
- 서버 CV 부하는 닫힌 루프, 사진 8개 순환, 1회 측정이며 OpenCV 스레드 설정을 조정하지 않았다. 크롭 전송, 웹서버, 네트워크는 포함하지 않았다.
- 개인정보 관점: 학교 서류 크롭이 클라이언트로 내려가거나 외부 CDN 라이브러리(jsdelivr)를 쓰는 구조의 운영 판단은 하지 않았다.

## 재현

```sh
# elgrim: 모델/언어데이터 ~/bro (tools/browserocr/fetch_models.sh), 이미지 docker build -f docker/Dockerfile.bro -t sheetparser:bro docker
tools/browserocr/dk.sh sh tools/browserocr/run_all.sh pp_det2f_mob   # base | pp_split2 | pp_det2f | pp_det2f_mob | tess_best72 ...
python3 tools/browserocr/summarize.py runs/bro base pp_det2f_mob     # runs/bro/<변형>.log 필요
python3 tools/browserocr/errors.py runs/bro base pp_det2f_mob
# CV 단독 부하 (서버 컨테이너에서)
python tools/browserocr/cvload.py --n 8 --reqs 48 --tag cv8
# 브라우저: 저장소 루트에서 python3 tools/browserocr/serve.py 18765 -> http://localhost:18765/tools/browserocr/index.html
#   (tmp/bro_models: rec_ko.onnx, det_mobile.onnx, dict_ko.txt, best|fast/kor.traineddata, tmp/bro_crops: 백엔드를 BRO_CROPS=<폴더> 로 돌려 칸 크롭+manifest 생성)
#   콘솔에서 await bench({engine:'ort', ep:'wasm', threads:4, set:'sched_09', mode:'det', det:'det_mobile.onnx', reps:2})
```
