"""8라운드 입력 만들기: 각 PDF -> scan_<n>.pdf (이미지 PDF), <n>_300dpi.png"""
import fitz, sys, os
for n in ("attendance_09", "activity_09", "meal_09"):
    src = "data/pdfs/%s.pdf" % n
    pg = fitz.open(src)[0]
    pix = pg.get_pixmap(matrix=fitz.Matrix(300/72, 300/72), colorspace=fitz.csRGB, alpha=False)
    if not os.path.exists("data/pdfs/%s_300dpi.png" % n):
        pix.save("data/pdfs/%s_300dpi.png" % n)
    if not os.path.exists("data/pdfs/scan_%s.pdf" % n):
        d = fitz.open(); p = d.new_page(width=pg.rect.width, height=pg.rect.height)
        p.insert_image(p.rect, stream=pix.tobytes("png")); d.save("data/pdfs/scan_%s.pdf" % n)
    print(n, pg.rect)
