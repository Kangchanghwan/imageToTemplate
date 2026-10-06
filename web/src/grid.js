// sheetparser/grid.py 이식: 선 마스크 -> 전역 격자 -> 경계 유무/두께 -> 병합 -> trim_outer
import { getCv, tracker } from './cv.js';
import { pyRound, npSum, median } from './npy.js';

// line_masks(mask, ppm) -> {hb, vb} (Mat, 호출자가 delete)
export function lineMasks(mask, ppm) {
  const cv = getCv();
  const L = Math.max(5, Math.trunc(3.0 * ppm));
  const hk = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(L, 1));
  const vk = cv.getStructuringElement(cv.MORPH_RECT, new cv.Size(1, L));
  const hb = new cv.Mat(), vb = new cv.Mat();
  const bv = cv.morphologyDefaultBorderValue();
  cv.morphologyEx(mask, hb, cv.MORPH_OPEN, hk, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, bv);
  cv.morphologyEx(mask, vb, cv.MORPH_OPEN, vk, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, bv);
  hk.delete(); vk.delete();
  return { hb, vb };
}

// proj >= thr 인 인덱스를 gap 이하 간격이면 한 군집으로: [[start,end]]
export function groups(proj, thr, gap) {
  const out = [];
  let s = -1, p = -1;
  for (let i = 0; i < proj.length; i++) {
    if (!(proj[i] >= thr)) continue;
    if (s < 0) { s = i; p = i; continue; }
    if (i - p > gap) { out.push([s, p]); s = i; }
    p = i;
  }
  if (s >= 0) out.push([s, p]);
  return out;
}

// data: Uint8Array(nrows*ncols) 0/255, lines: [[lo,hi]] (axis0), edges: axis1 경계 중심
// 반환 res[k][j] = null | [두께mm, 이중선]
function segStats(data, nrows, ncols, lines, edges, ppm) {
  const res = [];
  for (const [lo, hi] of lines) {
    const a = Math.max(0, lo - 2), b = Math.min(nrows, hi + 3);
    const nb = b - a;
    const row = [];
    for (let j = 0; j < edges.length - 1; j++) {
      const x0 = edges[j], x1 = edges[j + 1];
      const m = 0.1 * (x1 - x0);
      let xa = pyRound(x0 + m), xb = pyRound(x1 - m);
      if (xb <= xa + 1) { xa = Math.trunc(x0); xb = Math.trunc(x1); }
      xa = Math.max(xa, 0);
      const xe = Math.min(xb, ncols);
      const width = xe - xa;   // 파이썬 슬라이스: 음수 길이는 0
      if (width <= 0) { row.push(null); continue; }
      let hits = 0;
      const hitCol = new Uint8Array(width);
      for (let x = xa; x < xe; x++) {
        for (let r = a; r < b; r++) if (data[r * ncols + x] > 0) { hitCol[x - xa] = 1; hits++; break; }
      }
      if (hits / width < 0.5) { row.push(null); continue; }
      const prof = new Float64Array(nb);
      for (let r = 0; r < nb; r++) {
        let cnt = 0;
        for (let x = xa; x < xe; x++) if (hitCol[x - xa] && data[(a + r) * ncols + x] > 0) cnt++;
        prof[r] = cnt / hits;
      }
      const thick = npSum(prof) / ppm;
      let pk = -Infinity;
      for (let r = 0; r < nb; r++) if (prof[r] > pk) pk = prof[r];
      const on = Array.from(prof, (v) => v > 0.5 * pk);
      let runs = on[0] ? 1 : 0;
      for (let r = 1; r < nb; r++) if (on[r] && !on[r - 1]) runs++;
      row.push([thick, runs >= 2]);
    }
    res.push(row);
  }
  return res;
}

export function buildGrid(mask, ppm, minLenMm = 2.5) {
  const cv = getCv();
  const T = tracker();
  try {
    const H = mask.rows, W = mask.cols;
    const { hb, vb } = lineMasks(mask, ppm);
    T.add(hb); T.add(vb);
    const k = Math.max(3, Math.trunc(0.8 * ppm));
    const orm = T.add(new cv.Mat());
    cv.bitwise_or(hb, vb, orm);
    const kk = T.add(cv.Mat.ones(k, k, cv.CV_8U));
    const comb = T.add(new cv.Mat());
    cv.dilate(orm, comb, kk, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const lab = T.add(new cv.Mat()), st = T.add(new cv.Mat()), cen = T.add(new cv.Mat());
    const n = cv.connectedComponentsWithStats(comb, lab, st, cen, 8, cv.CV_32S);
    if (n < 2) throw new Error('no_lines');
    const sd = st.data32S;
    let main = 1;
    for (let i = 2; i < n; i++) if (sd[i * 5 + 4] > sd[main * 5 + 4]) main = i;
    const [x, y, w, h] = [0, 1, 2, 3].map((i) => sd[main * 5 + i]);
    const extras = [];
    for (let i = 1; i < n; i++) if (i !== main && sd[i * 5 + 2] * sd[i * 5 + 3] > 0.03 * H * W) extras.push([0, 1, 2, 3].map((j) => sd[i * 5 + j]));
    const ld = lab.data32S, hd = hb.data, vd = vb.data;
    const hbc = new Uint8Array(h * w), vbcT = new Uint8Array(w * h), vbc = new Uint8Array(h * w);
    for (let yy = 0; yy < h; yy++) {
      for (let xx = 0; xx < w; xx++) {
        if (ld[(y + yy) * W + x + xx] === main) {
          hbc[yy * w + xx] = hd[(y + yy) * W + x + xx];
          const v = vd[(y + yy) * W + x + xx];
          vbc[yy * w + xx] = v; vbcT[xx * h + yy] = v;
        }
      }
    }
    const thr = minLenMm * ppm;
    const gap = Math.max(2, Math.trunc(1.0 * ppm));
    const rowProj = new Float64Array(h), colProj = new Float64Array(w);
    for (let yy = 0; yy < h; yy++) { let s = 0; for (let xx = 0; xx < w; xx++) s += hbc[yy * w + xx]; rowProj[yy] = s / 255.0; }
    for (let xx = 0; xx < w; xx++) { let s = 0; for (let yy = 0; yy < h; yy++) s += vbc[yy * w + xx]; colProj[xx] = s / 255.0; }
    let ylines = groups(rowProj, thr, gap);
    let xlines = groups(colProj, thr, gap);
    if (ylines.length < 2 || xlines.length < 2) throw new Error('no_grid');

    let Hs, Vs, ycen, xcen;
    for (let it = 0; it < 4; it++) {
      ycen = ylines.map(([a, b]) => (a + b) / 2);
      xcen = xlines.map(([a, b]) => (a + b) / 2);
      Hs = segStats(hbc, h, w, ylines, xcen, ppm);
      Vs = segStats(vbcT, w, h, xlines, ycen, ppm);
      const ykeep = [], xkeep = [];
      Hs.forEach((row, i) => { if (row.some((v) => v !== null)) ykeep.push(i); });
      Vs.forEach((row, j) => { if (row.some((v) => v !== null)) xkeep.push(j); });
      if (ykeep.length === ylines.length && xkeep.length === xlines.length) break;
      ylines = ykeep.map((i) => ylines[i]);
      xlines = xkeep.map((j) => xlines[j]);
      if (ylines.length < 2 || xlines.length < 2) throw new Error('no_grid');
    }
    const R = ylines.length - 1, C = xlines.length - 1;
    const hs = Hs;
    const vs = [];
    for (let r = 0; r < R; r++) { const row = []; for (let j = 0; j <= C; j++) row.push(Vs[j][r]); vs.push(row); }

    const par = Array.from({ length: R * C }, (_, i) => i);
    const f = (a) => { while (par[a] !== a) { par[a] = par[par[a]]; a = par[a]; } return a; };
    const u = (a, b) => { a = f(a); b = f(b); if (a !== b) par[b] = a; };
    for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) {
      if (c + 1 < C && vs[r][c + 1] === null) u(r * C + c, r * C + c + 1);
      if (r + 1 < R && hs[r + 1][c] === null) u(r * C + c, (r + 1) * C + c);
    }
    const components = () => {
      const comp = new Map();
      for (let r = 0; r < R; r++) for (let c = 0; c < C; c++) {
        const k2 = f(r * C + c);
        if (!comp.has(k2)) comp.set(k2, []);
        comp.get(k2).push([r, c]);
      }
      return comp;
    };
    let changed = true;
    while (changed) {
      changed = false;
      for (const cs of components().values()) {
        const r0 = Math.min(...cs.map((p) => p[0])), r1 = Math.max(...cs.map((p) => p[0]));
        const c0 = Math.min(...cs.map((p) => p[1])), c1 = Math.max(...cs.map((p) => p[1]));
        if ((r1 - r0 + 1) * (c1 - c0 + 1) !== cs.length) {
          for (let rr = r0; rr <= r1; rr++) for (let cc = c0; cc <= c1; cc++) u(r0 * C + c0, rr * C + cc);
          changed = true;
        }
      }
    }
    const cells = [];
    for (const cs of components().values()) {
      const r0 = Math.min(...cs.map((p) => p[0])), r1 = Math.max(...cs.map((p) => p[0]));
      const c0 = Math.min(...cs.map((p) => p[1])), c1 = Math.max(...cs.map((p) => p[1]));
      cells.push([r0, c0, r1 - r0 + 1, c1 - c0 + 1]);
    }
    cells.sort((p, q) => p[0] - q[0] || p[1] - q[1] || p[2] - q[2] || p[3] - q[3]);
    for (const [r, c, rs, cs] of cells) {
      for (let rr = r; rr < r + rs; rr++) for (let cc = c + 1; cc < c + cs; cc++) vs[rr][cc] = null;
      for (let cc = c; cc < c + cs; cc++) for (let rr = r + 1; rr < r + rs; rr++) hs[rr][cc] = null;
    }
    return { xs: xcen.map((v) => x + v), ys: ycen.map((v) => y + v), h: hs, v: vs, cells, extras, ppm };
  } finally { T.free(); }
}

export function trimOuter(grid, rowK = 2.2, colK = 4.0) {
  const removed = { top: 0, bottom: 0, left: 0, right: 0 };
  for (;;) {
    const { ys, xs } = grid;
    const hs = [], ws = [];
    for (let i = 0; i < ys.length - 1; i++) hs.push(ys[i + 1] - ys[i]);
    for (let i = 0; i < xs.length - 1; i++) ws.push(xs[i + 1] - xs[i]);
    if (hs.length < 4 || ws.length < 2) break;
    const mh = median(hs), mw = median(ws);
    let R = hs.length, C = ws.length;
    const { h, v } = grid;
    const closed = (side) => {
      if (side === 'left' || side === 'right') {
        const c = side === 'left' ? 0 : C - 1;
        const j = side === 'left' ? 0 : C;
        if (h[0][c] === null || h[R][c] === null) return false;
        let n = 0; for (let r = 0; r < R; r++) if (v[r][j] !== null) n++;
        return n >= 0.9 * R;
      }
      const r = side === 'top' ? 0 : R - 1;
      const i = side === 'top' ? 0 : R;
      if (v[r][0] === null || v[r][C] === null) return false;
      let n = 0; for (let c = 0; c < C; c++) if (h[i][c] !== null) n++;
      return n >= 0.9 * C;
    };
    const cand = [];
    if (hs[0] > rowK * mh) cand.push('top');
    if (hs[hs.length - 1] > rowK * mh) cand.push('bottom');
    if (ws.length > 3 && ws[0] > colK * mw) cand.push('left');
    if (ws.length > 3 && ws[ws.length - 1] > colK * mw) cand.push('right');
    const side = cand.find((s) => !closed(s));
    if (side === undefined) break;
    let r0 = 0, r1 = R, c0 = 0, c1 = C;
    if (side === 'top') r0 = 1;
    if (side === 'bottom') r1 = R - 1;
    if (side === 'left') c0 = 1;
    if (side === 'right') c1 = C - 1;
    const cells = [];
    for (const [r, c, rs, cs] of grid.cells) if (r >= r0 && c >= c0 && r + rs <= r1 && c + cs <= c1) cells.push([r - r0, c - c0, rs, cs]);
    grid = { ...grid };
    grid.xs = xs.slice(c0, c1 + 1); grid.ys = ys.slice(r0, r1 + 1);
    grid.h = grid.h.slice(r0, r1 + 1).map((row) => row.slice(c0, c1));
    grid.v = grid.v.slice(r0, r1).map((row) => row.slice(c0, c1 + 1));
    grid.cells = cells.sort((p, q) => p[0] - q[0] || p[1] - q[1] || p[2] - q[2] || p[3] - q[3]);
    removed[side]++;
  }
  return { grid, removed };
}

// photopage._extend_left
export function extendLeft(grid, mask, PPM = 10) {
  const x0 = grid.xs[0];
  const ya = Math.trunc(grid.ys[0]), yb = Math.trunc(grid.ys[grid.ys.length - 1]);
  if (x0 < 8 * PPM || x0 > 60 * PPM) return grid;
  const xa = Math.trunc(1.5 * PPM), xb = Math.trunc(x0 - 1.5 * PPM);
  let nz = 0;
  const W = mask.cols, d = mask.data;
  for (let y = ya; y < Math.min(yb, mask.rows); y++) for (let x = xa; x < Math.min(xb, W); x++) if (d[y * W + x] > 0) nz++;
  if (nz < 150) return grid;
  if (grid.cells.some(([r, c, rs, cs]) => c === 0 && cs > 1)) return grid;
  const g = { ...grid };
  g.xs = [0.0, ...grid.xs];
  g.h = grid.h.map((row) => [row[0], ...row]);
  g.v = grid.v.map((row) => [null, ...row]);
  const cells = grid.cells.map(([r, c, rs, cs]) => [r, c + 1, rs, cs]);
  for (let r = 0; r < grid.ys.length - 1; r++) cells.push([r, 0, 1, 1]);
  g.cells = cells.sort((p, q) => p[0] - q[0] || p[1] - q[1] || p[2] - q[2] || p[3] - q[3]);
  g.ext_left = true;
  return g;
}
