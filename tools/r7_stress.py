"""잘림/분할 경로 강제 시험(서버 설정은 그대로, 파이썬 쪽 한도만 줄인다).
  paddle: PADDLE_MAX=40 -> 긴 칸이 잘려 2배 재요청 불가 -> 그 칸만 32B
  32B 표: CTX=3600 -> 표 호출이 컨텍스트 보호로 미리 행을 나눠 전송
  32B 단일 호출 잘림: est 한도를 1/4 로 줄여 length -> 2배 재요청"""
import json, sys, collections, re
sys.path.insert(0, ".")
import fitz
from sheetparser import ocr as OCR, photopage as PP, convert as CV
import cv2
gt = collections.Counter(re.sub(r"\s+", "", fitz.open("data/pdfs/activity_09.pdf")[0].get_text()))
def score(sp):
    got = collections.Counter(re.sub(r"\s+", "", "".join(c.get("text", "") for c in sp["cells"])))
    return sum((gt & got).values()), sum((got - gt).values())
mode = sys.argv[1]
if mode == "paddle":
    OCR.PADDLE_MAX = 40
    sp = PP.run_page("data/pdfs/activity_09_300dpi.png")
    print("paddle", score(sp), sp["meta"]["trunc"], sp["meta"].get("ocr_backend"), sp["meta"].get("auto_fallback"))
elif mode == "ctx":
    OCR.CTX = 3600
    img = CV._render_scan("data/pdfs/scan_activity_09.pdf", "/tmp", "s")
    sp = PP.run_page("/tmp/s_300dpi.png", source_path="x", img0=img, kind="pdf_scan")
    print("ctx", score(sp), sp["meta"]["trunc"], sp["meta"]["vlm"], sp["meta"]["chunks"] if "chunks" in sp["meta"] else None)
else:
    orig = OCR.est_tokens
    OCR.est_tokens = lambda crop, **k: max(8, orig(crop, **k) // 6)
    img = CV._render_scan("data/pdfs/scan_activity_09.pdf", "/tmp", "s")
    sp = PP.run_page("/tmp/s_300dpi.png", source_path="x", img0=img, kind="pdf_scan")
    print("est", score(sp), sp["meta"]["trunc"], sp["meta"]["vlm"])
