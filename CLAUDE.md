# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

`sheetparser` converts table documents (vector PDF, scanned PDF, photo) into a Google Sheet that visually overlaps the original page (lines, column widths/row heights, merges, fills, font size/bold, text outside the table). Docs and comments are in Korean; see `README.md` for the detailed rationale, unit constants and operations notes, and `docs/SPEC.md` (PageSpec format), `docs/RESULTS.md` (per-round history), `docs/WEB_PORT.md`, `docs/BROWSER_OCR.md`.

Core principle: **structure (grid) is fixed by CV or PDF vectors; text comes from the PDF text layer or a VLM/OCR. The model never creates structure.**

## Pipeline (spans several files)

`convert.detect` classifies input, then:
- `pdf_vector` → `pdfvec.py` + `pipeline.run_pdf_page`
- `pdf_scan` (PDF with no text) → render 300dpi, normalize to 10px/mm → `photopage.run_page` (skip perspective correction)
- `photo` (jpg/png) → `preprocess.rectify` → `photopage.run_page` (uses `grid.py` for lines/merges, `style.py` for style, `ocr.py` for VLM calls)

Then `layout.build_page_spec` (table + out-of-table blocks + images → full-page grid, PageSpec v2) → `upload.py` → Apps Script web app (`apps_script/Code.gs`) → Google Sheet → optional `verify.py` / `verify_photo.py` (export sheet as A4 PDF, overlay against original, score).

OCR backend (`auto`): photos use PaddleOCR-VL; scan PDFs and paddle results with anomalies fall back to Qwen3-VL-32B. Both are llama.cpp servers on the `elgrim` host (`127.0.0.1:18003` paddle, `127.0.0.1:18001` vlm). Calibration constants (px/mm, 0.975 font factor, 1px column subtraction, baseline shift, line thickness thresholds) are documented in README "단위 규칙과 실측 보정값" — read it before touching layout/style code, because values are empirically measured against the Sheets PDF export.

`web/` is an ES-module port of the photo/scan CV path (OpenCV.js, pdf.js, onnxruntime) that runs in both browser and Node, aiming for numeric parity with the Python code. When changing `grid.py`, `preprocess.py`, `style.py`, `photopage.py` or `layout.py`, the JS counterparts in `web/src/` (function mapping table in `docs/WEB_PORT.md`) may need the same change; `tools/parity/` compares the two stage by stage.

## Commands

Python runs inside the `sheetparser` docker image (opencv, pymupdf, fonts-nanum; `docker/Dockerfile`) on the remote host `elgrim`, not locally. There is no Python test suite; verification is scoring scripts.

```sh
tools/dk.sh -m sheetparser convert data/photos/sched_09.jpg -o runs/convert/sched_09 --title v3_sched_09   # rsync to elgrim + docker run (dkbg.sh for >60s runs)
tools/pull.sh                                   # fetch elgrim runs/
python -m sheetparser convert <in.pdf|jpg|png> [-o dir] [--title T] [--verify] [--keep|--delete] [--no-upload] [--ocr-backend auto|qwen32b|...]
python tools/accuracy.py photo <spec.json> <name>   # offline ground-truth scoring of a spec
tools/run_r10.sh <prefix>                       # regression: spec-level scoring, creates NO sheets
tools/run_r10.sh <prefix> --sheets              # real sheet creation + PDF verify (only for the 2 representative inputs)
tools/dk.sh tools/cleanup.py --keep-prefix v3_  # delete non-matching sheets in the sheetparser-poc folder
```

Web (in `web/`): `npm install`, `npm test` (node --test; single file: `node --test test/npy.test.mjs`). Parity run: `tools/parity/run.sh [names...]`.

Needs `.env` (git-ignored) with `SHEETS_WEBAPP_URL`, `SHEETS_WEBAPP_KEY`.

## Rules to follow

- Google Sheets has a daily "spreadsheets created" quota (250 personal / 3,200 Workspace). Regressions must score at the spec stage (`--no-upload`); only create sheets for the representative inputs.
- Apps Script can respond with 404 and `create` may duplicate; `tools/cleanup.py` keeps the newest of same-named sheets.
- Ground truth for photos: `data/photos/gt_content.json`. Generated dirs (`runs/`, `data/synth`, `data/pdfs`, `data/scan`, `web/models`, `web/node_modules`, `tools/parity/out*`) are git-ignored.
