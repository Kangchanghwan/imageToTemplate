import glob, json, re, sys
sys.path.insert(0, ".")
import cv2, fitz, numpy as np
from sheetparser import upload as UP, pdfvec as PV
keep = {"v2_sched_09", "v2_form_attendance"}
ids = {}
for line in open("runs/ver.log"):
    if line.startswith("{"):
        d = json.loads(line); ids.setdefault(d["name"], []).append(d["url"])
for f in glob.glob("runs/verify/*_verify.json"):
    d = json.load(open(f)); 
    if d.get("url"): ids.setdefault("old_" + d["name"], []).append(d["url"])
cur = {}
for line in open("runs/ver2.log"):
    if line.startswith("{"):
        d = json.loads(line); cur[d["name"]] = d["url"]
dele = []
for n, us in ids.items():
    dele += us
dele += [u for n, u in cur.items() if n not in keep]
for u in dele:
    i = re.search(r"/d/([^/]+)", u).group(1)
    try: r = UP.call("delete", id=i); print("del", i[:8], r.get("ok"))
    except Exception as e: print("del fail", i[:8], repr(e)[:80])
print("KEEP", {n: u for n, u in cur.items() if n in keep})
for n in ["sched_09", "form_attendance"]:
    rect = cv2.imread("runs/r2h/dbg/%s_rectified.jpg" % n)
    pdf = fitz.open("runs/r2h/verify/v2_%s_sheet.pdf" % n)[0]
    sh = PV.render(pdf, 10)
    H = min(rect.shape[0], sh.shape[0]); W = 2100
    a = cv2.resize(rect[:H, :W], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    b = cv2.resize(sh[:H, :W], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    cv2.imwrite("runs/r2h/side_%s.png" % n, np.hstack([a, b]))
