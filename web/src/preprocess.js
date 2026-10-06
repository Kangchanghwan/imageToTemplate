// sheetparser/preprocess.py 이식: 용지 검출, 원근 보정, 선 마스크, table_rectify, 평탄화.
// 모든 이미지는 cv.Mat (BGR CV_8UC3). 반환하는 Mat 의 delete() 는 호출자 책임.
import { getCv, tracker, copyMat } from './cv.js';
import { pyRound, pyRoundN, arange, lstsq, percentileSorted } from './npy.js';

export const PPM = 10;
const f32 = Math.fround;

// np.arange(0.01, 0.1, 0.005) (18개), np.arange(0.01, 0.12, 0.005) (22개)
const EPS_PAPER = arange(0.01, 0.1, 0.005);
const EPS_TABLE = arange(0.01, 0.12, 0.005);

// _order: pts 4x2 -> float32 [좌상, 우상, 우하, 좌하]. 입력 [[x,y]*4]
export function order(pts) {
  const p = pts.map(([x, y]) => [f32(x), f32(y)]);
  const s = p.map(([x, y]) => f32(x + y));
  const d = p.map(([x, y]) => f32(y - x));   // np.diff(axis=1)
  const argmin = (a) => a.reduce((bi, v, i) => (v < a[bi] ? i : bi), 0);
  const argmax = (a) => a.reduce((bi, v, i) => (v > a[bi] ? i : bi), 0);
  return [p[argmin(s)], p[argmin(d)], p[argmax(s)], p[argmax(d)]];
}

function f32norm(a, b) {
  const dx = f32(b[0] - a[0]), dy = f32(b[1] - a[1]);
  return f32(Math.sqrt(f32(f32(dx * dx) + f32(dy * dy))));
}

function approxQuad(hull, peri, epsList) {
  const cv = getCv();
  for (const eps of epsList) {
    const ap = new cv.Mat();
    cv.approxPolyDP(hull, ap, eps * peri, true);
    if (ap.rows === 4) {
      const d = ap.data32S;
      const q = [[d[0], d[1]], [d[2], d[3]], [d[4], d[5]], [d[6], d[7]]];
      ap.delete();
      return q;
    }
    ap.delete();
  }
  return null;
}

function boxOfHull(hull) {
  const cv = getCv();
  const rr = cv.minAreaRect(hull);
  return cv.RotatedRect.points(rr).map((p) => [p.x, p.y]);
}

// find_paper(img) -> {quad(float32 4x2, 원본 좌표), touch} | null
export function findPaper(img) {
  const cv = getCv();
  const T = tracker();
  try {
    const h = img.rows, w = img.cols;
    const sc = 1000.0 / Math.max(h, w);
    const small = T.add(new cv.Mat());
    cv.resize(img, small, new cv.Size(0, 0), sc, sc, cv.INTER_AREA);
    const gray = T.add(new cv.Mat());
    cv.cvtColor(small, gray, cv.COLOR_BGR2GRAY);
    const g = T.add(new cv.Mat());
    cv.GaussianBlur(gray, g, new cv.Size(9, 9), 0, 0, cv.BORDER_DEFAULT);
    const th = T.add(new cv.Mat());
    cv.threshold(g, th, 0, 255, cv.THRESH_BINARY + cv.THRESH_OTSU);
    const k15 = T.add(cv.Mat.ones(15, 15, cv.CV_8U));
    const th2 = T.add(new cv.Mat());
    cv.morphologyEx(th, th2, cv.MORPH_CLOSE, k15, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const cnts = T.add(new cv.MatVector());
    const hier = T.add(new cv.Mat());
    cv.findContours(th2, cnts, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
    if (cnts.size() === 0) return null;
    let best = null, bestA = -1;
    for (let i = 0; i < cnts.size(); i++) {
      const c = cnts.get(i);
      const a = cv.contourArea(c);
      if (a > bestA) { if (best) best.delete(); best = c; bestA = a; } else c.delete();
    }
    T.add(best);
    if (bestA < 0.2 * small.rows * small.cols) return null;
    const hull = T.add(new cv.Mat());
    cv.convexHull(best, hull, false, true);
    const peri = cv.arcLength(hull, true);
    let quad = approxQuad(hull, peri, EPS_PAPER);
    if (quad === null) quad = boxOfHull(hull);
    const o = order(quad);
    const fsc = f32(sc);
    quad = o.map(([x, y]) => [f32(x / fsc), f32(y / fsc)]);
    const m = 0.01 * Math.max(h, w);
    const fm = f32(m), fwm = f32(w - m), fhm = f32(h - m);
    const touch = (quad.some((q) => q[0] < fm) ? 1 : 0) + (quad.some((q) => q[0] > fwm) ? 1 : 0) +
      (quad.some((q) => q[1] < fm) ? 1 : 0) + (quad.some((q) => q[1] > fhm) ? 1 : 0);
    return { quad, touch };
  } finally { T.free(); }
}

function warp(img, quad, dstPts, W, H) {
  const cv = getCv();
  const T = tracker();
  try {
    const s = T.add(cv.matFromArray(4, 1, cv.CV_32FC2, quad.flat()));
    const d = T.add(cv.matFromArray(4, 1, cv.CV_32FC2, dstPts.flat()));
    const M = T.add(cv.getPerspectiveTransform(s, d));
    const out = new cv.Mat();
    cv.warpPerspective(img, out, M, new cv.Size(W, H), cv.INTER_CUBIC, cv.BORDER_CONSTANT, new cv.Scalar(255, 255, 255, 255));
    return out;
  } finally { T.free(); }
}

// rectify(img, forceFullframe) -> {img: Mat, pageMm, flags}
export function rectify(img, forceFullframe = false) {
  const cv = getCv();
  const flags = [];
  let res = forceFullframe ? null : findPaper(img);
  let quad = null;
  if (res !== null) {
    quad = res.quad;
    const wq = f32(f32norm(quad[0], quad[1]) + f32norm(quad[3], quad[2])) / 2;
    const hq = f32(f32norm(quad[0], quad[3]) + f32norm(quad[1], quad[2])) / 2;
    const ratio = f32(Math.max(wq, hq) / Math.max(1.0, Math.min(wq, hq)));
    if (res.touch >= 3) { flags.push({ reason: 'paper_clipped' }); res = null; }
    else if (Math.abs(ratio - 1.414) > 0.12) { flags.push({ reason: 'paper_not_a4_ratio:' + ratio.toFixed(2) }); res = null; }
  }
  if (res === null) {
    flags.push({ reason: 'no_paper_assume_width_210mm' });
    const s = 2100.0 / img.cols;
    const out = new cv.Mat();
    cv.resize(img, out, new cv.Size(0, 0), s, s, s < 1 ? cv.INTER_AREA : cv.INTER_CUBIC);
    return { img: out, pageMm: [210, pyRoundN(out.rows / PPM, 1)], flags };
  }
  const wq = f32(f32norm(quad[0], quad[1]) + f32norm(quad[3], quad[2])) / 2;
  const hq = f32(f32norm(quad[0], quad[3]) + f32norm(quad[1], quad[2])) / 2;
  let W, H, pg;
  if (wq > hq) { W = 2970; H = 2100; pg = [297, 210]; flags.push({ reason: 'landscape_page' }); }
  else { W = 2100; H = 2970; pg = [210, 297]; }
  const dst = [[0, 0], [W - 1, 0], [W - 1, H - 1], [0, H - 1]];
  const out = warp(img, quad, dst, W, H);
  return { img: out, pageMm: pg, flags };
}

// line_mask(img, ppm) -> Mat CV_8UC1 (0/255)
export function lineMask(img, ppm = PPM) {
  const cv = getCv();
  const T = tracker();
  try {
    const g = T.add(new cv.Mat());
    cv.cvtColor(img, g, cv.COLOR_BGR2GRAY);
    const k5 = T.add(cv.Mat.ones(5, 5, cv.CV_8U));
    const dil = T.add(new cv.Mat());
    cv.dilate(g, dil, k5, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const bg = T.add(new cv.Mat());
    cv.medianBlur(dil, bg, 4 * ppm + 1);
    const diff = T.add(new cv.Mat());
    cv.subtract(bg, g, diff);
    const mask = new cv.Mat();
    cv.threshold(diff, mask, 40, 255, cv.THRESH_BINARY);
    const mg = Math.trunc(1.5 * ppm);
    const H = mask.rows, W = mask.cols, d = mask.data;
    d.fill(0, 0, mg * W);
    d.fill(0, (H - mg) * W, H * W);
    for (let y = 0; y < H; y++) { d.fill(0, y * W, y * W + mg); d.fill(0, y * W + W - mg, (y + 1) * W); }
    return mask;
  } finally { T.free(); }
}

// table_rectify(img, keepFrame) -> {img, origin_mm|null, ok}
export function tableRectify(img, keepFrame = false) {
  const cv = getCv();
  const T = tracker();
  try {
    const m = T.add(lineMask(img));
    const k5 = T.add(cv.Mat.ones(5, 5, cv.CV_8U));
    const comb = T.add(new cv.Mat());
    cv.dilate(m, comb, k5, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const lab = T.add(new cv.Mat()), st = T.add(new cv.Mat()), cen = T.add(new cv.Mat());
    const n = cv.connectedComponentsWithStats(comb, lab, st, cen, 8, cv.CV_32S);
    if (n < 2) return { img: copyMat(img), origin: null, ok: false };
    const sd = st.data32S;
    let main = 1;
    for (let i = 2; i < n; i++) if (sd[i * 5 + 4] > sd[main * 5 + 4]) main = i;
    const ld = lab.data32S;
    const cnt = sd[main * 5 + 4];
    const pts = new Int32Array(cnt * 2);
    let k = 0;
    const W0 = img.cols, H0 = img.rows;
    for (let y = 0; y < H0; y++) for (let x = 0; x < W0; x++) if (ld[y * W0 + x] === main) { pts[k++] = x; pts[k++] = y; }
    const pm = T.add(cv.matFromArray(cnt, 1, cv.CV_32SC2, Array.from(pts)));
    const hull = T.add(new cv.Mat());
    cv.convexHull(pm, hull, false, true);
    const peri = cv.arcLength(hull, true);
    let quad = approxQuad(hull, peri, EPS_TABLE);
    if (quad === null) quad = boxOfHull(hull);
    quad = order(quad);
    const W = Math.trunc(f32(f32norm(quad[0], quad[1]) + f32norm(quad[3], quad[2])) / 2);
    const H = Math.trunc(f32(f32norm(quad[0], quad[3]) + f32norm(quad[1], quad[2])) / 2);
    if (keepFrame) {
      const x0 = quad[0][0], y0 = quad[0][1];
      const dst = [[x0, y0], [x0 + W, y0], [x0 + W, y0 + H], [x0, y0 + H]];
      const out = warp(img, quad, dst, img.cols, img.rows);
      return { img: out, origin: [0.0, 0.0], ok: true };
    }
    const pad = 60;
    const dst = [[pad, pad], [pad + W, pad], [pad + W, pad + H], [pad, pad + H]];
    const out = warp(img, quad, dst, W + 2 * pad, H + 2 * pad);
    return { img: out, origin: [pyRoundN(quad[0][0] / PPM, 1), pyRoundN(quad[0][1] / PPM, 1)], ok: true };
  } finally { T.free(); }
}

// flatten(img, regionPx, ppm, bs) -> Mat BGR uint8
export function flatten(img, regionPx, ppm = PPM, bs = 8) {
  const cv = getCv();
  const T = tracker();
  try {
    const g = T.add(new cv.Mat());
    cv.cvtColor(img, g, cv.COLOR_BGR2GRAY);
    const H = g.rows, W = g.cols;
    const sm = T.add(new cv.Mat());
    cv.resize(g, sm, new cv.Size(Math.floor(W / ppm), Math.floor(H / ppm)), 0, 0, cv.INTER_AREA);
    const h = sm.rows, w = sm.cols;
    const ny = Math.floor(h / bs), nx = Math.floor(w / bs);
    const sd = sm.data;
    const p = new Float32Array(ny * nx);
    const blk = new Float64Array(bs * bs);
    for (let by = 0; by < ny; by++) {
      for (let bx = 0; bx < nx; bx++) {
        let k = 0;
        for (let yy = 0; yy < bs; yy++) for (let xx = 0; xx < bs; xx++) blk[k++] = sd[(by * bs + yy) * w + bx * bs + xx];
        const s = Float64Array.from(blk).sort();
        p[by * nx + bx] = percentileSorted(s, 90);   // float32 저장 = numpy 결과 dtype
      }
    }
    const [rx0, ry0, rx1, ry1] = regionPx.map((v) => v / ppm);
    const idx = [];
    for (let by = 0; by < ny; by++) {
      const Y = (by + 0.5) * bs;
      for (let bx = 0; bx < nx; bx++) {
        const X = (bx + 0.5) * bs;
        if (X > rx0 - 10 && X < rx1 + 10 && Y > ry0 - 10 && Y < ry1 + 10) idx.push([X, Y, p[by * nx + bx]]);
      }
    }
    let sel = idx;
    if (sel.length < 20) {
      sel = [];
      for (let by = 0; by < ny; by++) for (let bx = 0; bx < nx; bx++) sel.push([(bx + 0.5) * bs, (by + 0.5) * bs, p[by * nx + bx]]);
    }
    const pw = (x, n) => (n === 0 ? 1 : n === 1 ? x : n === 2 ? x * x : Math.pow(x, n));
    const pairs = [];
    for (let i = 0; i < 4; i++) for (let j = 0; j < 4 - i; j++) pairs.push([i, j]);
    const termsRow = (x, y) => { const u = x / w, v = y / h; return pairs.map(([i, j]) => pw(u, i) * pw(v, j)); };
    const A = sel.map(([X, Y]) => termsRow(X, Y));
    const vals = sel.map((s) => s[2]);
    let keep = vals.map(() => true);
    let co = null;
    for (let it = 0; it < 6; it++) {
      const ki = keep.map((k, i) => (k ? i : -1)).filter((i) => i >= 0);
      co = lstsq(ki.map((i) => A[i]), ki.map((i) => vals[i]));
      const nk = A.map((row, i) => {
        let s = 0;
        for (let k = 0; k < 10; k++) s += row[k] * co[k];
        return vals[i] - s > -8;
      });
      keep = nk;
      if (keep.filter(Boolean).length < 15) break;
    }
    // 곡면: surf[y][x] = sum_k co[k] * pu[i][x] * pv[j][y]
    const lo_x = Math.max(rx0, 0), hi_x = Math.min(rx1, w);
    const lo_y = Math.max(ry0, 0), hi_y = Math.min(ry1, h);
    const clip = (v, a, b) => Math.min(Math.max(v, a), b);
    const U = [], V = [];
    for (let i = 0; i < 4; i++) { U.push(new Float64Array(w)); V.push(new Float64Array(h)); }
    for (let x = 0; x < w; x++) { const u = clip(x + 0.5, lo_x, hi_x) / w; for (let i = 0; i < 4; i++) U[i][x] = pw(u, i); }
    for (let y = 0; y < h; y++) { const v = clip(y + 0.5, lo_y, hi_y) / h; for (let j = 0; j < 4; j++) V[j][y] = pw(v, j); }
    const surf = new Float32Array(h * w);
    for (let y = 0; y < h; y++) {
      for (let x = 0; x < w; x++) {
        let s = 0;
        for (let k = 0; k < 10; k++) s += (U[pairs[k][0]][x] * V[pairs[k][1]][y]) * co[k];
        surf[y * w + x] = s;
      }
    }
    const sm32 = T.add(cv.matFromArray(h, w, cv.CV_32FC1, surf));
    const big = T.add(new cv.Mat());
    cv.resize(sm32, big, new cv.Size(W, H), 0, 0, cv.INTER_LINEAR);
    const out = new cv.Mat(H, W, cv.CV_8UC3);
    const bd = big.data32F, od = out.data, id = img.data;   // 할당 뒤에 뷰를 가져온다(힙 성장 시 이전 뷰는 무효)
    const lo = f32(0.8), hi = f32(2.2);
    for (let i = 0; i < H * W; i++) {
      let s = bd[i]; if (!(s >= 1)) s = 1;   // np.maximum(surf, 1)
      let gain = f32(255.0 / s);
      gain = gain < lo ? lo : gain > hi ? hi : gain;
      for (let c = 0; c < 3; c++) {
        let v = f32(id[i * 3 + c] * gain);
        v = v < 0 ? 0 : v > 255 ? 255 : v;
        od[i * 3 + c] = v;   // uint8 캐스트 = 절삭
      }
    }
    return out;
  } finally { T.free(); }
}
