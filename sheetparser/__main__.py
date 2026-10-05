import argparse
import glob
import json
import os
import sys
import time


def fmt(v, p=1, pct=False):
    if v is None: return "-"
    if isinstance(v, bool): return "O" if v else "X"
    return ("%.*f" % (p, v * 100) + "%") if pct else "%.*f" % (p, v)


def bench(d, out, ocr_n, modes):
    from . import pipeline, score
    rows = []
    os.makedirs(out, exist_ok=True)
    names = sorted(os.path.basename(p)[:-4] for p in glob.glob(os.path.join(d, "s??.pdf")))
    for mode in modes:
        for k, nm in enumerate(names):
            gt = json.load(open(os.path.join(d, nm + ".json")))
            use_ocr = mode == "photo" and k < ocr_n and ocr_n > 0
            t = time.time()
            try:
                if mode == "vector":
                    sp = pipeline.run_pdf(os.path.join(d, nm + ".pdf"), debug_dir=os.path.join(out, "dbg_v"))
                else:
                    sp = pipeline.run_image(os.path.join(d, nm + "_photo.jpg"), ocr=use_ocr,
                                            debug_dir=os.path.join(out, "dbg_p"))
                json.dump(sp, open(os.path.join(out, "%s_%s.json" % (nm, mode)), "w"), ensure_ascii=False)
                s = score.score(sp, gt)
                s["fail"] = None
            except Exception as e:
                s = {"fail": repr(e)}
            s.update({"name": nm, "mode": mode, "ocr": use_ocr, "sec": round(time.time() - t, 1)})
            rows.append(s)
            print(json.dumps(s, ensure_ascii=False), flush=True)
    json.dump(rows, open(os.path.join(out, "bench.json"), "w"), ensure_ascii=False, indent=1)
    lines = ["| 파일 | 경로 | 행 | 열 | 병합F1 | 열폭 평균% | 열폭 최대% | 행높이 평균% | 행높이 최대% | 경계 | 정렬 | CER | 초 |",
             "|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for s in rows:
        if s.get("fail"):
            lines.append("| %s | %s | FAIL %s |" % (s["name"], s["mode"], s["fail"][:60])); continue
        lines.append("| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |" % (
            s["name"], s["mode"] + ("+ocr" if s["ocr"] else ""), fmt(s["rows_ok"]), fmt(s["cols_ok"]),
            fmt(s["merge_f1"], 2), fmt(s["col_mean"], 2), fmt(s["col_max"], 2), fmt(s["row_mean"], 2),
            fmt(s["row_max"], 2), fmt(s["border_acc"], 0, True), fmt(s["align_acc"], 0, True),
            fmt(s["cer"], 1, True), s["sec"]))
    md = "\n".join(lines)
    open(os.path.join(out, "bench.md"), "w").write(md)
    print(md)


def main():
    ap = argparse.ArgumentParser(prog="sheetparser")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run"); r.add_argument("input"); r.add_argument("-o", required=True)
    r.add_argument("--no-ocr", action="store_true"); r.add_argument("--v1", action="store_true"); r.add_argument("--debug-dir")
    s = sub.add_parser("score"); s.add_argument("pred"); s.add_argument("gt")
    y = sub.add_parser("synth"); y.add_argument("-o", required=True); y.add_argument("-n", type=int, default=12)
    b = sub.add_parser("bench"); b.add_argument("dir"); b.add_argument("-o", default="runs/bench")
    b.add_argument("--ocr-n", type=int, default=0); b.add_argument("--modes", default="vector,photo")
    u = sub.add_parser("upload"); u.add_argument("spec"); u.add_argument("--title")
    v = sub.add_parser("verify"); v.add_argument("spec"); v.add_argument("-o", default="runs/verify")
    v.add_argument("--keep", action="store_true", help="시트를 지우지 않는다(기본도 유지)"); v.add_argument("--delete", action="store_true")
    cv = sub.add_parser("convert", help="입력(pdf/jpg/png) 자동 판별 -> 시트 -> 검증 요약")
    cv.add_argument("input"); cv.add_argument("-o", default=None); cv.add_argument("--title")
    cv.add_argument("--verify", action="store_true", help="시트 PDF 내보내기 + 원본 겹쳐 채점 + 정답 채점 (기본은 업로드 후 URL만)")
    cv.add_argument("--ocr-backend", default="qwen32b", choices=["paddle", "qwen8b", "qwen32b", "hybrid"],
                    help="사진 경로 OCR 백엔드 (기본 qwen32b). 주소는 환경변수 VLM_URL / VLM8_URL / PADDLE_URL")
    cv.add_argument("--keep", action="store_true", help="시트 유지 (기본 동작)"); cv.add_argument("--delete", action="store_true", help="검증 후 시트 삭제")
    a = ap.parse_args()
    if a.cmd == "run":
        from . import pipeline
        sp = pipeline.run(a.input, ocr=not a.no_ocr, debug_dir=a.debug_dir, v1=a.v1)
        json.dump(sp, open(a.o, "w"), ensure_ascii=False, indent=1)
        print("rows=%d cols=%d merges=%d" % (len(sp["rows"]), len(sp["columns"]),
              sum(1 for c in sp["cells"] if c["rs"] > 1 or c["cs"] > 1)))
    elif a.cmd == "score":
        from . import score
        print(json.dumps(score.score(json.load(open(a.pred)), json.load(open(a.gt))), ensure_ascii=False, indent=1))
    elif a.cmd == "synth":
        from . import synth
        synth.synth(a.o, a.n)
    elif a.cmd == "bench":
        bench(a.dir, a.o, a.ocr_n, a.modes.split(","))
    elif a.cmd == "upload":
        from . import upload
        print(json.dumps(upload.upload(json.load(open(a.spec)), a.title or os.path.basename(a.spec)), ensure_ascii=False))
    elif a.cmd == "convert":
        from . import convert, ocr
        ocr.set_backend(a.ocr_backend)
        convert.convert(a.input, a.o, a.title, delete=a.delete and not a.keep, verify_on=a.verify)
    elif a.cmd == "verify":
        from . import verify
        verify.main(a.spec, a.o, a.delete)


main()
