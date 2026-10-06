"""근무일정표 사진 4장: 열별 정렬/굵기/크기 일관성(열 안 분산). 정답 서식이 없어 열 안에서 값이 몇 종류인지 본다.
사용: sched_consist.py runs/<접두> (r9_sched_*.json)"""
import glob, json, sys
from collections import Counter
for f in sorted(glob.glob(sys.argv[1] + "/sched_*/r9_sched_*.json")):
    s = json.load(open(f)); cols = {}
    for c in s["cells"]:
        if c.get("role") == "table" and c["text"] and c["r"] > min(x["r"] for x in s["cells"] if x.get("role") == "table") and c["cs"] == 1:
            cols.setdefault(c["c"], []).append(c)
    out = []
    for k in sorted(cols):
        cs = cols[k]
        h = Counter(c["h"] for c in cs); b = Counter(bool(c["bold"]) for c in cs); z = Counter(c["size_pt"] for c in cs)
        out.append("c%d n=%d h=%s b=%s sz=%s" % (k, len(cs), dict(h), dict(b), dict(z)))
    print(f.split("/")[-2]); [print("  " + o) for o in out]
