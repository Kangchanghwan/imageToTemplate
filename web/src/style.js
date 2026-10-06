// sheetparser/style.py 이식 (1단계 범위): style_name, analyze (empty/med/uni/bgr/정렬/글줄 띠/size_pt/stroke 굵기).
// hangul_thickness(hth) 는 2단계(굵기 판정 단계)에서 이식한다.
import { getCv, tracker } from './cv.js';
import { pyRound, median, medianU8, percentileU8, histU8, f32 } from './npy.js';

export const PPM = 10;

export function styleName(info) {
  if (info === null) return 'NONE';
  const [t, dbl] = info;
  if (dbl) return 'DOUBLE';
  if (t < 0.35) return 'SOLID';
  if (t < 0.7) return 'SOLID_MEDIUM';
  return 'SOLID_THICK';
}

// 1차원 불리언 배열 -> 군집 [(start,end)] (간격 > gap 이면 분리)
export function runs(mask1d, gap) {
  const out = [];
  let s = -1, p = -1;
  for (let i = 0; i < mask1d.length; i++) {
    if (!mask1d[i]) continue;
    if (s < 0) { s = i; p = i; continue; }
    if (i - p > gap) { out.push([s, p]); s = i; }
    p = i;
  }
  if (s >= 0) out.push([s, p]);
  return out;
}

export function lineBands(rows, y0, gap = 4) {
  const rr = runs(rows, gap - 1);
  if (!rr.length) return [];
  const mh = Math.max(...rr.map(([a, b]) => b - a + 1));
  let out = [];
  for (const [a, b] of rr) {
    if (out.length && (b - a + 1) < 0.45 * mh) out[out.length - 1] = [out[out.length - 1][0], b];
    else if ((b - a + 1) < 0.45 * mh && !out.length) out.push([a, b]);
    else out.push([a, b]);
  }
  if (out.length > 1 && (out[0][1] - out[0][0] + 1) < 0.45 * mh) { out[1] = [out[0][0], out[1][1]]; out = out.slice(1); }
  return out.map(([a, b]) => [a + y0, b + y0]);
}

// analyze(img, gray, rect, inset) — img: BGR Mat, gray: Mat. rect=[x0,y0,x1,y1] float
export function analyze(img, gray, rect, inset = 7) {
  const cv = getCv();
  let [x0, y0, x1, y1] = rect.map((v) => pyRound(v));
  x0 += inset; y0 += inset; x1 -= inset; y1 -= inset;
  const H = gray.rows, W = gray.cols;
  x0 = Math.max(x0, 0); y0 = Math.max(y0, 0); x1 = Math.min(x1, W); y1 = Math.min(y1, H);
  const res = { empty: true, bgr: null };
  if (x1 - x0 < 8 || y1 - y0 < 8) return res;
  const cw = x1 - x0, ch = y1 - y0, n = cw * ch;
  const gd = gray.data, id = img.data;
  const g = new Uint8Array(n);
  for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) g[y * cw + x] = gd[(y0 + y) * W + x0 + x];
  const med = medianU8(g);
  res.med = med;
  let u = 0, nearN = 0;
  for (let i = 0; i < n; i++) {
    const dv = Math.abs(g[i] - med);
    if (dv <= 12 || g[i] < med - 40) u++;
    if (dv <= 20) nearN++;
  }
  res.uni = u / n;
  if (nearN > 10) {
    const ch3 = [[], [], []];
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) {
      if (Math.abs(g[y * cw + x] - med) <= 20) {
        const o = ((y0 + y) * W + x0 + x) * 3;
        ch3[0].push(id[o]); ch3[1].push(id[o + 1]); ch3[2].push(id[o + 2]);
      }
    }
    res.bgr = ch3.map((a) => medianU8(a));
  }
  const T = tracker();
  try {
    const inkMat = T.add(new cv.Mat(ch, cw, cv.CV_8UC1));
    const thr = med - 55;
    const idat = inkMat.data;
    for (let i = 0; i < n; i++) idat[i] = g[i] < thr ? 1 : 0;
    const lab = T.add(new cv.Mat()), st = T.add(new cv.Mat()), cen = T.add(new cv.Mat());
    const nl = cv.connectedComponentsWithStats(inkMat, lab, st, cen, 8, cv.CV_32S);
    const sd = st.data32S, ld = lab.data32S;
    const ok = new Uint8Array(nl);
    for (let i = 1; i < nl; i++) {
      const x = sd[i * 5], y = sd[i * 5 + 1], w = sd[i * 5 + 2], h = sd[i * 5 + 3], a = sd[i * 5 + 4];
      if (x === 0 || y === 0 || x + w >= cw || y + h >= ch || a < 4) continue;
      if ((w > 0.9 * cw && h < 6) || (h > 0.9 * ch && w < 6)) continue;
      ok[i] = 1;
    }
    const keep = new Uint8Array(n);
    let ksum = 0;
    for (let i = 0; i < n; i++) if (ok[ld[i]]) { keep[i] = 1; ksum++; }
    if (ksum < 15) return res;
    let xmin = cw, xmax = -1, ymin = ch, ymax = -1;
    const rows = new Uint8Array(ch);
    for (let y = 0; y < ch; y++) for (let x = 0; x < cw; x++) if (keep[y * cw + x]) {
      if (x < xmin) xmin = x; if (x > xmax) xmax = x; if (y < ymin) ymin = y; if (y > ymax) ymax = y; rows[y] = 1;
    }
    res.empty = false;
    const gl = xmin, gr = cw - 1 - xmax, gt = ymin, gb = ch - 1 - ymax;
    let d = gr - gl;
    res.h = Math.abs(d) < 0.24 * cw ? 'CENTER' : (d > 0 ? 'LEFT' : 'RIGHT');
    d = gb - gt;
    res.v = Math.abs(d) < 0.12 * ch ? 'MIDDLE' : (d > 0 ? 'TOP' : 'BOTTOM');
    const rr = runs(rows, 2);
    res.lbands = lineBands(rows, y0);
    res.lbx = [];
    for (const [ya, yb] of res.lbands) {
      let cmin = -1, cmax = -1;
      for (let x = 0; x < cw; x++) {
        let any = false;
        for (let y = ya - y0; y <= yb - y0; y++) if (keep[y * cw + x]) { any = true; break; }
        if (any) { if (cmin < 0) cmin = x; cmax = x; }
      }
      if (cmin >= 0) res.lbx.push([cmin, cmax]);
    }
    res.gl = gl; res.gr = gr; res.cw = cw;
    res.fill = (xmax - xmin + 1) / cw;
    res.hth = hangulThickness(g, cw, ch);
    const hs = rr.map(([a, b]) => b - a + 1);
    const lh = hs.length ? median(hs) : 0;
    res.nlines = rr.length;
    res.size_pt = lh ? pyRound(lh / PPM * (72 / 25.4) / 0.85 * 2) / 2 : 10;
    // 굵기: 윤곽 길이 기준 평균 획 두께
    const km = T.add(new cv.Mat(ch, cw, cv.CV_8UC1));
    km.data.set(keep);
    const cnts = T.add(new cv.MatVector()), hier = T.add(new cv.Mat());
    cv.findContours(km, cnts, hier, cv.RETR_LIST, cv.CHAIN_APPROX_NONE);
    let per = 0;
    for (let i = 0; i < cnts.size(); i++) { const c = cnts.get(i); per += cv.arcLength(c, true); c.delete(); }
    const stroke = per ? 2.0 * ksum / per : 0;
    res.bold = !!(lh && stroke / lh > 0.135);
    res.stroke_ratio = lh ? stroke / lh : 0;
    res.ink_h = ymax - ymin + 1;
    res.ink_bbox = [xmin + x0, ymin + y0, xmax + x0, ymax + y0];
    return res;
  } finally { T.free(); }
}

// hangul_thickness(g): 한글 음절 크기 덩어리만 4배 확대해 획 두께(원 해상도 px)의 중앙값. 반환 [두께px, 덩어리 수] | null
export function hangulThickness(g, cw, ch) {
  const cv = getCv();
  const T = tracker();
  try {
    const gm = T.add(new cv.Mat(ch, cw, cv.CV_8UC1));
    gm.data.set(g);
    const big = T.add(new cv.Mat());
    cv.resize(gm, big, new cv.Size(0, 0), 4, 4, cv.INTER_CUBIC);
    const bd = new Uint8Array(big.data), bn = big.rows * big.cols;   // 복사본(이후 할당에 안전)
    const hist = histU8(bd);
    const bg = f32(percentileU8(hist, bn, 85)), ink = f32(percentileU8(hist, bn, 1.0));
    if (f32(bg - ink) < 60) return null;
    const thr = f32(f32(bg + ink) / 2);
    const m = T.add(new cv.Mat(big.rows, big.cols, cv.CV_8UC1));
    const md = m.data;
    for (let i = 0; i < bn; i++) md[i] = bd[i] < thr ? 1 : 0;
    const lab = T.add(new cv.Mat()), st = T.add(new cv.Mat()), cen = T.add(new cv.Mat());
    const n = cv.connectedComponentsWithStats(m, lab, st, cen, 8, cv.CV_32S);
    if (n < 2) return null;
    const sd = st.data32S;
    let ih = 0;
    for (let i = 1; i < n; i++) ih = Math.max(ih, sd[i * 5 + 3]);
    const keep = new Uint8Array(n);
    let nk = 0;
    for (let i = 1; i < n; i++) {
      const x = sd[i * 5], y = sd[i * 5 + 1], w = sd[i * 5 + 2], h = sd[i * 5 + 3], a = sd[i * 5 + 4];
      if (h >= 0.7 * ih && w >= 0.75 * h && a > 40 && x > 0 && y > 0 && x + w < big.cols && y + h < big.rows) { keep[i] = 1; nk++; }
    }
    if (nk < 1) return null;
    const ld = new Int32Array(lab.data32S);
    const km = T.add(new cv.Mat(big.rows, big.cols, cv.CV_8UC1));
    const kd = km.data;
    for (let i = 0; i < bn; i++) kd[i] = keep[ld[i]];
    const dt = T.add(new cv.Mat());
    cv.distanceTransform(km, dt, cv.DIST_L2, cv.DIST_MASK_PRECISE);
    const k3 = T.add(cv.Mat.ones(3, 3, cv.CV_8U));
    const mx = T.add(new cv.Mat());
    cv.dilate(dt, mx, k3, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const dd = dt.data32F, xd = mx.data32F;
    const eps = f32(1e-3);
    const vals = [];
    for (let i = 0; i < bn; i++) if (dd[i] >= f32(xd[i] - eps) && dd[i] >= 2.0) vals.push(f32(f32(2 * dd[i]) / 4.0));
    if (vals.length < 10) return null;
    const s = Float32Array.from(vals).sort();
    const nn = s.length;
    const med = nn % 2 ? s[(nn - 1) / 2] : f32(f32(s[nn / 2 - 1] + s[nn / 2]) / 2);
    return [med, nk];
  } finally { T.free(); }
}

export const HANGUL_RATIO = 0.88, LATIN_RATIO = 0.72, LEAD = 1.2;
// 잉크 bbox 높이(px)와 글 내용으로 글자 크기(pt) 추정
export function sizeFromInk(inkHPx, text, ppm = PPM, nlines = null) {
  const t = (text || '').replace(/^\n+|\n+$/g, '');
  const n = Math.max(1, t.split('\n').length, nlines || 1);
  const hangul = /[\uac00-\ud7a3]/.test(text || '');
  const ratio = hangul ? HANGUL_RATIO : LATIN_RATIO;
  const emMm = inkHPx / ppm / (ratio + LEAD * (n - 1));
  return emMm * 72 / 25.4;
}

// unify_sizes(items, rel): 인접 값이 rel 이내면 한 단계(중앙값 0.5pt 반올림). 반환 Map(value -> unified)
export function unifySizes(items, rel = 0.12) {
  const vals = [...new Set(items)].sort((a, b) => a - b);
  const groups = [];
  for (const v of vals) {
    if (groups.length && v <= groups[groups.length - 1][groups[groups.length - 1].length - 1] * (1 + rel)) groups[groups.length - 1].push(v);
    else groups.push([v]);
  }
  const m = new Map();
  for (const g of groups) {
    const c = pyRound(median(g) * 2) / 2;
    for (const v of g) m.set(v, c);
  }
  return m;
}
