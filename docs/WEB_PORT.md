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
