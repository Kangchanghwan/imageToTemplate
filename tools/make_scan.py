"""PDF 를 300dpi 이미지로 렌더링해 이미지만 든 PDF(스캔본)를 만든다. 사용: make_scan.py in.pdf out.pdf"""
import sys
import fitz
src, dst = sys.argv[1:3]
pg = fitz.open(src)[0]
pix = pg.get_pixmap(matrix=fitz.Matrix(300 / 72, 300 / 72), colorspace=fitz.csRGB, alpha=False)
d = fitz.open()
p = d.new_page(width=pg.rect.width, height=pg.rect.height)
p.insert_image(p.rect, stream=pix.tobytes("png"))
d.save(dst)
