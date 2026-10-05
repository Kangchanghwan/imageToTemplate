"""TableSpec -> Apps Script 웹앱 (시트 생성 / PDF 내보내기 / 삭제)."""
import base64
import copy
import json
import os
import urllib.request


SHEET_PT_SCALE = 0.975


def _env():
    root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    env = {}
    for line in open(os.path.join(root, ".env")):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip('"').strip("'")
    return env["SHEETS_WEBAPP_URL"], env["SHEETS_WEBAPP_KEY"]


def call(action, **kw):
    url, key = _env()
    body = json.dumps(dict(key=key, action=action, **kw)).encode()
    # urllib는 302에서 POST를 GET으로 바꿔 따라간다 (curl -L 과 동일)
    req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
    return json.load(urllib.request.urlopen(req, timeout=120))


def upload(spec, title="sheetparser"):
    """실측 보정: 열 너비는 시트에서 (px+1)*0.75pt 로 그려지므로 업로드 직전에만 각 열에서 1을 뺀다."""
    s = copy.deepcopy(spec)
    s["columns"] = [max(1, c - 1) for c in s["columns"]]
    s.pop("meta", None)
    for c in s["cells"]:  # Sheets API font_size 는 int32
        c["size_pt"] = c.pop("sheet_pt", None) or max(1, int(c["size_pt"] / SHEET_PT_SCALE + 0.5))  # 시트 PDF 내보내기는 글자를 0.975배로 그린다 (실측)
    return call("create", spec=s, title=title)


def export_pdf(sheet_id, gid):
    r = call("pdf", id=sheet_id, gid=gid)
    data = r.get("pdf_b64") or r.get("pdf") or r.get("base64") or r.get("data")
    if data is None:
        raise RuntimeError("pdf action response keys: %s" % list(r.keys()))
    return base64.b64decode(data)
