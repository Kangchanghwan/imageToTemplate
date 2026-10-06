// ocr.py 의 CV 부분: _ink_tight, 칸/블록/줄 크롭 (Python 슬라이스 의미 그대로)
import { getCv, tracker, copyMat } from './cv.js';
import { percentileU8, histU8 } from './npy.js';

const toInt = Math.trunc;

// 파이썬 img[y0:y1, x0:x1] (음수/역전은 빈 슬라이스, 범위는 이미 max/min 으로 맞춘 값) -> 복사 Mat | null
export function slice(img, y0, y1, x0, x1) {
  const cv = getCv();
  if (y1 <= y0 || x1 <= x0) return null;
  const roi = img.roi(new cv.Rect(x0, y0, x1 - x0, y1 - y0));
  const out = copyMat(roi);
  roi.delete();
  return out;
}

// _ink_tight(crop, pad): 진한 잉크 덩어리를 감싸는 사각형으로 조인다. 반환 새 Mat (입력 Mat 은 호출자가 해제)
export function inkTight(crop, pad = 14) {
  const cv = getCv();
  const T = tracker();
  try {
    const g = T.add(new cv.Mat());
    cv.cvtColor(crop, g, cv.COLOR_BGR2GRAY);
    const H = g.rows, W = g.cols;
    const gd = new Uint8Array(g.data);   // 복사본(wasm 힙 뷰는 이후 할당으로 무효화될 수 있다)
    const bg = percentileU8(histU8(gd), gd.length, 80);
    const m = T.add(new cv.Mat(H, W, cv.CV_8UC1));
    const md = m.data;
    for (let i = 0; i < gd.length; i++) md[i] = (bg - gd[i]) > 70 ? 1 : 0;
    const k2 = T.add(cv.Mat.ones(2, 2, cv.CV_8U));
    const mo = T.add(new cv.Mat());
    cv.morphologyEx(m, mo, cv.MORPH_OPEN, k2, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const lab = T.add(new cv.Mat()), st = T.add(new cv.Mat()), cen = T.add(new cv.Mat());
    const n = cv.connectedComponentsWithStats(mo, lab, st, cen, 8, cv.CV_32S);
    const sd = st.data32S;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity, any = false;
    for (let i = 1; i < n; i++) {
      if (sd[i * 5 + 4] >= 12 && sd[i * 5 + 3] >= 6) {
        any = true;
        x0 = Math.min(x0, sd[i * 5]); y0 = Math.min(y0, sd[i * 5 + 1]);
        x1 = Math.max(x1, sd[i * 5] + sd[i * 5 + 2]); y1 = Math.max(y1, sd[i * 5 + 1] + sd[i * 5 + 3]);
      }
    }
    if (!any) return copyMat(crop);
    return slice(crop, Math.max(y0 - pad, 0), Math.min(y1 + pad, H), Math.max(x0 - pad, 0), Math.min(x1 + pad, W));
  } finally { T.free(); }
}

// paddle_cells 의 칸 크롭: img[max(y0+3,0):min(y1-3,H), max(x0+3,0):min(x1-3,W)] -> _ink_tight
export function cellCrop(flat, rect) {
  const [x0, y0, x1, y1] = rect.map(toInt);
  const c = slice(flat, Math.max(y0 + 3, 0), Math.min(y1 - 3, flat.rows), Math.max(x0 + 3, 0), Math.min(x1 - 3, flat.cols));
  if (!c) return null;
  const t = inkTight(c);
  c.delete();
  return t;
}

// read_line_paddle 의 블록 크롭 (ink_tight 없음)
export function blockCrop(flat, bbox, band) {
  const [x0, y0, x1, y1] = bbox;
  const [ya, yb] = band ?? [toInt(y0) - 12, toInt(y1) + 12];
  return slice(flat, Math.max(toInt(ya), 0), Math.min(toInt(yb), flat.rows), Math.max(toInt(x0) - 20, 0), Math.min(toInt(x1) + 20, flat.cols));
}

// break_pass 줄 크롭
export function lineCrop(flat, rect, bands, k) {
  const [x0, , x1] = rect.map(toInt);
  const lo = k === 0 ? bands[k][0] - 6 : Math.floor((bands[k - 1][1] + bands[k][0]) / 2);
  const hi = Math.floor((bands[k][1] + bands[k + 1][0]) / 2);
  const c = slice(flat, Math.max(lo, 0), Math.min(hi + 1, flat.rows), Math.max(x0 + 3, 0), Math.min(x1 - 3, flat.cols));
  if (!c) return null;
  const t = inkTight(c);
  c.delete();
  return t;
}
