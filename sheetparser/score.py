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


# ---- v2: 사진 내용 채점 (data/photos/gt_content.json) ----
SCHED_HEAD = ["날짜", "요일", "근무시간(휴게30분포함)", "실근무시간", "비고"]


def _fmt_hours(h):
    return ("%g" % h)


def _ntime(s):
    s = _norm(s).replace("∼", "~").replace("～", "~")
    return re.sub(r"\([^)]*\)$", "", s)


def _num_eq(a, b):
    try:
        return abs(float(_norm(a)) - float(b)) < 1e-6
    except ValueError:
        return False


def content_score(spec, gt_all, name):
    """반환: {"cells_total","cells_ok","acc","wrong":[...]} (schedules) 또는 필수 문구 포함 여부(forms), 블록 포함 여부"""
    tcells = [c for c in spec["cells"] if c.get("role", "table") == "table"]
    rows = sorted({c["r"] for c in tcells})
    ridx = {r: i for i, r in enumerate(rows)}
    mat = {}
    for c in tcells:
        mat[(ridx[c["r"]], c["c"])] = c.get("text", "")
    cols = sorted({c["c"] for c in tcells})
    cidx = {c: i for i, c in enumerate(cols)}
    mat = {(r, cidx[c]): t for (r, c), t in mat.items()}
    alltext = _norm("".join(c.get("text", "") for c in spec["cells"]))
    btext = _norm("".join(c.get("text", "") for c in spec["cells"] if c.get("role") == "text"))
    out = {}
    if name in gt_all["schedules"]:
        g = gt_all["schedules"][name]
        n = ok = 0
        wrong = []

        def chk(r, k, good, exp):
            nonlocal n, ok
            n += 1
            if good:
                ok += 1
            else:
                wrong.append("r%d c%d 정답=%r 예측=%r" % (r, k, exp, mat.get((r, k), "")))
        for k, h in enumerate(SCHED_HEAD):
            chk(0, k, _norm(mat.get((0, k), "")) == _norm(h), h)
        tot = [r for r in range(len(rows)) if any("총" in mat.get((r, k), "") for k in range(len(cols)))]
        trow = tot[-1] if tot else len(g["rows"]) + 1
        for i, row in enumerate(g["rows"]):
            r = i + 1
            chk(r, 0, _norm(mat.get((r, 0), "")) == _norm(row["date"]), row["date"])
            chk(r, 1, _norm(mat.get((r, 1), "")) == _norm(row["weekday"]), row["weekday"])
            exp_t = "%s~%s" % (row["start"], row["end"])
            chk(r, 2, _ntime(mat.get((r, 2), "")) == exp_t, exp_t)
            chk(r, 3, _num_eq(mat.get((r, 3), ""), row["hours"]), row["hours"])
            chk(r, 4, _norm(mat.get((r, 4), "")) == _norm(row["note"]), row["note"])
        r = trow
        chk(r, 2, _norm(mat.get((r, 2), "")) == _norm("총 %d일 근무" % g["total_days"]), "총 %d일 근무" % g["total_days"])
        chk(r, 3, _num_eq(mat.get((r, 3), ""), g["total_hours"]), g["total_hours"])
        chk(r, 0, _norm(mat.get((r, 0), "")) == "", "")
        chk(r, 1, _norm(mat.get((r, 1), "")) == "", "")
        chk(r, 4, _norm(mat.get((r, 4), "")) == "", "")
        out.update({"cells_total": n, "cells_ok": ok, "acc": ok / n, "wrong": wrong,
                    "rows_match": trow == len(g["rows"]) + 1})
        out["block_ok"] = "근무일정표" in btext
    elif name in gt_all["forms"]:
        f = gt_all["forms"][name]
        heads = [_norm(h[0]) for h in f["columns"]]
        miss = [h for h in heads if h not in alltext]
        must = [_norm(m) for m in f["header_must"] + f["footer_must"]]
        miss_b = [m for m in must if m not in alltext]
        out.update({"cells_total": len(heads), "cells_ok": len(heads) - len(miss), "acc": 1 - len(miss) / max(1, len(heads)),
                    "wrong": miss, "block_ok": not miss_b, "block_missing": miss_b})
    out["block_text"] = [c.get("text", "") for c in spec["cells"] if c.get("role") == "text"]
    return out
