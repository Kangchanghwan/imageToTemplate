"""오류 유형 분류: runs/bro/<variant>.log 의 틀린 칸(정답/예측)을 규칙으로 분류. 사용: errors.py runs/bro v1 v2 ..."""
import json, re, sys
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]")
def cls(gt, pr):
    ws = lambda s: re.sub(r"\s+", "", s)
    if pr == "<서식 문구 누락>":
        return "서식 문구 누락"
    if not pr.strip():
        return "빈 칸"
    if HAN.search(pr):
        return "한자 혼입"
    if "\n" in pr and ws(pr) == ws(gt):
        return "줄바꿈"
    if len(ws(gt)) >= 18:
        return "긴 칸(18자+)"
    if re.search(r"[_|=—\-~·.,'\"]{2,}|[_|=]\s*$|^[|=\-]", pr) and re.sub(r"[_|=—\-~\s'\"]", "", pr).startswith(re.sub(r"[_|=—\-~\s'\"]", "", gt)[:3]):
        return "표선/기호 잔재"
    if re.fullmatch(r"[\d/:~.,\-\s()]*", ws(gt)) or re.fullmatch(r"[\d/:~.,\-\s()]*", ws(pr)):
        return "숫자/기호"
    return "한글 오독"
def wrongs(v):
    out = []
    for l in open("%s/%s.log" % (sys.argv[1], v), encoding="utf-8"):
        m = re.match(r"ACC (sched_\d+|form_\w+) (\{.*)", l)
        if m:
            a = re.search(r'"wrong": \[(.*)\], "block_ok"', m.group(2))
            if not a or not a.group(1).strip():
                continue
            for it in re.split(r'", "(?=r\d+ c\d+ 정답=)', a.group(1).strip().strip('"')) if m.group(1).startswith("sched") else [None]:
                if it is None:
                    for ph in re.findall(r'"([^"]+)"', a.group(1)):
                        out.append((m.group(1), ph, "<서식 문구 누락>"))
                    continue
                k = re.match(r"r\d+ c\d+ 정답=(.*?) 예측=(.*)$", it, re.S)
                if k:
                    out.append((m.group(1), k.group(1).strip("'\""), k.group(2).strip("'\"").replace("\\n", "\n")))
        m = re.match(r"(\S+) STRUCT (\{.*)", l)
        if m:
            j = json.loads(m.group(2))
            for w in j["text_wrong"]:
                k = re.search(r"정답='(.*?)' 예측='(.*)'$", w, re.S) if isinstance(w, str) else None
                out.append((m.group(1), k.group(1), k.group(2)) if k else (m.group(1), str(w), "?"))
    return out
cats = ["서식 문구 누락", "빈 칸", "한자 혼입", "줄바꿈", "긴 칸(18자+)", "표선/기호 잔재", "숫자/기호", "한글 오독"]
print("| 변형 | 틀린 칸 | " + " | ".join(cats) + " |")
print("|---|---|" + "---|" * len(cats))
for v in sys.argv[2:]:
    w = wrongs(v)
    c = {k: 0 for k in cats}
    for _, g, p in w:
        c[cls(g, p)] += 1
    print("| %s | %d | %s |" % (v, len(w), " | ".join(str(c[k]) for k in cats)))
