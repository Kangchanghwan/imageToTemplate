"""run_all.sh 로그(runs/bro/<variant>.log) -> 변형별 요약표. 사용: summarize.py runs/bro v1 v2 ..."""
import json, re, sys
d = sys.argv[1]
vs = sys.argv[2:]
PDFN = ["attendance_09_photo", "attendance_09_scan", "activity_09_photo", "activity_09_scan", "meal_09_photo", "meal_09_scan"]
SCH = ["sched_09", "sched_10", "sched_11", "sched_12"]
FRM = ["form_activity", "form_attendance", "form_meal"]
def parse(v):
    R = {}
    last = None
    for l in open("%s/%s.log" % (d, v), encoding="utf-8"):
        m = re.match(r"ACC (\S+)", l)
        if m:
            last = m.group(1)
        if l.startswith("{") and "chars_ok" in l:
            R.setdefault(last, {}).update({k: x for k, x in json.loads(l).items() if k in ("chars_ok", "chars_total")})
        m = re.match(r"ACC (\S+) .*?(\{.*)", l)
        if m and "chars_ok" in m.group(2):
            R.setdefault(m.group(1), {}).update({k: x for k, x in json.loads(m.group(2)).items() if k in ("chars_ok", "chars_total")})
        elif m and "cells_ok" in m.group(2):
            a = re.search(r'"cells_total": (\d+), "cells_ok": (\d+)', m.group(2)); R.setdefault(m.group(1), {}).update(cells_ok=int(a.group(2)), cells_total=int(a.group(1)))
        m = re.match(r"(\S+) STRUCT (\{.*)", l)
        if m:
            j = json.loads(m.group(2)); R.setdefault(m.group(1), {}).update(text_ok=j["text_ok"], text_n=j["text_n"], struct=j["rows_ok"] and j["cols_ok"] and j["merge_exact"])
        m = re.match(r"== (\S+) \[.*\] ([\d.]+)s", l)
        if m:
            R.setdefault(m.group(1), {})["sec"] = float(m.group(2))
    return R
print("| 변형 | PDF 6건 칸별 | PDF 6건 글자 | 근무일정표 4장 | 서식 3장 | 구조 일치 | 6건 합계초 |")
print("|---|---|---|---|---|---|---|")
for v in vs:
    R = parse(v)
    g = lambda ns, a, b: (sum(R[n][a] for n in ns if n in R), sum(R[n][b] for n in ns if n in R))
    t = g(PDFN, "text_ok", "text_n"); c = g(PDFN, "chars_ok", "chars_total"); s = g(SCH, "cells_ok", "cells_total"); f = g(FRM, "cells_ok", "cells_total")
    st = sum(1 for n in PDFN if R.get(n, {}).get("struct"))
    sec = sum(R[n].get("sec", 0) for n in PDFN + SCH + FRM if n in R)
    print("| %s | %d/%d | %d/%d | %d/%d | %d/%d | %d/6 | 13건 %.0fs |" % (v, t[0], t[1], c[0], c[1], s[0], s[1], f[0], f[1], st, sec))
