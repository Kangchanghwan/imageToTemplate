# 결과 (3라운드, 2026-10-05)

`python -m sheetparser convert` 로 10개 + 스캔 경로 확인 1건을 실행한 결과. 시트는 `v3_<이름>`, 10개만 남기고 스캔 시트는 삭제했다.
시간은 변환 + 업로드 + 검증 전체(초). 나란히 PNG 는 `runs/convert/` 아래(저장소 제외), 왼쪽 원본(보정본) / 오른쪽 시트 A4 렌더.

| 시트 제목 | 경로 | 시간(초) | 셀/텍스트 정확도 | 선 오차 중앙/최대(mm) | 블록 오차 중앙/최대(mm) | 굵기 일치 | 시트 URL | 나란히 PNG |
|---|---|---|---|---|---|---|---|---|
| v3_attendance_09 | pdf_vector | 20 | 텍스트 일치 100.0%, 위치 찾음 100% | 0.15 / 0.25 | 0.59/0.74 | 100.0% (원본 굵은 글줄 11) | https://docs.google.com/spreadsheets/d/1Ef93JP89t0vtrTg78P2U68-Rp31-3alQUWJCXzVgcnM/edit | `runs/convert/attendance_09/v3_attendance_09_side.png` |
| v3_activity_09 | pdf_vector | 24 | 텍스트 일치 100.0%, 위치 찾음 100% | 0.10 / 0.25 | 0.69/1.20 | 100.0% (원본 굵은 글줄 10) | https://docs.google.com/spreadsheets/d/1JjKWFMBH538qK7Ygh5fg_ZXiThlpNmlf4qCZtzRYYXY/edit | `runs/convert/activity_09/v3_activity_09_side.png` |
| v3_meal_09 | pdf_vector | 12 | 텍스트 일치 100.0%, 위치 찾음 100% | 0.15 / 0.20 | 0.59/1.41 | 100.0% (원본 굵은 글줄 6) | https://docs.google.com/spreadsheets/d/1gbeMC4pQfTmwoVKTR76BzNAAcWYNwJkrWJcYRJgziqQ/edit | `runs/convert/meal_09/v3_meal_09_side.png` |
| v3_sched_09 | photo | 61 | 셀 75/75 (100.0%) | 0.05 / 0.20 | 0.35/0.35 | 100.0% (스펙 굵은 칸 57) | https://docs.google.com/spreadsheets/d/1P6YXREE0qUQ7uD2LktpZNdATrwmOtAYPXyl0rCaMuIs/edit | `runs/convert/sched_09/v3_sched_09_page_side.png` |
| v3_sched_10 | photo | 69 | 셀 75/75 (100.0%) | 0.05 / 0.25 | - | 100.0% (스펙 굵은 칸 41) | https://docs.google.com/spreadsheets/d/1m398Ride-Tvz4UKH7s8wTRDphTytn2UW9a0Ako7SoNk/edit | `runs/convert/sched_10/v3_sched_10_page_side.png` |
| v3_sched_11 | photo | 54 | 셀 70/70 (100.0%) | 0.05 / 0.15 | - | 100.0% (스펙 굵은 칸 38) | https://docs.google.com/spreadsheets/d/1NQQCS1NJb2hm9QD-7TD4_4Cw4l4iwSHFN06XlWiIyLE/edit | `runs/convert/sched_11/v3_sched_11_page_side.png` |
| v3_sched_12 | photo | 55 | 셀 70/70 (100.0%) | 0.05 / 0.15 | - | 96.7% (스펙 굵은 칸 51) | https://docs.google.com/spreadsheets/d/1vAs-DHn0bFgE_F5M6hB75mx1ROMU8MRB6MQUDfyS1e4/edit | `runs/convert/sched_12/v3_sched_12_page_side.png` |
| v3_form_activity | photo | 43 | 셀 6/6 (100.0%) | 0.05 / 0.25 | 0.31/0.40 | 92.3% (스펙 굵은 칸 1) | https://docs.google.com/spreadsheets/d/1Nmq6B3GBEt08gaPs17WgfTOA0ieM9eL0KTAt_QC4AiU/edit | `runs/convert/form_activity/v3_form_activity_page_side.png` |
| v3_form_attendance | photo | 39 | 셀 7/7 (100.0%) | 0.05 / 0.20 | 0.30/0.60 | 92.6% (스펙 굵은 칸 1) | https://docs.google.com/spreadsheets/d/1GezhhhhhNYoe1VNMvtqU9O1yMz2BKMARxWUHUSSLwjc/edit | `runs/convert/form_attendance/v3_form_attendance_page_side.png` |
| v3_form_meal | photo | 26 | 셀 5/5 (100.0%) | 0.10 / 0.15 | 0.40/0.68 | 100.0% (스펙 굵은 칸 1) | https://docs.google.com/spreadsheets/d/1wu7342HAznilTHjRpXOzKRodCp4y4I2DXqM6jERJrkw/edit | `runs/convert/form_meal/v3_form_meal_page_side.png` |
| scan_attendance_09 | pdf_scan | 102 | 정답 없음, 글줄 찾음 100% | 0.10 / 0.25 | 0.37/0.37 | 92.3% (스펙 굵은 칸 55) | (삭제됨) | `runs/convert/attendance_09_scan/scan_attendance_09_page_side.png` |

지표 설명
- PDF: 텍스트 일치 = 원본/시트 PDF 글자열 유사도, 선 오차 = 표 격자선 위치, 블록 오차 = 텍스트 글줄 중심 위치 오차.
- 사진: 셀 정확도 = `data/photos/gt_content.json` 대비, 선 오차 = 보정 원본과 시트 PDF 격자선, 블록 오차 = 표 밖 글줄 위치(정렬 기준 변). sched_10~12는 사진에 제목이 안 보여(종이가 잘림) 블록이 없다.
- 굵기 일치: PDF는 원본 PDF 글줄 굵기와 시트 PDF 글줄 굵기, 사진/스캔은 원본 PDF가 없어 스펙에 정한 굵기가 시트 PDF에 실제로 나온 비율.
- scan_attendance_09: attendance_09.pdf를 300dpi 이미지만 든 PDF로 만들어 pdf_scan 경로로 실행. 글자는 원본 텍스트 레이어와 664/664자 일치(vlm 읽기 결과 기준). 서명 이미지는 재현 안 됨.

## 3라운드 결함 수정 (a~f)

| 결함 | 원인 | 수정 | 확인 |
|---|---|---|---|
| a 굵은 글씨 소실 (PDF) | 굴림은 폰트명에 Bold 없이 fill+stroke 이중 그리기로 굵게 만듦 (`get_texttrace` type=1, linewidth 0.5~1.08). 3개 PDF 모두 해당 | stroke 글자 원점을 굵게로 판정, 업로드 | 3개 PDF 굵기 일치 100% (원본 굵은 글줄 11/10/6) |
| b 서명 줄 윗부분 잘림 | 표 밖 블록 행이 원본 글줄 높이라 시트 글줄(글자 x1.3)보다 낮음 | `layout.pad_blocks`: 행 높이 확보 + 병합 칸 가로 여유 | 이미지 확인, 3개 PDF 잘림 없음 |
| c 요일 열 일부 행 굵기/크기 다름, 머리글 굵기 제각각 | 잉크 측정이 실패한 칸은 기본값(10pt, 보통)으로 남음 | 머리글 행은 행 단위, 본문은 열 단위 최빈값(크기, 굵기)을 측정 실패 칸에도 적용 | 이미지 확인 (9/14, 9/15, 9/21 포함) |
| d 제목 오른쪽 끝 잘림 | 제목 칸이 글줄 폭만큼만 병합되고 시트 글꼴이 더 넓음 | 표 가운데 제목은 표 전체 폭 병합 + 가운데 정렬 | 이미지 확인 |
| e "디지털" -> "시털" | 제목 크롭 여유가 14px라 클립이 일부 가림 | 크롭 여유 확대(좌우 70, 상하 30px, 축소 없음) + 가려진 글자는 지어내지 말고 보이는 획만 읽도록 지시 | "디지털 튜터 9월 근무일정표" 로 읽힘 |
| f 제목이 보통 굵기 | 큰 글자는 잉크 두께/높이 비율이 낮게 나와 굵기 판정이 늘 보통 | 표 가운데 + 본문 1.2배 이상 큰 글줄은 굵게 (휴리스틱) | 이미지 확인 |

## 개선 이력

- 1라운드: 표 이미지/PDF -> TableSpec. 전처리, 격자, 벡터, 서식, OCR, Apps Script 작성기, 합성 데이터 채점, 표 기준 원근 보정, 셀 단위 OCR.
- 2라운드: 페이지 전체 재현(PageSpec v2). PDF 경로(pdfvec, layout, verify)와 사진 경로(photopage, ocr, style, verify_photo)를 따로 구현. 표 전체 1회 OCR + 행/이웃 재질의, 조명 평탄화/배경 판정, 표 밖 텍스트 블록, 내용 채점, 시트 교체 도구.
- 3라운드: 두 경로를 `convert` 한 진입점으로 연결(자동 판별, 스캔 PDF 경로 추가, 검증 라우팅). 결함 a~f 수정, 굵기 일치율 지표 추가, Apps Script `list` 액션으로 고아 시트 정리(38개 -> 10개), 업로드 재시도, 문서화.

## 속도 개선 (4라운드)

변경: (1) `convert` 기본은 스펙 생성 + 시트 업로드(create 1회)까지만 하고 URL을 반환한다. 시트 PDF 내보내기, 겹쳐 채점, 정답 채점은 `--verify`일 때만 한다. (2) vlm 출력을 JSON에서 압축 텍스트로 바꿨다. 표 전체 호출은 CV가 잉크 있다고 본 칸만 요청하고 완전히 빈 행은 요청하지 않으며, 출력은 한 줄에 한 행 `행번호|칸|칸` 이다. 행 단위 읽기, 이웃 칸 재질의, 표 밖 글줄 읽기도 같은 원칙(요청한 칸만, 따옴표/키/괄호 없음)이다. (3) llama.cpp `grammar`(GBNF) 파라미터가 이 서버에서 동작함을 확인했고(`/v1/chat/completions` 본문에 `grammar` 전달), 줄 수, 줄마다 `|` 개수, 행번호를 문법으로 강제한다. 문법이 막아 주므로 칸 밀림은 구조적으로 생기지 않으며, 코드에서도 개수를 한 번 더 검증해 어긋난 행은 기존 행 재질의로 넘긴다(측정 중 어긋난 행 0). (4) 프롬프트를 줄였다(열 너비 비율은 유지, 병합 설명은 요청 칸 목록으로 대체). 이미지 해상도는 그대로(긴 변 <= 1900px, 축소 없음).

측정은 검증을 끈 `convert`, 호출 직렬, 시트 `--delete`(sched_09만 `v4_sched_09`로 보존)이다. 시간은 변환 + 업로드 전체(초). 정확도는 같은 spec JSON을 `tools/accuracy.py`로 오프라인 채점했다. 이전 값은 `runs/convert/*/convert.json`(3라운드, 검증 포함)이고 이전 생성 토큰은 vlm 로그로 확인(아래 정정 참고).

| 입력 | 전 시간 | 후 시간 (변환/업로드) | 전 호출 | 후 호출 | 후 생성 토큰 | 후 프롬프트 토큰 | 정확도 (전 -> 후) |
|---|---|---|---|---|---|---|---|
| sched_09 | 61.3 | 50.1 (41.5/8.6) | 2 | 2 | 441 (표 호출 462 -> 381) | 3,327 | 75/75 -> 75/75 |
| sched_10 | 68.9 | 55.4 (45.9/9.5) | 1 | 1 | 428 | 4,039 | 75/75 -> 75/75 |
| sched_11 | 54.5 | 47.5 (38.1/9.4) | 1 | 1 | 396 | 3,044 | 70/70 -> 70/70 |
| sched_12 | 55.2 | 48.6 (39.3/9.3) | 1 | 1 | 398 | 3,226 | 70/70 -> 70/70 |
| form_activity | 43.0 | 43.8 (32.3/11.5) | 19 | 19 | 284 | 3,740 | 6/6 -> 6/6 |
| form_attendance | 39.0 | 31.9 (23.4/8.5) | 19 | 19 | 214 | 3,877 | 7/7 -> 7/7 |
| form_meal | 25.9 | 19.5 (10.9/8.7) | 5 | 5 | 127 | 1,752 | 5/5 -> 5/5 |
| 스캔 PDF (attendance_09 300dpi) | 102.4 | 59.7 (52.4/7.3) | 4 | 3 | 808 | 4,260 | 글자 664/664 -> 664/664 |

- 근무일정표 4장 290/290칸, 빈 양식 머리글 18/18, 스캔 PDF 글자 664/664 유지. 스캔은 정답에 없는 글자가 2개 더 나온다(서명 이미지 부근 "강", 체크 표시 "✅"). 이전과 같은 조건이다.
- 효과가 큰 곳은 스캔 PDF(-43초, 호출 4 -> 3, 행 재질의가 압축 출력이라 빨라짐)와 근무일정표(-6~13초). 표 전체 호출의 생성 토큰은 약 15~18% 줄었다(아래 정정). 검증 분리로 업로드 후 PDF 내보내기/채점이 빠져 업로드 구간은 장당 7~12초.
- form_activity/form_attendance는 호출 19회(행 단위 읽기)라 호출당 prefill 고정 비용이 지배적이라 거의 안 줄었다.
- 남은 병목: (a) 표 이미지 prefill 약 3,000~4,000토큰(약 15~17초, 해상도 유지 조건이라 못 줄임), (b) 한글 글자 자체의 생성 토큰(칸 글자 수에 비례, 약 16 tok/s), (c) 업로드 create 약 8~10초(Apps Script 쪽), (d) 빈 양식은 행마다 호출하는 고정 비용.

### 정정 (vlm 로그 대조)
865토큰은 sched_09가 아니라 스캔 PDF의 표 호출이었다. 근무일정표 표 호출의 실제 전/후(prefill 토큰 / 생성 토큰 / 생성 시간):

| 사진 | 전 | 후 | 생성 토큰 감소 |
|---|---|---|---|
| sched_09 | 3372 / 462 / 27.5s | 3116 / 381 / 22.7s | -18% |
| sched_10 | 4306 / 504 / 30.4s | 4035 / 428 / 25.8s | -15% |
| sched_11 | 3292 / 470 / 28.1s | 3040 / 396 / 23.6s | -16% |
| sched_12 | 3478 / 477 / 28.6s | 3222 / 398 / 23.9s | -17% |

근무일정표 장당 단축(6~13초) 중 압축 효과는 약 5초(생성)+0.5초(prefill), 나머지는 검증 분리 효과다. 생성 토큰 대부분이 한글/시각 문자열 자체라 형식 압축만으로는 한계가 있다. 스캔 PDF(-43초)는 압축 효과가 컸다(865토큰 JSON).
