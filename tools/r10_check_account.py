"""새 계정(웹앱) 점검: create -> pdf -> 선 간격 실측 -> list -> delete. 사용: python tools/r10_check_account.py"""
import json, sys, time
sys.path.insert(0, ".")
import fitz
from sheetparser import upload as UP
spec = json.load(open("tests/fixtures/sample_spec.json"))
t = time.time()
r = UP.upload(spec, title="r10_account_check")
print("create", {k: (v if k not in ("url",) else "<url>") for k, v in r.items()}, round(time.time()-t, 1), "s")
sid, gid = r["id"] if "id" in r else r["spreadsheetId"], r.get("gid", 0)
pdf = UP.export_pdf(sid, gid)
open("tmp_check.pdf", "wb").write(pdf)
d = fitz.open("tmp_check.pdf"); p = d[0]
print("pdf pages", len(d), "size pt", p.rect.width, p.rect.height)
xs, ys = [], []
for dr in p.get_drawings():
    for it in dr["items"]:
        if it[0] == "l":
            a, b = it[1], it[2]
            if abs(a.x - b.x) < .1 and abs(a.y - b.y) > 5: xs.append(round(a.x, 2))
            if abs(a.y - b.y) < .1 and abs(a.x - b.x) > 5: ys.append(round(a.y, 2))
        if it[0] == "re":
            q = it[1]
            if q.width < 1.5 and q.height > 5: xs.append(round(q.x0, 2))
            if q.height < 1.5 and q.width > 5: ys.append(round(q.y0, 2))
def uniq(v):
    o = []
    for a in sorted(v):
        if not o or a - o[-1] > 1: o.append(a)
    return o
xs, ys = uniq(xs), uniq(ys)
print("vlines pt", xs); print("hlines pt", ys)
cx = [0]; 
for c in spec["columns"]: cx.append(cx[-1] + c)
ry = [0]
for c in spec["rows"]: ry.append(ry[-1] + c)
print("expected col px", spec["columns"], "measured col pt pitch", [round(b-a,2) for a,b in zip(xs, xs[1:])], "-> pt/px", [round((b-a)/c,4) for (a,b),c in zip(zip(xs, xs[1:]), spec["columns"])])
print("expected row px", spec["rows"], "measured row pt pitch", [round(b-a,2) for a,b in zip(ys, ys[1:])], "-> pt/px", [round((b-a)/c,4) for (a,b),c in zip(zip(ys, ys[1:]), spec["rows"])])
l = UP.call("list"); print("list count", l["count"], [f["name"] for f in l["files"]][:5])
print("create url folder check: list contains", any(f["id"] == sid for f in l["files"]))
print("delete", UP.call("delete", id=sid))
print("list after", UP.call("list")["count"])
