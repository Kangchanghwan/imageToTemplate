import sys, json
sys.path.insert(0, ".")
from sheetparser import photopage as PH, style as ST
orig = PH.find_blocks
def fb(img, fg, tb):
    out = orig(img, fg, tb)
    for b in out:
        x0, y0, x1, y1 = b["bbox"]
        print("   BLK bbox_h_mm %.2f w_mm %.1f ink_h_mm %.2f nc %d  size(core) %.1f size(bbox_h) %.1f ink2 %.1f" % ((y1-y0)/PH.PPM, (x1-x0)/PH.PPM, b["ink_h"]/PH.PPM, b["nc"], ST.size_from_ink(b["ink_h"], "가"), ST.size_from_ink(y1-y0, "가"), ST.size_from_ink(b["ink_h2"], "가")))
    return out
PH.find_blocks = fb
for f in sys.argv[1:]:
    print(f); PH.run_page(f)
