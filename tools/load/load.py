"""부하 측정 하네스. 컨테이너 1개 안에서 ProcessPoolExecutor(N)로 convert() 를 동시에 호출한다(프로세스별 ocr 전역 상태 분리).
  python tools/load/load.py photo --n 8 --reqs 24 --tag A8
  python tools/load/load.py scan --n 2 --reqs 4 --tag B2 [--files data/pdfs/scan_attendance_09.pdf,...]
  python tools/load/load.py mixed --n 8 --reqs 24 --tag C
  python tools/load/load.py pdf --n 8 --reqs 24 --tag D8
  python tools/load/load.py upload --tag E     (Apps Script create/delete, 총 생성 수 제한)
결과: runs/load/<tag>.json. 업로드 없음(no_upload=True) 외에는 convert 와 같은 경로."""
import argparse, glob, json, os, statistics, sys, time, shutil, uuid
import multiprocessing as mp
from concurrent.futures import ProcessPoolExecutor, as_completed

sys.path.insert(0, os.getcwd())
from sheetparser import convert as CV, ocr as OCR, score  # noqa: E402  (부모에서 미리 import, fork 로 공유)

PHOTOS = sorted(glob.glob("data/photos/*.jpg")) + ["data/pdfs/activity_09_300dpi.png"]
SCANS = ["data/pdfs/scan_attendance_09.pdf", "data/pdfs/scan_meal_09.pdf"]
DIGITAL = ["data/pdfs/activity_09.pdf", "data/pdfs/attendance_09.pdf", "data/pdfs/meal_09.pdf"]
GT = json.load(open("data/photos/gt_content.json"))
PLOG = []


def _patch():
    orig = OCR._paddle_one

    def wrapped(*a, **k):
        t = time.time()
        try:
            return orig(*a, **k)
        finally:
            PLOG.append(time.time() - t)
    OCR._paddle_one = wrapped


def work(path, tag, i):
    del PLOG[:]
    out = os.path.join("runs/load/out", "%s_%d_%s" % (tag, i, uuid.uuid4().hex[:6]))
    t = time.time()
    r = {"path": path, "i": i, "t0": t}
    try:
        s = CV.convert(path, out, "load_%s_%d" % (tag, i), no_upload=True)
        r["ok"] = True
        r["kind"] = s["kind"]; r["sec_spec"] = s["sec_spec"]; r["vlm"] = s.get("vlm"); r["fallback"] = s.get("auto_fallback")
        r["backend"] = s.get("ocr_backend")
        stem = os.path.splitext(os.path.basename(path))[0]
        if stem.startswith("sched_"):
            spec = json.load(open(s["spec"]))
            c = score.content_score(spec, GT, stem)
            r["cells_ok"], r["cells_total"] = c.get("cells_ok"), c.get("cells_total")
    except BaseException as e:
        r["ok"] = False; r["err"] = repr(e)[:300]
    r["lat"] = time.time() - t
    r["paddle_req"] = list(PLOG)
    shutil.rmtree(out, ignore_errors=True)
    return r


def init():
    _patch()
    import io, contextlib
    sys.stdout = open(os.devnull, "w")   # convert 의 출력 억제


def pct(v, p):
    v = sorted(v)
    if not v: return None
    k = (len(v) - 1) * p
    f = int(k); c = min(f + 1, len(v) - 1)
    return v[f] + (v[c] - v[f]) * (k - f)


def run(files, n, reqs, tag):
    os.makedirs("runs/load", exist_ok=True)
    jobs = [files[i % len(files)] for i in range(reqs)]
    with ProcessPoolExecutor(n, mp_context=mp.get_context("fork"), initializer=init) as ex:
        t0 = time.time()
        futs = [ex.submit(work, p, tag, i) for i, p in enumerate(jobs)]
        res = [f.result() for f in futs]
        wall = time.time() - t0
    return res, wall


def summarize(res, wall, n, tag):
    ok = [r for r in res if r["ok"]]
    lat = [r["lat"] for r in ok]
    pr = [x for r in ok for x in r["paddle_req"]]
    s = {"tag": tag, "n": n, "reqs": len(res), "ok": len(ok), "fail": len(res) - len(ok), "wall": round(wall, 1),
         "per_min": round(60 * len(ok) / wall, 2), "p50": pct(lat, .5), "p95": pct(lat, .95), "max": max(lat) if lat else None,
         "mean": statistics.mean(lat) if lat else None, "fallback": sum(1 for r in ok if r.get("fallback")),
         "paddle_reqs": len(pr), "paddle_p50": pct(pr, .5), "paddle_p95": pct(pr, .95), "paddle_max": max(pr) if pr else None,
         "errs": [r["err"] for r in res if not r["ok"]][:5]}
    sch = [r for r in ok if "cells_ok" in r]
    s["sched_cells"] = "%d/%d" % (sum(r["cells_ok"] for r in sch), sum(r["cells_total"] for r in sch)) if sch else None
    s["sched_n"] = len(sch)
    per = {}
    for r in ok:
        per.setdefault(os.path.basename(r["path"]), []).append(r["lat"])
    s["by_file_mean"] = {k: round(statistics.mean(v), 1) for k, v in per.items()}
    for k in ("p50", "p95", "max", "mean", "paddle_p50", "paddle_p95", "paddle_max"):
        if s[k] is not None: s[k] = round(s[k], 2)
    return s


def mixed(n_photo, reqs, tag):
    """사진 N 동시(닫힌 루프) + 스캔 1 동시. 스캔은 사진 구간 내내 1개씩 연속 요청."""
    from concurrent.futures import ThreadPoolExecutor
    out = {}
    with ProcessPoolExecutor(n_photo + 1, mp_context=mp.get_context("fork"), initializer=init) as ex:
        t0 = time.time()
        sc = ex.submit(work, SCANS[0], tag + "s", 0)
        time.sleep(3)   # 스캔 32B 호출이 시작된 뒤 사진 투입
        t1 = time.time()
        futs = [ex.submit(work, PHOTOS[i % len(PHOTOS)], tag + "p", i) for i in range(reqs)]
        pres = [f.result() for f in futs]
        t2 = time.time()
        sres = sc.result()
    return pres, t2 - t1, sres, time.time() - t0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("mode"); ap.add_argument("--n", type=int, default=1); ap.add_argument("--reqs", type=int, default=3)
    ap.add_argument("--tag", default="x"); ap.add_argument("--files", default="")
    a = ap.parse_args()
    OCR.set_backend("auto")
    files = a.files.split(",") if a.files else None
    if a.mode == "photo":
        res, wall = run(files or PHOTOS, a.n, a.reqs, a.tag)
        s = summarize(res, wall, a.n, a.tag)
    elif a.mode == "scan":
        res, wall = run(files or SCANS, a.n, a.reqs, a.tag)
        s = summarize(res, wall, a.n, a.tag)
    elif a.mode == "pdf":
        res, wall = run(files or DIGITAL, a.n, a.reqs, a.tag)
        s = summarize(res, wall, a.n, a.tag)
    elif a.mode == "mixed":
        pres, wall, sres, wall_all = mixed(a.n, a.reqs, a.tag)
        s = summarize(pres, wall, a.n, a.tag + "_photo")
        s["scan"] = {"ok": sres["ok"], "lat": round(sres["lat"], 1), "err": sres.get("err"), "vlm": sres.get("vlm")}
        res = pres + [sres]
    json.dump({"summary": s, "raw": res}, open("runs/load/%s.json" % a.tag, "w"), ensure_ascii=False)
    print(json.dumps(s, ensure_ascii=False), flush=True)
