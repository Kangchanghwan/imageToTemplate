import json, sys
s = json.load(open(sys.argv[1]))
for c in s["cells"]:
    if c.get("role", "table") == "table" and (len(sys.argv) < 3 or c["r"] <= int(sys.argv[2])):
        print(c["r"], c["c"], c["rs"], c["cs"], c["h"], c["v"], "B" if c.get("bold") else "-", c.get("size_pt"), c.get("bg"), repr(c["text"][:28]))
    elif c.get("role") == "text":
        print("BLK", c["h"], "B" if c.get("bold") else "-", c.get("size_pt"), repr(c["text"][:30]))
