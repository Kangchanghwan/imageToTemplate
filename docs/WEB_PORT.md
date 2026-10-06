# 브라우저 이식(1단계): 사진/스캔 경로 CV 를 OpenCV.js 로

목표는 사진/스캔 -> 시트 spec 파이프라인 전체를 브라우저에서 기존 Python 과 같은 결과로 돌리고, 원본 사진은 서버로 보내지 않고 의심 칸 크롭만 보내는 구조다. 이 문서는 1단계(대조 하네스 + 용지 검출, 원근 보정, 선 검출, 격자, 병합 판정, 칸 생성/빈 칸 판정)의 결과다. Python 코드는 바꾸지 않았다(덤프 스크립트 `tools/parity/dump_py.py` 가 같은 함수를 같은 순서로 호출한다). 시트 업로드/OCR 없음, vlm/paddle 컨테이너는 건드리지 않았다.

## 환경과 버전

| 항목 | Python 쪽 (elgrim `sheetparser:latest`) | JS 쪽 |
|---|---|---|
| OpenCV | cv2 **5.0.0** (opencv-python-headless, SIMD 디스패치 SSE4/AVX/AVX2/AVX512, IPP 표시 없음) | OpenCV.js **5.0.0** (npm `@techstark/opencv-js` 5.0.0-release.1, 빌드 2026-06-24, wasm) |
| 수치 | numpy 2.5.3 | JS 배열(Float64Array/Float32Array) + `web/src/npy.js` |
| 실행 | `docker run ... sheetparser python tools/parity/dump_py.py` | Node v26.5.0 (`web/`, ES 모듈) |
| 이미지 입출력 | cv2.imread/imwrite | Node 하네스에서만 pngjs(PNG), jpeg-js(JPEG 실험) |

OpenCV 메이저 버전을 5.0.0 으로 맞췄다(4.x 로 맞추려면 elgrim 이미지를 내려야 했다). Mat 은 `tracker()` 로 수명을 관리한다(wasm 힙이라 delete 필수).

## 파일

```
web/package.json, package-lock.json     opencv-js 5.0.0-release.1 (dev: pngjs, jpeg-js)
web/src/cv.js          setCv/getCv(브라우저/Node 공용 주입), tracker, bgr<->Mat
web/src/node_cv.js     Node 에서 opencv-js 로드
web/src/npy.js         numpy/Python 의미 도우미(pyRound=banker's, pyRoundN, arange, npSum(쌍별 합), median, percentile, lstsq)
web/src/preprocess.js  preprocess.py 이식
web/src/grid.js        grid.py 이식 + photopage._extend_left
web/src/style.js       style.py 일부(style_name, analyze)
web/src/front.js       photopage._run_page 앞부분(OCR 제외) + convert._render_scan 의 resize
web/src/exif.js        JPEG EXIF 방향(cv2.imread 는 기본 적용) 읽기/적용 (Node/폴백용)
web/test/npy.test.mjs  도우미 단위 테스트 (npm test)
tools/parity/dump_py.py  Python 덤프(JSON + 보정/평탄화 PNG, 입력 PNG)
tools/parity/dump_js.mjs JS 덤프(같은 JSON)
tools/parity/compare.mjs 단계별 비교기 (out/compare.json, compare.md)
tools/parity/jpegdiff.mjs JPEG 디코더 차이 실험
tools/parity/run.sh      전체 실행(동기화 -> Python -> 가져오기 -> JS -> 비교)
```

## 함수 대응표

| Python | JS | 비고 |
|---|---|---|
| `preprocess._order` | `preprocess.order` | float32 합/차, argmin/argmax 첫 번째 우선 |
| `preprocess.find_paper` | `findPaper` | `np.arange(0.01,0.1,0.005)` 를 `arange` 로 재현(길이는 step 기준 18개, 값은 delta 기준) |
| `preprocess.rectify` | `rectify` | 비율/방향 판정은 float32 norm 모사. flag 문자열 `paper_not_a4_ratio:%.2f` |
| `preprocess.line_mask` | `lineMask` | 가장자리 `int(1.5*ppm)`=15px 0 |
| `preprocess.table_rectify` | `tableRectify(img, keepFrame)` | 사진 경로(photopage)는 `keep_frame=True`. `W=int(...)` 는 절삭 |
| `preprocess.flatten` | `flatten` | percentile(90)은 float64 계산 후 float32 저장(numpy 와 비트 일치 확인), `lstsq` 는 Householder QR, `u**3` 은 `Math.pow`(glibc 와 일치), 곡면은 float32 저장 후 INTER_LINEAR, gain 은 float32 연산 후 절삭 |
| `grid.line_masks` | `lineMasks` | 열기 연산 기본 인자(앵커, BORDER_CONSTANT, 기본 borderValue)를 명시 |
| `grid._groups` | `groups` | |
| `grid._seg_stats` | `segStats` | `round()`=banker's(`pyRound`), `int()`=절삭, 두께 합은 numpy 쌍별 합(`npSum`) |
| `grid.build_grid` | `buildGrid` | 4회 정제 루프의 stale `Hs/Vs` 동작까지 동일, union-find 병합 동일 |
| `grid.trim_outer` | `trimOuter` | `np.median` -> `median` |
| `photopage._extend_left` | `extendLeft` | 원본의 `h` 첫 열 복제 동작 그대로 |
| `style.style_name` | `styleName` | |
| `style._runs`, `_line_bands` | `runs`, `lineBands` | |
| `style.analyze` | `analyze` | empty/med/uni/bgr/h/v/글줄 띠/size_pt/stroke 굵기(`findContours`+`arcLength`)까지. **`hangul_thickness`(hth)는 2단계** |
| `photopage._run_page` 앞부분 | `front.runFront` | 입력 -> 보정 -> (table_rectify) -> 마스크 -> 격자 -> trim -> extend_left -> 평탄화 -> 칸 analyze |
| `convert._render_scan` 의 resize | `front.scanNormalize` | 300dpi PNG -> 10px/mm (INTER_AREA). PDF 렌더 자체는 3단계 |

### 반올림/수치 규칙(이식 때 주의한 곳)

- Python `round(x)` 는 banker's rounding. `pyRound` 로만 쓴다(`Math.round` 금지). `src_bbox` 도 같은 규칙(예 246.5 -> 246, 611.5 -> 612). `round(x, 1)` 은 `pyRoundN`(정확한 이진 값 기준, 정확한 중간값만 짝수로).
- `int()` 는 0 방향 절삭(`Math.trunc`). 이진화 임계 `>40` 은 `cv.threshold(THRESH_BINARY)` 와 동일(포화 `subtract` 후 비교).
- `np.arange(a, b, step)` 길이는 `ceil((b-a)/step)`(step 기준), 값은 `a + i*((a+step)-a)`. (처음에 delta 로 길이를 구해 19개가 나온 버그를 단위 테스트로 잡았다.)
- float32 연산: `_order`, quad `/ sc`, 용지 비율/touch 비교, flatten 의 surf/gain/곱셈은 `Math.fround` 로 단계마다 맞춘다.
- 정렬 안정성: 격자 칸 정렬은 튜플 사전식, `argmax/argmin` 은 첫 번째. JS `sort` 는 안정 정렬. `findContours` 최대 면적 선택은 첫 번째 우선.
- OpenCV 인자 기본값: JS 는 기본 인자가 없는 함수가 많다. `dilate/morphologyEx` 는 `anchor(-1,-1), iterations 1, BORDER_CONSTANT, morphologyDefaultBorderValue()` 를 명시, `GaussianBlur` 는 `BORDER_DEFAULT`, `connectedComponentsWithStats` 는 connectivity 8 + CV_32S, `warpPerspective` borderValue 는 (255,255,255).
- 입력 디코드 이후의 구간은 위 규칙으로 비트 단위로 맞춘다. **디코드 자체(JPEG)는 맞출 수 없다**(아래).

## 대조 방법

`tools/parity/run.sh` 한 번으로 전부 돈다. 입력 26개: 사진 7(sched_09~12, form_activity/attendance/meal), `*_09_300dpi.png` 3(사진 경로), 스캔 PDF 3(`scan_*_09.pdf`: Python 이 300dpi 로 렌더한 PNG 를 JS 입력으로 쓰고 10px/mm 정규화는 JS 가 수행), 합성 벤치 `data/synth/s00~s11_photo.jpg` 12(**24장이 아니라 12장**: 현재 elgrim 의 data/synth 에는 12개뿐이다).

- JS 입력은 Python 이 `cv2.imread` 로 디코드(EXIF 방향 적용)한 BGR 을 무손실 PNG 로 저장한 것이다. 그래서 디코더 차이가 섞이지 않고 보정부터의 차이만 본다. JPEG 디코더 영향은 `jpegdiff.mjs` 로 따로 쟀다.
- 비교 단계: 입력 해시 -> find_paper 꼭짓점 -> rectify(shape, pg_mm, flags) -> table_rectify -> 보정 이미지 -> 선 마스크(hb/vb 포함) -> grid_raw -> trim_outer -> extend_left 후 최종 격자(xs, ys, h, v 두께/이중선, cells, extras) -> flags -> 평탄화 이미지 -> 칸 목록(r,c,rs,cs,_rect,_empty,info) -> 병합.
- Python 덤프는 같은 입력에 `photopage.run_page(ocr=False)` 도 돌려 `src_bbox` 와 칸 rect 가 같은지 교차 확인한다(26개 전부 일치). 덤프 스크립트의 오케스트레이션이 실제 경로와 어긋나지 않았다는 증거다.
- 일치 기준: 정수 구조(행/열 수, 병합, 빈 칸, flags)는 완전 일치. 좌표는 완전 일치가 목표.

## 결과 (입력별)

| 입력 | 종류 | 행x열 | 칸/병합/빈칸 | 구조일치 | 용지꼭짓점 최대차 | 격자 좌표 최대차 | 칸 rect 최대차 | 두께 최대차(mm) | 칸 info 정수필드 불일치(개/최대차) | 칸 info 실수필드 최대차 | 경계 스타일 불일치 | run_page 교차확인 | 보정이미지 평균절대차 / 다른픽셀% / 최대 | 평탄화 평균절대차 / 다른픽셀% / 최대 | JS ms |
|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
| sched_09 | photo | 15x5 | 75/0/14 | 일치 | 0 | 0 | 0 | 0.03171 | 0/0 | 1 | 0/170 | 75/75 | 0.02819 / 4.156 / 2 | 0.05437 / 10.02 / 3 | 1178 |
| sched_10 | photo | 15x5 | 75/0/10 | 일치 | 0 | 0 | 0 | 0.02292 | 0/0 | 1 | 0/170 | 75/75 | 0.02801 / 4.31 / 2 | 0.05121 / 9.422 / 3 | 1219 |
| sched_11 | photo | 14x5 | 70/0/11 | 일치 | 0 | 0 | 0 | 0.0119 | 0/0 | 1 | 0/159 | 70/70 | 0.02682 / 3.817 / 2 | 0.05134 / 9.023 / 3 | 1126 |
| sched_12 | photo | 15x5 | 75/0/14 | 일치 | 0 | 0 | 0 | 0.01071 | 0/0 | 0.000252 | 0/170 | 75/75 | 0.02728 / 3.917 / 2 | 0.0496 / 8.64 / 3 | 1133 |
| form_activity | photo | 16x7 | 94/17/71 | 일치 | 0 | 0 | 0 | 0.0287 | 0/0 | 1 | 0/247 | 94/94 | 0.02576 / 3.745 / 2 | 0.03657 / 6.358 / 4 | 1176 |
| form_attendance | photo | 16x9 | 109/34/85 | 일치 | 0 | 0 | 0 | 0.01351 | 0/0 | 1 | 0/313 | 109/109 | 0.02732 / 4.038 / 2 | 0.03786 / 5.994 / 4 | 1167 |
| form_meal | photo | 2x5 | 10/0/4 | 일치 | 0 | 0 | 0 | 0.001543 | 0/0 | 0.0001051 | 0/27 | 10/10 | 0.02424 / 3.295 / 2 | 0.04908 / 7.619 / 3 | 1060 |
| activity_300dpi | photo | 16x6 | 94/2/6 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/214 | 94/94 | 3.206e-7 / 0.00003206 / 1 | 0.00006828 / 0.006828 / 1 | 1392 |
| scan_activity | pdf_scan | 16x6 | 94/2/6 | 일치 | - | 0 | 0 | 0 | 0/0 | 0 | 0/214 | 94/94 | 0 / 0 / 0 | 0.0001968 / 0.01968 / 1 | 798 |
| attendance_300dpi | photo | 16x7 | 109/3/7 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/247 | 109/109 | 0 / 0 / 0 | 0 / 0 / 0 | 1391 |
| scan_attendance | pdf_scan | 16x7 | 109/3/7 | 일치 | - | 0 | 0 | 0 | 0/0 | 0 | 0/247 | 109/109 | 0 / 0 / 0 | 0 / 0 / 0 | 815 |
| meal_300dpi | photo | 2x5 | 10/0/0 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/27 | 10/10 | 0 / 0 / 0 | 0 / 0 / 0 | 1291 |
| scan_meal | pdf_scan | 2x5 | 10/0/0 | 일치 | - | 0 | 0 | 0 | 0/0 | 0 | 0/27 | 10/10 | 0 / 0 / 0 | 0 / 0 / 0 | 710 |
| s00_photo | photo | 7x3 | 15/3/3 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/52 | 15/15 | 0.000009673 / 0.002405 / 1 | 0.000005451 / 0.001267 / 2 | 962 |
| s01_photo | photo | 5x5 | 10/4/0 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/60 | 10/10 | 0.00001074 / 0.002453 / 1 | 0.000008391 / 0.001988 / 2 | 965 |
| s02_photo | photo | 9x7 | 51/3/13 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/142 | 51/51 | 0.000008925 / 0.002261 / 1 | 0.00000791 / 0.001892 / 2 | 972 |
| s03_photo | photo | 10x3 | 24/3/5 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/73 | 24/24 | 0.000008711 / 0.002245 / 1 | 0.000006841 / 0.0017 / 2 | 993 |
| s04_photo | photo | 6x7 | 33/4/10 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/97 | 33/33 | 0.000008605 / 0.002116 / 1 | 0.000006948 / 0.001635 / 2 | 973 |
| s05_photo | photo | 8x7 | 42/5/9 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/127 | 42/42 | 0.000009941 / 0.002421 / 1 | 0.000007643 / 0.001812 / 2 | 978 |
| s06_photo | photo | 7x3 | 16/4/4 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/52 | 16/16 | 0.00000962 / 0.002373 / 1 | 0.000009567 / 0.002325 / 2 | 971 |
| s07_photo | photo | 9x7 | 50/3/10 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0.0001524 | 0/142 | 50/50 | 0.000008124 / 0.002036 / 1 | 0.000006039 / 0.001395 / 2 | 989 |
| s08_photo | photo | 11x5 | 44/5/7 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/126 | 44/44 | 0.000009834 / 0.002357 / 1 | 0.00001026 / 0.002581 / 2 | 993 |
| s09_photo | photo | 7x6 | 30/4/6 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/97 | 30/30 | 0.000008925 / 0.002181 / 1 | 0.000006948 / 0.001844 / 2 | 975 |
| s10_photo | photo | 11x3 | 31/2/6 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/80 | 31/31 | 0.000009406 / 0.002405 / 1 | 0.000009139 / 0.0021 / 2 | 1000 |
| s11_photo | photo | 7x4 | 22/3/2 | 일치 | 0 | 0 | 0 | 0 | 0/0 | 0 | 0/67 | 22/22 | 0.000008979 / 0.002181 / 1 | 0.000009246 / 0.002565 / 2 | 974 |

읽는 법: `구조일치` = 행/열 수, 병합, 칸 목록, 빈 칸 판정, flags, 격자 선 유무(null 패턴), 이중선 여부 모두 일치. `칸 info 정수필드` = h/v 정렬, 글줄 띠, ink bbox, size_pt, bold 등(불일치 개수/최대차). `칸 info 실수필드` = med/uni/fill/stroke_ratio/bgr(bgr 은 정수 +-1). `경계 스타일` = 두께 보정(-0.2mm) 후 style_name(NONE/SOLID/MEDIUM/THICK/DOUBLE) 불일치 수/전체. `JS ms` = Node 에서 3회 중 최소, 디코드/PNG 인코드 제외, 스캔은 10px/mm 정규화 포함.

요약: 26개 모두 구조 일치, 격자 xs/ys/칸 rect 최대차 0px, 빈 칸 판정/칸 info 정수필드/경계 스타일 불일치 0, flags 일치.

## 남은 차이와 원인

1. **사진 경로의 원근 보정 이미지(warpPerspective INTER_CUBIC)**: 실사진 7장은 다른 픽셀이 3~4%(평균절대차 0.03, 최대 2), 합성 12장은 0.002%, 300dpi/스캔 6장은 0%에 가깝다. 같은 JS 코드에서 Python 쪽만 `cv2.setUseOptimized(False)`(SIMD 디스패치 끔)로 돌린 덤프(`dump_py.py` 환경변수 `PARITY_NOOPT=1`, 기본 꺼짐, 원인 분석 전용)와 비교하면 다른 픽셀이 0.007~0.009%, 최대 1 로 떨어진다. 즉 원인은 cv2 의 x86 SIMD(AVX2/AVX512) 경로와 wasm 경로의 큐빅 보간 반올림 차이이고, 라이브러리 수준이라 JS 에서 맞출 수 없다. 영향: 평탄화 이미지(<= 3~4 레벨), 선 두께 추정(최대 0.032mm), 칸 bgr(+-1)까지 번지지만 **격자 좌표/구조/빈 칸/경계 스타일/flags 에는 영향이 없었다**(위 표). 두께 0.03mm 차이가 스타일 임계(0.35/0.7mm, 보정 후)를 넘는 칸은 이 입력들에서 없었다.
2. **스캔/300dpi 입력은 거의 비트 일치**: scan_attendance, attendance_300dpi, meal_* 는 보정/평탄화 이미지가 완전히 같다(해시 일치 포함). activity 계열은 픽셀 1개가 1 차이다(0.00003%).

### JPEG 디코더 차이(`jpegdiff.mjs`, 원본 jpg 를 jpeg-js 로 읽은 경우)

브라우저/Node 의 JPEG 디코더는 libjpeg-turbo(cv2) 와 같지 않다. 원본 JPEG 를 jpeg-js(EXIF 방향은 `exif.js` 로 적용)로 읽어 같은 JS 파이프라인을 돌리면:

- 디코드 픽셀 평균절대차 0.25~0.6, 최대 24. 칸 목록(r,c,rs,cs)과 빈 칸 판정은 사진 19장 전부 Python 과 같다.
- 격자 xs/ys 는 대부분 0, 일부 합성 입력에서 최대 3px(s11), 2.5px(s08), 0.5~1px(sched_09 등). 즉 **디코더가 다르면 좌표가 ±3px 까지 움직인다. "완전 동일"은 디코드된 픽셀이 같을 때만 보장된다.**
- flags 의 `paper_not_a4_ratio:x.xx` 숫자가 달라질 수 있다(sched_10 1.17 vs 1.18, sched_12 1.20 vs 1.13, 판정 분기는 같음).
- 중요: **cv2.imread 는 EXIF 방향을 적용한다.** 실사진 7장(Galaxy S24)은 방향 6(90도 회전)이라 raw 2000x1500 이 1500x2000 이 된다. 브라우저는 `createImageBitmap(blob)`/`<img>` 가 방향을 자동 적용하므로 같지만, 디코더를 직접 쓰면(jpeg-js 등) `exif.js` 같은 처리가 필요하다.

## JS 단독 처리 시간 (Node, 입력별, 최소 3회)

Mac M5 Pro, Node v26.5.0, opencv.js(wasm, 단일 스레드). 서버 CV 단독 처리량 측정은 `docs/BROWSER_OCR.md` 참고.

| 구분 | 시간 |
|---|---|
| 실사진 7장 | 약 1.06~1.22초 |
| 300dpi PNG 3장(사진 경로) | 약 1.29~1.39초 |
| 스캔(10px/mm 정규화 + 격자) 3장 | 약 0.71~0.81초 |
| 합성 12장 | 약 0.96~1.00초 |

단계별(sched_09, ms): find_paper 20, rectify 65, table_rectify 412, line_mask 171, line_masks 137, build_grid 187, trim/extend 1, flatten 84, analyze_cells 72. 가장 느린 곳은 `tableRectify` 의 가장 큰 연결 성분 점 수집/convexHull(약 0.4초)이고 줄일 여지가 있다(컴포넌트 외곽 윤곽만 추출). `lineMask` 의 `medianBlur(41)` 도 큼. UI 스레드를 막지 않으려면 Web Worker 에서 돌려야 한다.

## 검증되지 않은 분기

입력 26개로 밟지 못한 분기: 가로 용지(`landscape_page`), `boxPoints` 폴백(approxPolyDP 가 4점을 못 낸 경우), `no_lines`/`no_grid` 오류 경로, `table_quad_failed`, `ext_left` 에서 병합이 있는 경우. 코드는 Python 과 같은 흐름으로 옮겼지만 대조는 하지 않았다. `trim_outer` 는 sched_10(top=1), `_extend_left` 는 sched_10 에서 대조됐다.

## 2단계로 넘길 주의점

1. 이 단계의 칸 info 에는 `hangul_thickness`(hth)가 빠져 있다. bold_pass 가 이를 쓰므로 `distanceTransform(DIST_MASK_PRECISE)` 지원/결과 일치를 먼저 확인해야 한다.
2. 대조 입력은 Python 이 디코드한 픽셀이다. 브라우저에서는 디코더가 달라 좌표가 ±3px 움직일 수 있으므로, 2단계 이후의 "동일" 기준은 (a) 디코드 이후 동일(이번 하네스), (b) 실제 브라우저 디코드 입력은 구조 동일 + 좌표 허용치로 분리해서 잡아야 한다. 구조 판정이 흔들리는 입력이 나오면 그 칸을 flags 로 올리는 편이 안전하다.
3. 사진 경로의 보정 이미지는 SIMD 차이로 실사진에서 최대 2 레벨 달라진다. 임계값이 걸린 후속 판정(잉크 `med-55`, 배경색 `bg`, 굵기)이 경계에 있는 칸은 불일치가 날 수 있다. 2단계 대조에서는 보정 이미지를 Python 덤프 PNG 로 고정한 비교와 JS 보정 이미지를 쓴 비교를 둘 다 해 어느 쪽 차이인지 분리할 것.
4. `cv.Mat` 은 wasm 힙이라 반드시 delete. `data` 뷰는 힙이 커지면 무효화되므로 읽기 직전에 접근한다. 이번 이식은 `tracker()` 패턴을 썼다.
5. `lstsq` 는 QR 로 풀어 numpy(gelsd)와 다른 알고리즘이다. 이번 입력에서는 평탄화 이미지가 일치했지만 다항식 적합 입력이 병적이면(점이 적거나 한쪽에 몰림) 계수 오차가 커질 수 있다.
6. 시간: 합계 1초 안팎에서 table_rectify 가 40%. 2단계 이후 OCR 칸 크롭(`_ink_tight`)과 붙으면 Worker 로 옮기고, table_rectify 의 점 수집을 줄이는 최적화를 한 번 해 둘 것.
7. 합성 벤치는 elgrim 에 12장뿐이다(요청은 24장). 합성 생성은 `sheetparser/synth.py` / `python -m sheetparser bench` 에서 쓰는 것으로 보이며 이번에는 생성하지 않았다.


---

# 2단계: 나머지 파이프라인 + 브라우저 OCR + 의심 칸 규칙 -> 최종 spec

범위: `_run_page` 나머지 전부(서식/정렬/굵기/글자 크기/줄바꿈/표 밖 블록/레이아웃), 브라우저 OCR(PP-OCRv5), 의심 칸 규칙, 서버 재판독. Python 코드는 바꾸지 않았다(덤프는 함수 래핑만). 시트 생성 없음. vlm/paddle 컨테이너는 건드리지 않고 ssh -L 터널로 호출만 했다.

## 추가한 모듈과 함수 대응표

| Python | JS (`web/src/`) | 비고 |
|---|---|---|
| `photopage.find_blocks`, `_bands`, `_blk_corr`, `_syllable_h` | `blocks.js` `findBlocks`, `bands`, `blkCorr`, `syllableH` | HSV 종이 마스크, 윤곽 메움, 글줄 묶기, 윤곽 길이 기반 굵기 |
| `photopage.bold_pass`, `align_pass`, `_cut`, `fit_pass`, `fit_blocks` | `passes.js` | `Counter.most_common` 순서(동률은 먼저 나온 값) 재현(`mostCommon`), `score.lev` -> `lev` |
| `photopage.break_pass` | `run.js` + `ocr_cv.js lineCrop` | 줄 읽기는 OCR 콜백(`readLines`) 주입, `_cut` 은 `passes.cut` |
| `style.hangul_thickness`, `size_from_ink`, `unify_sizes` | `style.js` `hangulThickness`, `sizeFromInk`, `unifySizes` | `distanceTransform(DIST_L2, DIST_MASK_PRECISE)` 가 JS 에서 Python 과 비트 일치(hth 대조 0 차이) |
| `layout.py` 전부 | `layout.js` `padBlocks`, `buildPageSpec` | `round(v,3)`, `bisect`, `int(round())` 는 `pyRoundN/pyRound` |
| `ocr._ink_tight`, 칸/블록/줄 크롭 | `ocr_cv.js` `inkTight`, `cellCrop`, `blockCrop`, `lineCrop` | 파이썬 슬라이스 의미(`max(y0+3,0)`, `min(y1-3,H)`) 그대로 |
| `photopage._run_page` 나머지, `pipeline._assemble`(사진/스캔 부분) | `run.js` `runPage(img, kind, opts)` | 이미지 -> 최종 spec. OCR 은 `opts.ocr` 콜백 주입 |
| (신규) `ocr.paddle_read` 의 브라우저판 | `ppocr.js`, `ocr_client.js`, `suspect.js` | PP-OCRv5 kor rec + mobile det(표선 제거 + det + 줄 묶기 + det 빈 결과 시 줄 분할 폴백), 의심 판정, 서버 재판독 콜백 |

`runPage(img, kind, opts)` 는 파일 I/O 가 없어 브라우저/Node 공용이다. 주입 지점:

```
opts.ocr = { readCells(items) -> [{text, conf, ...}], readBlocks(items) -> [text], readLines(items) -> [text|null] }
opts.fixed = { img, pgMm, flags }    // (선택) 보정 이미지 고정(대조 모드 i)
```

`makeClientOcr({ppocr, suspect, server, encode})`(ocr_client.js)가 이 콜백을 만든다. `server(reqs)` 는 `[{id, kind, png, w, h, est, reasons}] -> [{text}]` 이고, Node 하네스는 `tools/parity/server_mock.mjs`(ocr.py `_paddle_one`/`_paddle_read_raw`/`paddle_read`/`read_crop32` 와 같은 프롬프트, 파라미터, 잘림 재요청, 한자 시 32B)로 구현했다. 브라우저에서는 실제 백엔드 API 가 이 자리를 채운다.

## 대조 A: OCR 고정, CV/서식/레이아웃 동일성

Python 현행 결과(paddle 백엔드, 업로드 없음)의 칸 텍스트, 블록 텍스트, break_pass 줄 읽기(`_cut` 입력)를 `dump_spec_py.py` 가 함수 래핑으로 기록하고(`out/spec_py/*_ocr.json`), JS 에 그대로 주입했다. 비교 필드(텍스트 포함, 허용 오차 0): 칸마다 text(줄바꿈 위치 포함), h, v, size_pt, bold, bg, wrap, font, underline, italic, color, src_bbox, sheet_pt, 블록의 `_lay_pt/_ink_w_mm/_stroke/_line/_nc`, 그리고 페이지 단위 page_mm, 열 폭, 행 높이, 표/블록 경계(`meta.x_mm/y_mm`), 테두리 h/v, flags, images. 칸 목록(role,r,c,rs,cs)도 필드로 센다. 입력은 1단계와 같은 26개(합성 12장 포함).

| 입력 | 칸 수(py/js) | 모드 (i) Python 보정 PNG 고정 | 모드 (ii) JS 자체 보정 | 불일치 칸 (i/ii) |
|---|---|---|---|---|
| sched_09 | 76/76 | 924/924 (100.00%) | 924/924 (100.00%) | 0/0 |
| sched_10 | 75/75 | 908/908 (100.00%) | 908/908 (100.00%) | 0/0 |
| sched_11 | 70/70 | 848/848 (100.00%) | 848/848 (100.00%) | 0/0 |
| sched_12 | 75/75 | 908/908 (100.00%) | 908/908 (100.00%) | 0/0 |
| form_activity | 97/97 | 1184/1184 (100.00%) | 1184/1184 (100.00%) | 0/0 |
| form_attendance | 112/112 | 1364/1364 (100.00%) | 1364/1364 (100.00%) | 0/0 |
| form_meal | 14/14 | 192/192 (100.00%) | 192/192 (100.00%) | 0/0 |
| activity_300dpi | 97/97 | 1190/1190 (100.00%) | 1190/1190 (100.00%) | 0/0 |
| scan_activity | 97/97 | 1190/1190 (100.00%) | 1190/1190 (100.00%) | 0/0 |
| attendance_300dpi | 112/112 | 1364/1364 (100.00%) | 1364/1364 (100.00%) | 0/0 |
| scan_attendance | 112/112 | 1365/1365 (100.00%) | 1365/1365 (100.00%) | 0/0 |
| meal_300dpi | 13/13 | 177/177 (100.00%) | 177/177 (100.00%) | 0/0 |
| scan_meal | 14/14 | 193/193 (100.00%) | 193/193 (100.00%) | 0/0 |
| s00_photo | 15/15 | 188/188 (100.00%) | 188/188 (100.00%) | 0/0 |
| s01_photo | 10/10 | 128/128 (100.00%) | 128/128 (100.00%) | 0/0 |
| s02_photo | 51/51 | 620/620 (100.00%) | 620/620 (100.00%) | 0/0 |
| s03_photo | 24/24 | 296/296 (100.00%) | 296/296 (100.00%) | 0/0 |
| s04_photo | 33/33 | 404/404 (100.00%) | 404/404 (100.00%) | 0/0 |
| s05_photo | 42/42 | 512/512 (100.00%) | 512/512 (100.00%) | 0/0 |
| s06_photo | 16/16 | 200/200 (100.00%) | 200/200 (100.00%) | 0/0 |
| s07_photo | 50/50 | 608/608 (100.00%) | 608/608 (100.00%) | 0/0 |
| s08_photo | 44/44 | 536/536 (100.00%) | 536/536 (100.00%) | 0/0 |
| s09_photo | 30/30 | 368/368 (100.00%) | 368/368 (100.00%) | 0/0 |
| s10_photo | 31/31 | 380/380 (100.00%) | 380/380 (100.00%) | 0/0 |
| s11_photo | 22/22 | 272/272 (100.00%) | 272/272 (100.00%) | 0/0 |
| **합계** | | **16319/16319 (100.00%)** | **16319/16319 (100.00%)** | 0/0 |

- 두 모드 모두 비교 필드 전부 일치, 불일치 칸 0. 모드 (ii) 는 1단계의 보정 이미지 차이(SIMD 라이브러리 차이, 최대 2 레벨)가 있어도 최종 spec 의 어떤 필드도 바꾸지 못했다. 1단계 주의점 3(임계값 경계 칸)은 이 26개 입력에서는 발생하지 않았다.
- 수정 이력(불일치당 3회 이내): sched_09 의 표 밖 블록 1개가 JS 에서 빠졌다(24%대 필드 불일치). 원인은 `Mat.data` 힙 뷰를 잡아둔 채 다음 Mat 을 할당해 wasm 힙이 커지면서 이전 뷰가 detach 되어 0 으로 읽힌 것이다(1회 수정으로 해결, 아래 주의점).

## 대조 B: 브라우저 OCR 종단 (JS 자체 보정 + PP-OCRv5 + 의심 칸 서버 재판독)

구성: `korean_PP-OCRv5_mobile_rec`(rec_ko.onnx 13.4MB) + `PP-OCRv5_mobile_det`(det_mobile.onnx 4.8MB), onnxruntime-web 1.30.0 wasm EP 4스레드를 Node 에서 실행(브라우저와 같은 패키지; `onnxruntime-node` 는 이 맥/Node v26 에서 `ERR_DLOPEN_FAILED` 로 로드되지 않았다). `docs/BROWSER_OCR.md` 의 최선 구성(`pp_det2f_mob`)을 이식: 표선 제거(`clean_rules`), det(DB) 후 줄 묶기, rec, det 가 빈 결과면 줄 분할 rec. 서버: paddle(127.0.0.1:18003, `_paddle_one` 과 같은 "OCR:" 프롬프트/`temperature 0`/`logprobs`/출력 한도 est_tokens 기반, 잘림 재요청, 한자면 32B). 채점은 `tools/accuracy.py`, `tools/struct_eval.py` 를 그대로 호출(회귀셋 13개)하고 합성 12장은 칸 텍스트 일치(공백 제거, `score.table_view` 키 (r,c,rs,cs))로 채점했다(`tools/parity/score_ocr.sh`).

### 정확도

| 구성 | PDF 6건 칸(struct_eval) | PDF 6건 글자(accuracy) | 일정표 4 + 서식 3 (칸/필수문구) | 합성 12장 칸 |
|---|---|---|---|---|
| 현행 Python PaddleOCR-VL 전체(이 하네스에서 재측정) | 400/400 | 3462/3472 | 308/308 | 291/293 |
| JS 클라이언트 OCR 단독(서버 재판독 없음) | 389/400 | 3445/3472 | 306/308 | 276/293 |
| **JS 클라이언트 OCR + 의심 칸만 서버 재판독** | **400/400** | **3462/3472** | **308/308** | **293/293** |

- 서버 재판독을 붙인 결과는 현행 Python 과 같거나(PDF/사진) 낫다(합성: 현행이 놓친 `월1`, `긴산중학교` 2칸도 일치. 합성 정답 대비 기준이라 Python 쪽 오독이 그대로 드러난다). 블록 필수 문구는 둘 다 4/7 이다(sched_10~12 의 제목 블록, 현행도 같다).
- 정답 대비 칸 오류 수(채점기 판정이 아닌 칸 단위 비교, PDF/합성은 GT, 일정표/서식은 서버 paddle 결과를 정답으로 대용): 클라이언트 단독 칸 35/992 오류(96.5% 일치), 블록 10/30 오류.

### 의심 칸 규칙 (근거: `tools/parity/suspect_eval.mjs`, 클라이언트 단독 결과를 정답과 비교)

규칙은 `web/src/suspect.js`. 채택: `empty, han, digit_hangul, paren, fallback, sparse, low_conf(칸<0.8, 블록<0.95)`.

### 칸: 규칙별 (플래그 수 / 오류 재현율 / 정밀도)
| 규칙 | 의심(전체 대비) | 재현율(잡은 오류/전체 오류) | 정밀도 |
|---|---|---|---|
| empty | 1 (0.1%) | 1/35 (3%) | 100% |
| han | 0 (0.0%) | 0/35 (0%) | -% |
| digit_hangul | 10 (1.0%) | 10/35 (29%) | 100% |
| digit_hangul_any | 74 (7.5%) | 11/35 (31%) | 15% |
| low_conf conf<0.8 | 23 (2.3%) | 11/35 (31%) | 48% |
| low_conf conf<0.9 | 32 (3.2%) | 11/35 (31%) | 34% |
| low_conf conf<0.95 | 83 (8.4%) | 11/35 (31%) | 13% |
| low_conf conf<0.97 | 149 (15.0%) | 14/35 (40%) | 9% |
| low_conf conf<0.99 | 307 (30.9%) | 30/35 (86%) | 10% |
| fallback | 13 (1.3%) | 5/35 (14%) | 38% |
| long (공백 제외 20자 이상) | 42 (4.2%) | 11/35 (31%) | 26% |
| multiline | 61 (6.1%) | 10/35 (29%) | 16% |
| paren | 3 (0.3%) | 3/35 (9%) | 100% |
| sparse | 18 (1.8%) | 12/35 (34%) | 67% |
| uncovered | 285 (28.7%) | 16/35 (46%) | 6% |

### 블록: 규칙별 (플래그 수 / 오류 재현율 / 정밀도)
| 규칙 | 의심(전체 대비) | 재현율(잡은 오류/전체 오류) | 정밀도 |
|---|---|---|---|
| empty | 0 (0.0%) | 0/10 (0%) | -% |
| han | 0 (0.0%) | 0/10 (0%) | -% |
| digit_hangul | 0 (0.0%) | 0/10 (0%) | -% |
| digit_hangul_any | 6 (20.0%) | 2/10 (20%) | 33% |
| low_conf conf<0.8 | 10 (33.3%) | 9/10 (90%) | 90% |
| low_conf conf<0.9 | 10 (33.3%) | 9/10 (90%) | 90% |
| low_conf conf<0.95 | 10 (33.3%) | 9/10 (90%) | 90% |
| low_conf conf<0.97 | 10 (33.3%) | 9/10 (90%) | 90% |
| low_conf conf<0.99 | 10 (33.3%) | 9/10 (90%) | 90% |
| fallback | 4 (13.3%) | 4/10 (40%) | 100% |
| long (공백 제외 20자 이상) | 4 (13.3%) | 1/10 (10%) | 25% |
| multiline | 0 (0.0%) | 0/10 (0%) | -% |
| paren | 3 (10.0%) | 3/10 (30%) | 100% |
| sparse | 0 (0.0%) | 0/10 (0%) | -% |
| uncovered | 6 (20.0%) | 6/10 (60%) | 100% |

- `digit_hangul` 은 처음에 "숫자와 한글이 붙기만 해도"로 만들었다가(`digit_hangul_any`, 74칸 7.5%, 정밀도 15%) 오류가 `7->기`, `0->이` 혼동이라는 것을 보고 `숫자-하이픈-한글` 또는 `숫자+기/이` 로 좁혔다(10칸 1.0%, 정밀도 100%). `2교시` 같은 정상 글자가 걸리지 않는다.
- `sparse`: det 박스 폭(`sum(w/h)`)에 비해 읽은 글자 수가 모자라면 의심(`글자수/박스폭 < 0.75`). `퇴근 -> 퇴`, `출근 -> 출` 같은 글자 누락이 rec 확률은 0.97~0.99 로 높아서 `low_conf` 로는 못 잡는다. 이 규칙 하나가 합성 오류 12칸을 잡았다.
- `low_conf`: rec 최소 확률(det 박스별 평균 확률의 최솟값). 칸은 0.8, 블록은 0.95(블록 오류는 전부 확률이 낮고 블록 수가 적어 높게 둠).
- `fallback`: det 가 아무것도 못 찾아 줄 분할 rec 로 폴백한 칸(`초그 알드` 같은 오독이 나옴, 확률 0).
- `han`: 데이터에 한자 오독이 한 건도 없어 재현율을 측정하지 못했다(현행 정책을 따라 둔 규칙이며 서버가 한자면 32B 로 한 번 더 읽는 정책도 서버 쪽에 그대로 있다).
- `multiline`, `long`, `uncovered`(det 박스가 덮지 못한 잉크 비율)는 정밀도가 낮아 채택하지 않았다.

### 칸: 조합
| 조합 | 의심(전체 대비) | 재현율 | 정밀도 |
|---|---|---|---|
| empty+han+digit_hangul+paren+fallback+sparse | 45 (4.5%) | 31/35 (89%) | 69% |
| 위 + low_conf<0.8 | 52 (5.2%) | 34/35 (97%) | 65% |
| 위 + low_conf<0.9 | 61 (6.1%) | 34/35 (97%) | 56% |
| 위 + low_conf<0.95 | 111 (11.2%) | 34/35 (97%) | 31% |
| 위 + low_conf<0.97 | 174 (17.5%) | 34/35 (97%) | 20% |
| 위 + low_conf<0.99 | 317 (32.0%) | 35/35 (100%) | 11% |
| 위(0.9) + multiline | 107 (10.8%) | 34/35 (97%) | 32% |
| 위(0.9) + long | 92 (9.3%) | 34/35 (97%) | 37% |
| 위(0.9) + uncovered>5% | 314 (31.7%) | 34/35 (97%) | 11% |
| **채택**: 위 + low_conf(칸<0.8, 블록<0.95) | 52 (5.2%) | 34/35 (97%) | 65% |

### 블록: 조합
| 조합 | 의심(전체 대비) | 재현율 | 정밀도 |
|---|---|---|---|
| empty+han+digit_hangul+paren+fallback+sparse | 5 (16.7%) | 5/10 (50%) | 100% |
| 위 + low_conf<0.8 | 8 (26.7%) | 8/10 (80%) | 100% |
| 위 + low_conf<0.9 | 9 (30.0%) | 8/10 (80%) | 89% |
| 위 + low_conf<0.95 | 10 (33.3%) | 9/10 (90%) | 90% |
| 위 + low_conf<0.97 | 15 (50.0%) | 10/10 (100%) | 67% |
| 위 + low_conf<0.99 | 18 (60.0%) | 10/10 (100%) | 56% |
| 위(0.9) + multiline | 9 (30.0%) | 8/10 (80%) | 89% |
| 위(0.9) + long | 13 (43.3%) | 9/10 (90%) | 69% |
| 위(0.9) + uncovered>5% | 9 (30.0%) | 8/10 (80%) | 89% |
| **채택**: 위 + low_conf(칸<0.8, 블록<0.95) | 10 (33.3%) | 9/10 (90%) | 90% |

한계: 규칙/임계값은 이 26개 입력으로 정했고 정답을 같은 데이터에서 봤으므로 과적합 위험이 있다(특히 `sparse` 0.75, `digit_hangul`). 일정표/서식 7장은 서버 paddle 결과를 정답으로 대용했다. 새 입력으로 재측정이 필요하다.

### 의심 비율과 전송량

| 입력 | OCR 대상(칸+블록) | 의심(서버로 감) | 비율 | 전송 PNG KB | (참고) JPEG q90 KB | 서버 변경 | 클라이언트 OCR ms | 서버 재판독 ms | 전체 ms |
|---|---|---|---|---|---|---|---|---|---|
| sched_09 | 62 | 2 | 3.2% | 24 | 5 | 0 | 963 | 315 | 3849 |
| sched_10 | 65 | 6 | 9.2% | 133 | 26 | 1 | 1192 | 342 | 3864 |
| sched_11 | 59 | 1 | 1.7% | 23 | 5 | 1 | 850 | 71 | 3194 |
| sched_12 | 61 | 1 | 1.6% | 4 | 1 | 0 | 884 | 118 | 3258 |
| form_activity | 26 | 5 | 19.2% | 261 | 50 | 2 | 388 | 293 | 2614 |
| form_attendance | 27 | 5 | 18.5% | 347 | 67 | 3 | 424 | 327 | 2805 |
| form_meal | 10 | 1 | 10.0% | 54 | 14 | 1 | 209 | 202 | 2224 |
| activity_300dpi | 91 | 6 | 6.6% | 194 | 108 | 6 | 2097 | 1238 | 5993 |
| scan_activity | 91 | 6 | 6.6% | 172 | 111 | 6 | 2122 | 792 | 4818 |
| attendance_300dpi | 105 | 3 | 2.9% | 50 | 37 | 3 | 1633 | 348 | 4804 |
| scan_attendance | 105 | 1 | 1.0% | 8 | 5 | 1 | 1603 | 152 | 3644 |
| meal_300dpi | 13 | 2 | 15.4% | 20 | 12 | 1 | 462 | 280 | 2894 |
| scan_meal | 14 | 2 | 14.3% | 10 | 6 | 1 | 440 | 368 | 2375 |
| s00_photo | 12 | 0 | 0.0% | 0 | 0 | 0 | 252 | 0 | 2049 |
| s01_photo | 10 | 1 | 10.0% | 8 | 2 | 0 | 238 | 226 | 2200 |
| s02_photo | 38 | 4 | 10.5% | 60 | 13 | 3 | 537 | 1115 | 3632 |
| s03_photo | 19 | 1 | 5.3% | 72 | 11 | 1 | 437 | 75 | 2705 |
| s04_photo | 23 | 3 | 13.0% | 49 | 10 | 3 | 329 | 1158 | 3246 |
| s05_photo | 33 | 4 | 12.1% | 85 | 18 | 3 | 499 | 330 | 2600 |
| s06_photo | 12 | 2 | 16.7% | 47 | 9 | 1 | 302 | 306 | 2456 |
| s07_photo | 40 | 1 | 2.5% | 7 | 2 | 1 | 531 | 66 | 2535 |
| s08_photo | 37 | 1 | 2.7% | 7 | 2 | 1 | 717 | 78 | 2890 |
| s09_photo | 24 | 2 | 8.3% | 17 | 4 | 2 | 376 | 80 | 2390 |
| s10_photo | 25 | 2 | 8.0% | 185 | 31 | 2 | 549 | 80 | 2597 |
| s11_photo | 20 | 0 | 0.0% | 0 | 0 | 0 | 308 | 0 | 2203 |
| **합계/평균** | 1022 | 62 | 6.1% | 장당 평균 73 | 장당 평균 22 | | | | |

- 의심 비율: 전체 OCR 대상(칸+블록) 1,022 중 62개(6.1%, 칸만 보면 5.2%)가 서버로 갔다. 전송은 의심 칸의 ink-tight 크롭(PNG)뿐이고 원본 사진은 보내지 않는다.
- 전송량: 장당 평균 73KB(PNG, 중앙값 47KB, 최대 347KB). 같은 크롭을 JPEG q90 으로 인코딩하면 평균 22KB(참고용 기록, 서버 정확도는 JPEG 로 검증하지 않았다). 실사진 7장의 원본 JPEG 는 평균 440KB, 전송 PNG 는 장당 4~347KB(평균 약 121KB)다. 합성 s01(10%)처럼 크롭이 칸 전체로 남는 경우 PNG 가 커진다.
- 시간(Node, 3회 중 최소가 아닌 1회 종단): 클라이언트 OCR 장당 평균 약 0.73초(최대 2.1초), 서버 재판독 평균 약 0.33초(최대 1.2초, 동시 4건), 종단(보정+서식+OCR+서버) 평균 약 3.1초(최대 6.0초).
- 규칙별 서버 전송 건수(중복 포함): `low_conf` 33, `sparse` 18, `fallback` 17, `digit_hangul` 10, `paren` 6, `empty` 1, `han` 0.

### 놓친 오류(클라이언트가 틀렸는데 의심 규칙이 못 잡은 것)

- 칸 1: sched_12 r13c3 `O` 대 `0`(정답으로 쓴 서버 paddle 결과가 `O`, 채점기는 둘 다 통과). 사실상 정답 대용 오류일 가능성이 있다.
- 블록 1: sched_09 제목 `시털 튜터 9월 근무일정표`(현행 서버 결과는 `지털 튜터...`로 서로 다르다. 채점기 block_ok 는 현행과 같은 결과).
- 종단 결과에 남은 오류는 현행 Python 과 동일한 PDF 글자 10자(서명/서경 계열, 시그니처 블록 환각)뿐이다.

## JS 단계별 시간 (Node, 입력당 3회 중 최소, OCR 은 주입이라 CV 만)

| 구분 | 전체 ms(최소~최대) | 평균 |
|---|---|---|
| 실사진 7 | 1763~2244 | 2003 |
| 300dpi PNG 3 | 2039~2621 | 2390 |
| 스캔 PDF 3 | 1499~1878 | 1735 |
| 합성 12 | 1604~2002 | 1747 |

단계별 평균(ms, 26개): table_rectify 424, find_blocks 540, analyze_cells 329(hth 포함), rectify 201, build_grid 199, line_mask 183, line_masks 146, flatten 116, find_paper 66(사진만), 나머지(크기/굵기/정렬/레이아웃) 1 미만. 병목은 find_blocks(HSV 전체 + medianBlur 71 + 윤곽)와 table_rectify 다.

## 이번에 추가로 알게 된 주의점 (3단계로 넘길 것 포함)

1. **`Mat.data` 힙 뷰 무효화**: `Mat.data/data32S` 는 wasm 힙 위의 뷰다. 그 뒤에 새 Mat 을 할당해 힙이 커지면 이전 뷰는 detach 되어 읽으면 0/undefined 다. 입력 크기/타이밍에 따라 간헐적으로 나타나므로(sched_09 에서만 터졌다), 뷰는 쓰기 직전에 가져오거나 `new Uint8Array(mat.data)` 로 복사해 쓴다. 이번에 blocks.js, style.js, ocr_cv.js, preprocess.js 를 정리했다. 새 코드를 쓸 때도 같은 규칙을 지킬 것.
2. **`Mat.clone()` 은 ROI 의 step 을 유지한 비연속 Mat 을 돌려준다**(OpenCV.js 5.0.0 실측: `roi().clone()` 의 `isContinuous()` 가 false, step 이 부모 폭). 선형 인덱싱(`data[i*3+c]`)이나 PNG 인코딩이 틀어진다(서버가 점무늬로 봄). `copyTo` 로 복사하는 `copyMat()`(cv.js)을 쓴다. 이 버그가 `clean_rules` 를 오염시켜 클라이언트 OCR 결과를 일부 왜곡했던 것을 서버 재판독 결과가 쓰레기로 나와서 발견했다. 이후 결과는 모두 수정본이다.
3. **JPEG 디코더/EXIF**(1단계와 동일): 종단 B 의 입력도 Python 이 디코드한 PNG 다. 브라우저 실제 디코드 입력은 좌표가 ±3px 흔들릴 수 있다(구조는 같았다).
4. **서버 재판독 크기**: 크롭이 칸 전체로 남는 경우(잉크 판별 실패) PNG 가 수백 KB 가 된다. 크롭 상한(예: 긴 변 1,000px, 축소)과 JPEG 사용을 검토할 것(서버 정확도 영향 미검증).
5. **브라우저 OCR 속도**: Node wasm(4스레드)에서 장당 약 0.73초(칸 평균 약 8ms). 브라우저(Chrome, Mac M5 Pro)는 `docs/BROWSER_OCR.md` 의 측정과 같은 범위일 것으로 보이나 이 하네스에서는 Node 만 쟀다. Web Worker + ort 스레드 필요.
6. **서버 목(mock)은 Node 재구현**이다. 운영 서버 API(크롭 수신 -> `paddle_read` 정책 적용)는 아직 없다. 한자/잘림/32B 경로가 이번 입력에서 몇 번 탔는지는 기록하지 않았다.
7. **밟지 못한 분기**: `ocr` 없이(`opts.ocr` 생략) 돌리는 경로는 대조하지 않았다(Python `ocr=False`와 같은 의도). 블록 텍스트가 `x` 가 되는 것만 맞춰 두었다.
