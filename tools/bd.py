import json,collections,sys
d=sys.argv[1]; mode=sys.argv[2]
cnt=collections.Counter()
for i in range(12):
    n="s%02d"%i
    p=json.load(open("runs/b1/%s_%s.json"%(n,mode)));g=json.load(open("data/synth/%s.json"%n))
    if len(p["rows"])!=len(g["rows"]) or len(p["columns"])!=len(g["columns"]): continue
    for k in "hv":
        for ra,rb in zip(p["borders"][k],g["borders"][k]):
            for a,b in zip(ra,rb):
                if a!=b: cnt[(b,a)]+=1
print(cnt.most_common())
