// pdf_scan 용 300dpi 렌더: PyMuPDF get_pixmap(Matrix(dpi/72)) 에 해당. 반환 BGR cv.Mat (흰 배경, 알파 없음).
//  1) renderWithCanvas: 브라우저(또는 canvas 가 있는 Node)에서 pdf.js 의 page.render 를 쓴다. createCanvas(w,h) 주입.
//  2) renderImageOnly: 페이지가 이미지만으로 이루어진 스캔(글자/벡터 없음)이면 이미지를 OpenCV warpAffine 으로 직접 배치한다(Node 에서 canvas 없이).
import { getCv } from '../cv.js';
import { tp } from './extract.js';

// MuPDF pixmap 크기: 페이지 rect 에 scale 을 곱해 바깥으로 올림
export function pixmapSize(rect, dpi) {
  const s = dpi / 72;
  return [Math.ceil(rect[2] * s - 1e-6), Math.ceil(rect[3] * s - 1e-6)];
}

export async function renderWithCanvas(page, dpi, createCanvas) {
  const cv = getCv();
  const E = null;
  const s = dpi / 72;
  const viewport = page.getViewport({ scale: s });
  const w = Math.ceil(viewport.width - 1e-6), h = Math.ceil(viewport.height - 1e-6);
  const canvas = createCanvas(w, h);
  const ctx = canvas.getContext('2d');
  ctx.fillStyle = '#ffffff';
  ctx.fillRect(0, 0, w, h);
  await page.render({ canvasContext: ctx, viewport, canvas }).promise;
  const id = ctx.getImageData(0, 0, w, h).data;
  const m = new cv.Mat(h, w, cv.CV_8UC3);
  const d = m.data;
  for (let i = 0, n = w * h; i < n; i++) { d[i * 3] = id[i * 4 + 2]; d[i * 3 + 1] = id[i * 4 + 1]; d[i * 3 + 2] = id[i * 4]; }
  return m;
}

export function isImageOnly(E) {
  return E.images.length > 0 && E.drawings.length === 0 && E.glyphs.length === 0 && E.images.every((im) => im.img && im.img.data);
}

export function renderImageOnly(E, dpi) {
  const cv = getCv();
  const s = dpi / 72;
  const [W, H] = pixmapSize(E.rect, dpi);
  const out = new cv.Mat(H, W, cv.CV_8UC3, new cv.Scalar(255, 255, 255, 0));
  for (const im of E.images) {
    const i = im.img, c = im.ctm;
    const rgb = i.kind === 3 ? 4 : 3;
    // 원본 이미지 -> BGR(A 는 알파로 합성)
    const src = new cv.Mat(i.height, i.width, rgb === 4 ? cv.CV_8UC4 : cv.CV_8UC3);
    src.data.set(i.data.subarray ? i.data.subarray(0, i.height * i.width * rgb) : i.data);
    const bgr = new cv.Mat();
    cv.cvtColor(src, bgr, rgb === 4 ? cv.COLOR_RGBA2BGR : cv.COLOR_RGB2BGR);
    src.delete();
    // 이미지 연속좌표 (X=i, Y=j) -> 장치(px). u=X/w, v=1-Y/h, [x,y]=ctm*[u,v]
    const a = c[0] * s / i.width, b = c[1] * s / i.width, cc = -c[2] * s / i.height, d = -c[3] * s / i.height;
    const e = (c[2] + c[4]) * s, f = (c[3] + c[5]) * s;
    // OpenCV 는 픽셀 중심을 정수로 쓰므로 반 픽셀 보정
    const e2 = e + (a + cc) * 0.5 - 0.5, f2 = f + (b + d) * 0.5 - 0.5;
    const M = cv.matFromArray(2, 3, cv.CV_64FC1, [a, cc, e2, b, d, f2]);
    const warped = new cv.Mat();
    cv.warpAffine(bgr, warped, M, new cv.Size(W, H), cv.INTER_LINEAR, cv.BORDER_CONSTANT, new cv.Scalar(255, 255, 255, 0));
    warped.copyTo(out);
    bgr.delete(); M.delete(); warped.delete();
  }
  return out;
}
