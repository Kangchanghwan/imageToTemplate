// photopage.bold_pass / align_pass / _cut / fit_pass / fit_blocks 이식 (break_pass 의 OCR 호출은 run.js 가 주입)
import { pyRound, pyRoundN } from './npy.js';

const PPM = 10;
export const BOLD_THR = 0.08;
export const ALIGN_TOL_MM = 2.0;
export const FIT_PAD_PT = 3.8, SHEET_W_RATIO = 1.075, FIT_MAX_DOWN = 1.5, SHEET_SCALE = 0.975;

export const maj = (vals) => vals.length > 0 && vals.reduce((a, b) => a + (b ? 1 : 0), 0) * 2 > vals.length;

// Python Counter.most_common(): 개수 내림차순, 같은 개수는 먼저 등장한 순
export function mostCommon(arr) {
  const m = new Map();
  for (const v of arr) m.set(v, (m.get(v) || 0) + 1);
  return [...m.entries()].map((e, i) => [e, i]).sort((a, b) => b[0][1] - a[0][1] || a[1] - b[1]).map((p) => p[0]);
}

export function boldPass(cells, HR, meta) {
  const vals = new Map();
  for (const c of cells) {
    if (!c.text) continue;
    const h = c._info.hth;
    if (h) vals.set(c, h[0] / (Math.max(c.size_pt, 1.0) * 25.4 / 72 * PPM));
  }
  if (!vals.size) return;
  let thr = BOLD_THR;
  const sv = [...vals.values()].sort((a, b) => a - b);
  let best = null;
  for (let i = 0; i + 1 < sv.length; i++) {
    const a = sv[i], b = sv[i + 1];
    if (0.06 <= (a + b) / 2 && (a + b) / 2 <= 0.105 && b - a >= 0.012 && (best === null || b - a > best[0])) best = [b - a, (a + b) / 2];
  }
  if (best) thr = best[1];
  meta.bold_thr = pyRoundN(thr, 4);
  const own = new Map();
  for (const c of cells) if (vals.has(c)) own.set(c, vals.get(c) >= thr);
  const hv = cells.filter((c) => c.r < HR && own.has(c)).map((c) => own.get(c));
  const rowb = new Map();
  for (const c of cells) if (own.has(c)) { if (!rowb.has(c.r)) rowb.set(c.r, []); rowb.get(c.r).push(own.get(c)); }
  for (const c of cells) {
    if (!c.text) continue;
    if (c.r < HR && hv.length) c.bold = maj(hv);
    else if (own.has(c)) c.bold = own.get(c);
    else c.bold = maj(rowb.get(c.r) || []);
  }
}

export function alignPass(cells, HR) {
  const dec = new Map();
  for (const c of cells) {
    const i = c._info;
    if (!c.text || !('gl' in i)) continue;
    const cw = i.cw / PPM;
    const d = (i.gr - i.gl) / PPM;
    const tol = Math.max(ALIGN_TOL_MM, 0.05 * cw);
    let o = Math.abs(d) <= tol ? 'CENTER' : (d > 0 ? 'LEFT' : 'RIGHT');
    let weak = tol < Math.abs(d) && Math.abs(d) < 2 * tol;
    const lb = i.lbx || [];
    if (lb.length >= 2) {
      const s0 = (Math.max(...lb.map((p) => p[0])) - Math.min(...lb.map((p) => p[0]))) / PPM;
      const s1 = (Math.max(...lb.map((p) => p[1])) - Math.min(...lb.map((p) => p[1]))) / PPM;
      if (s0 <= 1.0 && s1 > 1.0) { o = 'LEFT'; weak = false; }
      else if (s1 <= 1.0 && s0 > 1.0) { o = 'RIGHT'; weak = false; }
    } else if (i.fill >= 0.8 && [...c.text].filter((ch) => !/\s/.test(ch)).length > 20) { o = 'LEFT'; weak = false; }
    dec.set(c, [o, weak]);
  }
  const groups = new Map();
  for (const c of cells) {
    if (!dec.has(c)) continue;
    const k = c.r < HR ? 'h' + c.r : 'c' + c.c + ',' + c.cs;
    if (!groups.has(k)) groups.set(k, []);
    groups.get(k).push(c);
  }
  for (const cs of groups.values()) {
    const strong = cs.filter((c) => !dec.get(c)[1]).map((c) => dec.get(c)[0]);
    let mj = null;
    if (strong.length >= 3) {
      const [top, n] = mostCommon(strong)[0];
      if (n >= 0.6 * strong.length) mj = top;
    }
    for (const c of cs) {
      const [o, weak] = dec.get(c);
      c.h = (weak && mj) ? mj : o;
    }
  }
}

export function lev(a, b) {
  if (!a) return b.length;
  const A = [...a], B = [...b];
  let prev = Array.from({ length: B.length + 1 }, (_, i) => i);
  for (let i = 1; i <= A.length; i++) {
    const cur = [i];
    for (let j = 1; j <= B.length; j++) cur.push(Math.min(prev[j] + 1, cur[j - 1] + 1, prev[j - 1] + (A[i - 1] !== B[j - 1] ? 1 : 0)));
    prev = cur;
  }
  return prev[B.length];
}

const strip = (s) => s.replace(/^\s+|\s+$/g, '');   // Python str.strip()
const noSpace = (s) => [...s].filter((ch) => !/\s/.test(ch)).join('');

export function cut(text, lines) {
  const chars = [...text];
  const idx = [];
  chars.forEach((ch, k) => { if (!/\s/.test(ch)) idx.push(k); });
  const n = idx.length;
  let a = 0;
  const cuts = [];
  for (const ln of lines.slice(0, -1)) {
    const L = noSpace(ln);
    if (!L) return null;
    let best = null;
    for (let j = Math.max(a + 1, a + [...L].length - 3); j <= Math.min(n - 1, a + [...L].length + 3); j++) {
      const e = lev(idx.slice(a, j).map((k) => chars[k]).join(''), L);
      if (best === null || e < best[0] || (e === best[0] && Math.abs(j - a - [...L].length) < Math.abs(best[1] - a - [...L].length))) best = [e, j];
    }
    if (best === null || best[0] > Math.max(2, 0.4 * [...L].length)) return null;
    a = best[1];
    cuts.push(a);
  }
  const out = [];
  let prev = 0;
  for (const cj of cuts) { out.push(strip(chars.slice(prev, idx[cj]).join(''))); prev = idx[cj]; }
  out.push(strip(chars.slice(prev).join('')));
  return out.join('\n');
}

export function fitPass(cells, meta) {
  let nDown = 0;
  const steps = [];
  for (const c of cells) {
    const i = c._info || {};
    const lb = i.lbx || [];
    if (!c.text || !lb.length || c.size_pt <= 0) continue;
    const s0 = c.size_pt;
    const twPt = Math.max(...lb.map((p) => p[1] - p[0])) / PPM * 72 / 25.4;
    const avail = (c._rect[2] - c._rect[0]) / PPM * 72 / 25.4 - FIT_PAD_PT;
    const p0 = Math.max(1, Math.trunc(s0 / SHEET_SCALE + 0.5));
    let pt = p0;
    while (pt > 1 && twPt * SHEET_W_RATIO * pt * SHEET_SCALE / s0 > avail && pt - 1 >= s0 / SHEET_SCALE - FIT_MAX_DOWN) pt--;
    if (pt !== p0) { c.sheet_pt = pt; nDown++; steps.push([c.r, c.c, s0, p0, pt, pyRoundN(twPt, 1), pyRoundN(avail, 1)]); }
  }
  meta.fit_down = nDown;
  meta.fit_dbg = steps;
}

export function fitBlocks(blocks, meta) {
  let n = 0;
  for (const b of blocks) {
    const [x0, , x1] = b.bbox_mm;
    const s0 = b.size_pt;
    const tw = b._ink_w_mm;
    if (!tw || s0 <= 0) continue;
    const avail = (x1 - x0) * 72 / 25.4;
    const p0 = Math.max(1, Math.trunc(s0 / SHEET_SCALE + 0.5));
    let pt = p0;
    while (pt > 1 && tw * 72 / 25.4 * SHEET_W_RATIO * pt * SHEET_SCALE / s0 > avail && pt - 1 >= s0 / SHEET_SCALE - FIT_MAX_DOWN) pt--;
    if (pt !== p0) { b.sheet_pt = pt; n++; }
  }
  meta.fit_blocks_down = n;
}
