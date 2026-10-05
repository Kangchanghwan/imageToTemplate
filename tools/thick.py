import sys, json, cv2, collections
sys.argv=['x']
from sheetparser import preprocess as PP, grid as G
import numpy as np
D=collections.defaultdict(list)
for i in range(6):
    n="s%02d"%i
    g=json.load(open("data/synth/%s.json"%n))
    img,_,_=PP.rectify(cv2.imread("data/synth/%s_photo.jpg"%n))
    gr=G.build_grid(PP.line_mask(img),10)
    for k in "hv":
        for ra,rb in zip(gr[k],g["borders"][k]):
            for a,b in zip(ra,rb):
                if a: D[(b,a[1])].append(a[0])
for k,v in sorted(D.items()): print(k,len(v),np.percentile(v,[10,50,90]).round(2))
