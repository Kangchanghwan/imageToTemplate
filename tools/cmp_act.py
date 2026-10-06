import fitz,json,re,sys
d=fitz.open("data/pdfs/activity_09.pdf")[0]
print(sorted(set(re.sub(r"[가-힣0-9 ]","",d.get_text()))))
for l in d.get_text().split("\n"):
    if "교시" in l or "지원" in l: print("GT",l)
s=json.load(open(sys.argv[1]))
for c in s["cells"]:
    if c["cs"]>=4 or c["c"]>=8: print("PH",c["r"],c["c"],c["rs"],repr(c["text"]))
