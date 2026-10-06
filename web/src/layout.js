// layout.py 이식: pad_blocks, build_page_spec
import { pyRound, pyRoundN } from './npy.js';

const PX_MM = 96 / 25.4;
const MERGE_MM = 1.0;
const SHEET_PT_SCALE = 0.975;
const LINE_FACTOR = 1.3;

function bisectLeft(a, v) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < v) lo = m + 1; else hi = m; } return lo; }
function bisectRight(a, v) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (v < a[m]) hi = m; else lo = m + 1; } return lo; }
const uniqSorted = (arr) => [...new Set(arr)].sort((a, b) => a - b);

function cluster(vals, fixed, tol = MERGE_MM) {
  const fx = uniqSorted(fixed.map((v) => pyRoundN(v, 3)));
  const out = [...fx];
  const free = uniqSorted(vals.map((v) => pyRoundN(v, 3)));
  let last = null;
  for (const v of free) {
    if (fx.some((f) => Math.abs(v - f) < tol)) continue;
    if (last !== null && v - last < tol) continue;
    out.push(v);
    last = v;
  }
  return out.sort((a, b) => a - b);
}

function idx(bounds, v) {
  const i = bisectLeft(bounds, v);
  const cands = [i - 1, i].filter((j) => j >= 0 && j < bounds.length);
  let best = cands[0];
  for (const j of cands) if (Math.abs(bounds[j] - v) < Math.abs(bounds[best] - v)) best = j;
  return best;
}

function px(boundsMm, totalPx) {
  const cum = boundsMm.map((b) => pyRound(b * PX_MM));
  cum[0] = 0;
  cum[cum.length - 1] = totalPx;
  for (let i = 1; i < cum.length; i++) cum[i] = Math.max(cum[i], cum[i - 1]);
  return cum;
}

export function padBlocks(blocks, table, pageMm) {
  const H = pageMm[1];
  const tb = table ? [table.x_mm[0], table.y_mm[0], table.x_mm[table.x_mm.length - 1], table.y_mm[table.y_mm.length - 1]] : null;
  const orig = blocks.map((b) => [...b.bbox_mm]);
  const out = [];
  blocks.forEach((b, k) => {
    const [x0, y0, x1, y1] = orig[k];
    const sp = Math.max(1, Math.trunc((b._lay_pt ?? b.size_pt ?? 10) / SHEET_PT_SCALE + 0.5));
    const need = sp * 96 / 72 * LINE_FACTOR / PX_MM;
    const h = y1 - y0;
    const w = x1 - x0;
    const ex = (b.bold ? 0.14 : 0.07) * w + 1.0;
    const al = b.h ?? 'LEFT';
    let nx0 = x0 - (al === 'CENTER' ? ex / 2 : al === 'RIGHT' ? ex : 0);
    let nx1 = x1 + (al === 'CENTER' ? ex / 2 : al === 'LEFT' ? ex : 0);
    const W = pageMm[0];
    nx0 = Math.max(nx0, 1.0); nx1 = Math.min(nx1, W - 1.0);
    orig.forEach((o, j) => {
      if (j === k || o[3] <= y0 || o[1] >= y1) return;
      if (o[0] >= x1 - 0.1) nx1 = Math.min(nx1, Math.max(x1, (o[0] + x1) / 2 - 0.15));
      else if (o[2] <= x0 + 0.1) nx0 = Math.max(nx0, Math.min(x0, (o[2] + x0) / 2 + 0.15));
    });
    nx0 = Math.min(nx0, x0); nx1 = Math.max(nx1, x1);
    if (h >= need) { out.push({ ...b, bbox_mm: [nx0, y0, nx1, y1] }); return; }
    let lo = 0.0, hi = H;
    if (tb && x1 > tb[0] && x0 < tb[2]) {
      if (y1 <= tb[1] + 0.6) hi = tb[1] - 0.3;
      else if (y0 >= tb[3] - 0.6) lo = tb[3] + 0.3;
    }
    orig.forEach((o, j) => {
      if (j === k || o[2] <= x0 || o[0] >= x1) return;
      const oc = (o[1] + o[3]) / 2, c = (y0 + y1) / 2;
      if (oc < c) lo = Math.max(lo, (o[3] + y0) / 2);
      else hi = Math.min(hi, (y1 + o[1]) / 2);
    });
    const g = (need - h) / 2;
    let a = y0 - g, bb = y1 + g;
    if (bb > hi) { a -= bb - hi; bb = hi; }
    if (a < lo) { bb = Math.min(hi, bb + lo - a); a = lo; }
    out.push({ ...b, bbox_mm: [nx0, Math.max(a, lo), nx1, Math.min(bb, hi)] });
  });
  return out;
}

export function buildPageSpec(pageMm, table, blocks0, images, source) {
  const [W, H] = pageMm;
  const blocks = padBlocks(blocks0, table, pageMm);
  const fx = [0.0, W], fy = [0.0, H];
  const freex = [], freey = [];
  if (table) { fx.push(...table.x_mm); fy.push(...table.y_mm); }
  for (const b of blocks) { const [x0, y0, x1, y1] = b.bbox_mm; freex.push(x0, x1); freey.push(y0, y1); }
  let xs = cluster(freex, fx);
  let ys = cluster(freey, fy);
  const tfx = new Set((table ? table.x_mm : []).map((v) => pyRoundN(v, 3)));
  const tfy = new Set((table ? table.y_mm : []).map((v) => pyRoundN(v, 3)));
  xs = xs.filter((v, i) => i === 0 || i === xs.length - 1 || tfx.has(v) || v - xs[i - 1] >= 0.3);
  ys = ys.filter((v, i) => i === 0 || i === ys.length - 1 || tfy.has(v) || v - ys[i - 1] >= 0.3);
  const cpx = px(xs, pyRound(W * PX_MM));
  const rpx = px(ys, Math.trunc(W * 0 + H * PX_MM));
  const C = xs.length - 1, R = ys.length - 1;
  const columns = [], rows = [];
  for (let i = 0; i < C; i++) columns.push(cpx[i + 1] - cpx[i]);
  for (let i = 0; i < R; i++) rows.push(rpx[i + 1] - rpx[i]);
  const hB = Array.from({ length: R + 1 }, () => Array(C).fill('NONE'));
  const vB = Array.from({ length: R }, () => Array(C + 1).fill('NONE'));
  const cells = [];
  if (table) {
    const tx = table.x_mm.map((v) => idx(xs, v));
    const ty = table.y_mm.map((v) => idx(ys, v));
    for (const c of table.cells) {
      const r0 = ty[c.r], c0 = tx[c.c];
      const r1 = ty[c.r + (c.rs ?? 1)], c1 = tx[c.c + (c.cs ?? 1)];
      cells.push({ ...c, r: r0, c: c0, rs: Math.max(1, r1 - r0), cs: Math.max(1, c1 - c0), role: 'table' });
    }
    const th = table.borders.h, tv = table.borders.v;
    for (let i = 0; i < th.length; i++) for (let c = 0; c < th[i].length; c++) {
      const st = th[i][c];
      if (st === 'NONE') continue;
      for (let pc = tx[c]; pc < tx[c + 1]; pc++) hB[ty[i]][pc] = st;
    }
    for (let r = 0; r < tv.length; r++) for (let j = 0; j < tv[r].length; j++) {
      const st = tv[r][j];
      if (st === 'NONE') continue;
      for (let pr = ty[r]; pr < ty[r + 1]; pr++) vB[pr][tx[j]] = st;
    }
  }
  const occupied = new Set();
  for (const c of cells) for (let rr = c.r; rr < c.r + c.rs; rr++) for (let cc = c.c; cc < c.c + c.cs; cc++) occupied.add(rr + ',' + cc);
  const flags = [];
  for (const b of blocks) {
    const [x0, y0, x1, y1] = b.bbox_mm;
    let r0 = idx(ys, y0), r1 = idx(ys, y1), c0 = idx(xs, x0), c1 = idx(xs, x1);
    if (r1 <= r0) r1 = r0 + 1;
    if (c1 <= c0) c1 = c0 + 1;
    let hit = false;
    for (let rr = r0; rr < r1 && !hit; rr++) for (let cc = c0; cc < c1; cc++) if (occupied.has(rr + ',' + cc)) { hit = true; break; }
    if (hit) { flags.push({ reason: 'block_overlaps_table', text: (b.text ?? '').slice(0, 20) }); continue; }
    for (let rr = r0; rr < r1; rr++) for (let cc = c0; cc < c1; cc++) occupied.add(rr + ',' + cc);
    const { bbox_mm, ...d } = b;
    d.h ??= 'LEFT'; d.v ??= 'MIDDLE';
    Object.assign(d, { r: r0, c: c0, rs: r1 - r0, cs: c1 - c0, wrap: false, role: 'text', src_bbox: bbox_mm.map((v) => pyRoundN(v, 2)) });
    cells.push(d);
  }
  const imgs = [];
  for (const im of images) {
    const [x0, y0, x1, y1] = im.bbox_mm;
    let r = Math.max(0, bisectRight(ys, y0) - 1), c = Math.max(0, bisectRight(xs, x0) - 1);
    r = Math.min(r, R - 1); c = Math.min(c, C - 1);
    imgs.push({ r, c, dx_px: pyRound((x0 - xs[c]) * PX_MM), dy_px: pyRound((y0 - ys[r]) * PX_MM), w_px: pyRound((x1 - x0) * PX_MM), h_px: pyRound((y1 - y0) * PX_MM), png_b64: im.png_b64, bbox_mm: im.bbox_mm.map((v) => pyRoundN(v, 2)) });
  }
  return { version: 2, mode: 'page', source, page_mm: [W, H], columns, rows, cells, borders: { h: hB, v: vB }, images: imgs, flags, meta: { x_mm: xs, y_mm: ys } };
}
