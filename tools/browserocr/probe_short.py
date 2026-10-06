"""한 글자/짧은 칸이 빈 결과가 되는 원인 탐색: 크롭 전처리별 rec 결과 비교. 사용: probe_short.py <크롭폴더>"""
import glob, os, sys
sys.path.insert(0, "."); sys.path.insert(0, "tools/browserocr")
import cv2, numpy as np
import backend as B
def pad(img, l, r, t=6, b=6):
    return cv2.copyMakeBorder(img, t, b, l, r, cv2.BORDER_CONSTANT, value=(255, 255, 255))
def rec(img, h):
    B.PREP = False
    return B.rec_line(img, h)[0]
preps = {
  "raw48": lambda c: rec(c, 48),
  "pad6_48": lambda c: rec(pad(c, 6, 6), 48),
  "pad.5h_48": lambda c: rec(pad(c, c.shape[0] // 2, c.shape[0] // 2), 48),
  "pad1h_48": lambda c: rec(pad(c, c.shape[0], c.shape[0]), 48),
  "min3_48": lambda c: rec(B.minwide(pad(c, 6, 6)), 48),
}
for f in sorted(glob.glob(sys.argv[1] + "/*.png")):
    c = cv2.imread(f)
    if c.shape[1] > 3 * c.shape[0]:
        continue   # 짧은 칸만
    print(os.path.basename(f), c.shape[:2], {k: v(c) for k, v in preps.items()})
