import json, re, sys
sys.path.insert(0, ".")
from sheetparser import upload as UP
for u in sys.argv[1:]:
    i = re.search(r"/d/([^/]+)", u).group(1)
    for k in range(4):
        try: print("del", UP.call("delete", id=i).get("ok")); break
        except Exception as e: print("retry", repr(e)[:50])
