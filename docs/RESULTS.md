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
