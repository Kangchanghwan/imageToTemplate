import glob, json, re, sys
sys.path.insert(0, ".")
import cv2, fitz, numpy as np
from sheetparser import upload as UP, pdfvec as PV
d = sys.argv[1]
keep = {"v2_sched_09", "v2_form_attendance"}
for f in sorted(glob.glob(d + "/verify/*_verify.json")):
    j = json.load(open(f))
    if j["name"] in keep:
        print("KEEP", j["name"], j["url"]); continue
    i = re.search(r"/d/([^/]+)", j["url"]).group(1)
    for k in range(4):
        try:
            print("del", j["name"], UP.call("delete", id=i).get("ok")); break
        except Exception as e:
            print("retry", j["name"], repr(e)[:60]); import time; time.sleep(5)
for n in ["sched_09", "form_attendance"]:
    rect = cv2.imread("%s/dbg/%s_rectified.jpg" % (d, n))
    sh = PV.render(fitz.open("%s/verify/v2_%s_sheet.pdf" % (d, n))[0], 10)
    H = min(rect.shape[0], sh.shape[0])
    a = cv2.resize(rect[:H, :2100], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    b = cv2.resize(sh[:H, :2100], None, fx=0.5, fy=0.5, interpolation=cv2.INTER_AREA)
    cv2.imwrite("%s/side_%s.png" % (d, n), np.hstack([a, b]))
