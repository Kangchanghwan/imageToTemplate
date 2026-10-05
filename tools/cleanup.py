"""sheetparser-poc 폴더 정리. 사용: python tools/cleanup.py [--keep-prefix v3_] [--dry]
list 액션으로 폴더 파일을 받아 --keep-prefix 로 시작하지 않는 것을 모두 휴지통으로 보낸다."""
import sys
import time
sys.path.insert(0, ".")
from sheetparser import upload as UP
keep = sys.argv[sys.argv.index("--keep-prefix") + 1] if "--keep-prefix" in sys.argv else None
r = UP.call("list")
n = 0
latest = {}
for f in r["files"]:   # 같은 이름이 여럿이면(재시도로 생긴 중복) 가장 최근 것만 남긴다
    latest[f["name"]] = f["id"]
for f in r["files"]:
    if keep and f["name"].startswith(keep) and latest[f["name"]] != f["id"]:
        print("dup", f["name"]); UP.call("delete", id=f["id"]); n_dup = 1; continue
    if keep and f["name"].startswith(keep):
        print("KEEP", f["name"], f["url"]); continue
    if "--dry" in sys.argv:
        print("would delete", f["name"]); continue
    for k in range(4):   # 가끔 404/일시 오류가 나므로 재시도
        try:
            UP.call("delete", id=f["id"]); n += 1; break
        except Exception as e:
            print("retry", f["name"], repr(e)[:60]); time.sleep(3)
print("deleted", n, "of", r["count"])
print("remaining", UP.call("list")["count"] if "--dry" not in sys.argv else "-")
