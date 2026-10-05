# sheetparser PoC 공통 명세 (TableSpec v1)

목표: 이미지/PDF 속 표를 구글 시트로 "구조 + 크기 + 서식"까지 그대로 옮긴다.
원칙: 기하(선/셀 좌표)를 먼저 CV로 확정하고, 글자는 나중에 셀 단위로 채운다. 모델이 구조를 생성하게 두지 않는다.

## 파이프라인
1. 입력 분기: pdf_vector(텍스트 레이어+벡터 선) / pdf_scan / photo
2. (photo/pdf_scan) 용지 외곽 검출 → 원근 보정 → A4 비율로 정규화 (10 px/mm, 2100x2970)
3. 격자 추출: 선 마스크(모폴로지) 또는 PDF 벡터 선 → 선 위치 클러스터링 → 전역 격자 → 셀별 rowspan/colspan
4. 서식: 선 두께/이중선, 배경색, 정렬, 글자 크기, 굵게
5. 내용: pdf_vector는 텍스트 레이어, 그 외는 elgrim vlm(127.0.0.1:18001, OpenAI 호환, json_schema 지원)에 셀/행 크롭
6. TableSpec JSON 출력 → Apps Script 웹앱이 시트 생성
7. 검증: 시트를 A4 100% PDF로 내보내 원본(보정본)과 겹쳐 채점

## 단위 규칙
- 시트 px = mm x 96/25.4 (A4 폭 210mm = 794px). PDF pt → px = pt x 96/72.
- photo는 용지 외곽으로 mm를 구한다. 외곽 검출 실패 시 이미지 폭 = 210mm로 가정하고 flags에 기록.

## TableSpec JSON
```json
{
  "version": 1,
  "source": {"path": "data/photos/sched_09.jpg", "kind": "photo|pdf_scan|pdf_vector", "page": 0},
  "page_mm": [210, 297],
  "origin_mm": [x, y],              // 표 왼쪽 위 모서리의 용지상 위치 (mm)
  "columns": [100, 80],             // 열 너비, 시트 px 정수
  "rows": [21, 30],                 // 행 높이, 시트 px 정수
  "cells": [
    {"r": 0, "c": 0, "rs": 1, "cs": 2,
     "text": "근무일정표",
     "h": "LEFT|CENTER|RIGHT", "v": "TOP|MIDDLE|BOTTOM",
     "size_pt": 10, "bold": false, "bg": "#ffffff" , "wrap": true,
     "src_bbox": [x0, y0, x1, y1]}  // 보정된 원본 이미지(또는 PDF pt) 좌표
  ],
  "borders": {
    "h": [["SOLID", "NONE"]],       // h[i][c]: 행 i 위쪽 경계(i=0..R), 열 c 구간. R+1 x C
    "v": [["SOLID"]]                // v[r][j]: 열 j 왼쪽 경계(j=0..C), 행 r 구간. R x (C+1)
  },
  "flags": [{"r": 0, "c": 0, "reason": "low_ocr_conf"}]
}
```
- 병합 셀은 왼쪽 위 칸 하나만 cells에 넣는다. 덮이는 칸은 생략.
- 선 스타일 값: NONE, SOLID, SOLID_MEDIUM, SOLID_THICK, DOUBLE, DASHED, DOTTED (Sheets API 열거값 그대로)
- 두께 기준(용지 mm): <0.35 SOLID, <0.7 SOLID_MEDIUM, 그 이상 SOLID_THICK

## 성공 기준 (PoC)
- 합성 데이터(정답 있음): 행/열 수 100%, 병합 집합 100% 일치, 열 너비/행 높이 상대오차 평균 3% 이하, 최대 5% 이하
- 실사진 7장: 시트 PDF와 보정 원본의 격자선 위치 오차 중앙값 1mm 이하, 디버그 오버레이 육안 확인

## 실행 환경
- 맥에는 numpy 등 C 확장이 막혀 있다. 모든 파이썬 실행은 elgrim(ssh 별칭 `elgrim`)의 docker 컨테이너에서.
- elgrim 동기화 경로: `~/sheetparser`. 60초 넘는 작업은 nohup + 로그 폴링 (긴 ssh 동기 실행은 끊김).
- `vlm` 컨테이너(Qwen3-VL-32B, GPU 두 장 사용)는 절대 중지/재시작하지 않는다.
- Apps Script 웹앱 URL/키는 `.env`(git 제외)에: `SHEETS_WEBAPP_URL=`, `SHEETS_WEBAPP_KEY=`
