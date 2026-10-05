"""예측 TableSpec vs 정답 채점."""
import re


def lev(a, b):
    if not a: return len(b)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a, 1):
        cur = [i]
        for j, cb in enumerate(b, 1):
            cur.append(min(prev[j] + 1, cur[-1] + 1, prev[j - 1] + (ca != cb)))
        prev = cur
    return prev[-1]


def _norm(s):
    return re.sub(r"\s+", "", s or "")


def score(p, g):
    out = {}
    out["rows_ok"] = len(p["rows"]) == len(g["rows"])
    out["cols_ok"] = len(p["columns"]) == len(g["columns"])
    mp = {(c["r"], c["c"], c["rs"], c["cs"]) for c in p["cells"] if c["rs"] > 1 or c["cs"] > 1}
    mg = {(c["r"], c["c"], c["rs"], c["cs"]) for c in g["cells"] if c["rs"] > 1 or c["cs"] > 1}
    tp = len(mp & mg)
    out["merge_f1"] = 1.0 if not mp and not mg else (2 * tp / (len(mp) + len(mg)))
    out["merge_exact"] = mp == mg
    nan = None
    for key, k in (("col", "columns"), ("row", "rows")):
        if len(p[k]) == len(g[k]):
            e = [abs(a - b) / b * 100 for a, b in zip(p[k], g[k])]
            out[key + "_mean"], out[key + "_max"] = sum(e) / len(e), max(e)
        else:
            out[key + "_mean"] = out[key + "_max"] = nan
    if out["rows_ok"] and out["cols_ok"]:
        n = ok = 0
        for k in ("h", "v"):
            for ra, rb in zip(p["borders"][k], g["borders"][k]):
                for a, b in zip(ra, rb):
                    n += 1; ok += a == b
        out["border_acc"] = ok / n
    else:
        out["border_acc"] = nan
    pc = {(c["r"], c["c"], c["rs"], c["cs"]): c for c in p["cells"]}
    n = ok = 0
    for c in g["cells"]:
        if not c["text"]: continue
        q = pc.get((c["r"], c["c"], c["rs"], c["cs"]))
        n += 1
        if q and q["h"] == c["h"] and q["v"] == c["v"]: ok += 1
    out["align_acc"] = ok / n if n else nan
    out["align_n"] = n
    # CER
    pt = {(c["r"], c["c"]): c["text"] for c in p["cells"]}
    ed = tot = 0
    has = any(c["text"] for c in p["cells"])
    for c in g["cells"]:
        t = _norm(c["text"])
        if not t: continue
        ed += lev(_norm(pt.get((c["r"], c["c"]), "")), t); tot += len(t)
    out["cer"] = ed / tot if (tot and has) else nan
    return out
