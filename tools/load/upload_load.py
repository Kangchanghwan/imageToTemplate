"""Apps Script 웹앱 create/delete 동시성 측정. 총 create 수를 제한한다(일일 한도 보호).
  python tools/load/upload_load.py                 # 계획: N=1 x3, 3 x6(2회), 6 x6, 12 x12 + 실제 크기 spec 1회
재시도 없이 요청 1회만 보내 에러를 그대로 기록한다(재시도가 시트를 중복 생성하지 않도록). 결과 runs/load/E.json"""
import json, os, sys, time, urllib.request, urllib.error
from concurrent.futures import ThreadPoolExecutor
sys.path.insert(0, os.getcwd())
from sheetparser import upload as UP, convert as CV, ocr as OCR

URL, KEY = UP._env()
CREATED = []


def raw(action, **kw):
    body = json.dumps(dict(key=KEY, action=action, **kw)).encode()
    req = urllib.request.Request(URL, data=body, headers={"Content-Type": "application/json"})
    t = time.time()
    try:
        r = json.load(urllib.request.urlopen(req, timeout=120))
        if r.get("msg") == "sheetparser-writer":
            return {"ok": False, "err": "doGet status msg", "sec": time.time() - t}
        r["sec"] = time.time() - t
        return r
    except urllib.error.HTTPError as e:
        return {"ok": False, "err": "HTTP %s %s" % (e.code, e.read()[:120]), "sec": time.time() - t}
    except Exception as e:
        return {"ok": False, "err": repr(e)[:160], "sec": time.time() - t}


UP.call = lambda action, **kw: raw(action, **kw)   # UP.upload 의 변환(열 -1, sheet_pt)을 그대로 쓰되 재시도 없이


def one(args):
    spec, title = args
    t = time.time()
    r = UP.upload(spec, title)
    t_create = time.time() - t
    out = {"create_sec": t_create, "ok": bool(r.get("ok")), "err": None if r.get("ok") else str(r.get("err") or r.get("error"))[:160]}
    if r.get("id"):
        CREATED.append(r["id"])
        d = raw("delete", id=r["id"])
        out["delete_sec"] = d["sec"]; out["delete_ok"] = bool(d.get("ok"))
        if d.get("ok"): CREATED.remove(r["id"])
    return out


def pct(v, p):
    v = sorted(v)
    if not v: return None
    k = (len(v) - 1) * p; f = int(k); c = min(f + 1, len(v) - 1)
    return round(v[f] + (v[c] - v[f]) * (k - f), 2)


def batch(spec, n, rounds, label):
    res = []
    t0 = time.time()
    for k in range(rounds):
        with ThreadPoolExecutor(n) as ex:
            res += list(ex.map(one, [(spec, "load_%s_%d_%d" % (label, k, i)) for i in range(n)]))
    wall = time.time() - t0
    c = [r["create_sec"] for r in res if r["ok"]]
    s = {"label": label, "n": n, "creates": len(res), "ok": len(c), "fail": len(res) - len(c), "wall": round(wall, 1),
         "create_p50": pct(c, .5), "create_p95": pct(c, .95), "create_max": round(max(c), 2) if c else None,
         "delete_p50": pct([r["delete_sec"] for r in res if "delete_sec" in r], .5),
         "errs": sorted({r["err"] for r in res if r["err"]})[:4], "per_min": round(60 * len(c) / wall, 1)}
    print(json.dumps(s, ensure_ascii=False), flush=True)
    return s


if __name__ == "__main__":
    small = json.load(open("tests/fixtures/sample_spec.json"))
    out = []
    for n, rounds in ((1, 3), (3, 2), (6, 1), (12, 1)):
        s = batch(small, n, rounds, "small%d" % n)
        out.append(s)
        if s["fail"] > max(2, s["creates"] // 2):
            print("too many failures, stopping"); break
        time.sleep(3)
    OCR.set_backend("auto")
    sm = CV.convert("data/photos/form_activity.jpg", "runs/load/e_spec", "load_e_activity", no_upload=True)
    big = json.load(open(sm["spec"]))
    out.append(batch(big, 1, 1, "activity_real"))
    # 남은 시트 정리
    for i in list(CREATED):
        raw("delete", id=i)
    json.dump(out, open("runs/load/E.json", "w"), ensure_ascii=False)
    print("created_total", sum(s["creates"] for s in out))
