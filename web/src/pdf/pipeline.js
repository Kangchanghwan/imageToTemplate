// pipeline.run_pdf_page / _cell_align 이식 (PDF 벡터 경로, PageSpec v2). OCR 없음.
import { getCv } from '../cv.js';
import { buildGrid } from '../grid.js';
import { styleName } from '../style.js';
import { buildPageSpec } from '../layout.js';
import { pyRound, pyRoundN } from '../npy.js';
import * as V from './pdfvec.js';

const PT_MM = V.PT_MM;
const BASE_DY_MM_PER_PT = 0.082;

export function cellAlign(tb, rect) {
  const L = tb[0] - rect[0], Rm = rect[2] - tb[2];
  const T = tb[1] - rect[1], B = rect[3] - tb[3];
  const cw = rect[2] - rect[0], ch = rect[3] - rect[1];
  const h = Math.abs(L - Rm) <= Math.max(3.0, 0.08 * cw) ? 'CENTER' : (L < Rm ? 'LEFT' : 'RIGHT');
  const v = Math.abs(T - B) <= Math.max(2.5, 0.2 * ch) ? 'MIDDLE' : (T < B ? 'TOP' : 'BOTTOM');
  return [h, v];
}

// np.searchsorted(a, v) (side='left')
function searchsorted(a, v) { let lo = 0, hi = a.length; while (lo < hi) { const m = (lo + hi) >> 1; if (a[m] < v) lo = m + 1; else hi = m; } return lo; }
const strip = (s) => s.replace(/^\s+|\s+$/g, '');

// E: extractPage 결과. opts: {path, pageNo, font, encodePng(w,h,rgba)->base64}
export function runPdfPage(E, opts = {}) {
  const t0 = performance.now();
  const font = opts.font ?? 'Calibri';
  const pageNo = opts.pageNo ?? 0;
  const W_mm = pyRoundN(E.rect[2] * PT_MM, 1), H_mm = pyRoundN(E.rect[3] * PT_MM, 1);
  const lines = V.textLines(E);
  const { ids: skip, ul } = V.underlineSegs(E, lines);
  const mask = V.maskV2(E, skip);
  let table = null, tbPt = null, grid = null;
  const flags = [];
  try { grid = buildGrid(mask, V.MASK_PPM); } catch (e) { if (e.message !== 'no_lines' && e.message !== 'no_grid') throw e; grid = null; }
  mask.delete();
  const fl = V.fills(E);
  let xs, ys, xsPt, ysPt, R, C, cells, owner, bh, bv;
  if (grid !== null) {
    const ppm = grid.ppm;
    xs = grid.xs.map((x) => x / ppm); ys = grid.ys.map((y) => y / ppm);
    xsPt = xs.map((v) => v / PT_MM); ysPt = ys.map((v) => v / PT_MM);
    tbPt = [xsPt[0], ysPt[0], xsPt[xsPt.length - 1], ysPt[ysPt.length - 1]];
    R = ys.length - 1; C = xs.length - 1;
    bh = Array.from({ length: R + 1 }, (_, i) => Array.from({ length: C }, (_, c) => styleName(grid.h[i][c])));
    bv = Array.from({ length: R }, (_, r) => Array.from({ length: C + 1 }, (_, j) => styleName(grid.v[r][j])));
    cells = []; owner = new Map();
    for (const [r, c, rs, cs] of grid.cells) {
      const cell = { r, c, rs, cs, text: '', h: 'CENTER', v: 'MIDDLE', size_pt: 10, bold: false, wrap: false, bg: null, font, underline: false, italic: false, color: '#000000', _lines: [] };
      const rect = [xsPt[c], ysPt[r], xsPt[c + cs], ysPt[r + rs]];
      cell._rect = rect;
      cell.src_bbox = rect.map((v) => pyRoundN(v * PT_MM, 2));
      const cx = (rect[0] + rect[2]) / 2, cy = (rect[1] + rect[3]) / 2;
      for (const f of fl) if (f[0] - 0.5 <= cx && cx <= f[2] + 0.5 && f[1] - 0.5 <= cy && cy <= f[3] + 0.5) cell.bg = f[4];
      if (cell.bg && ['#ffffff', '#fefefe'].includes(cell.bg.toLowerCase())) cell.bg = null;
      for (let rr = r; rr < r + rs; rr++) for (let cc = c; cc < c + cs; cc++) owner.set(rr + ',' + cc, cell);
      cells.push(cell);
    }
  }
  const blocks = [];
  for (const l of lines) {
    const whole = V.wholeLine(l);
    const cx = (whole.x0 + whole.x1) / 2, cy = (whole.y0 + whole.y1) / 2;
    const inside = tbPt && tbPt[0] - 1 <= cx && cx <= tbPt[2] + 1 && tbPt[1] - 1 <= cy && cy <= tbPt[3] + 1;
    if (inside) {
      const cc = searchsorted(xsPt, cx) - 1, rr = searchsorted(ysPt, cy) - 1;
      const cell = owner.get(Math.min(Math.max(rr, 0), R - 1) + ',' + Math.min(Math.max(cc, 0), C - 1));
      if (cell) { whole.ul = V.isUnderlined(whole, ul); cell._lines.push(whole); }
      continue;
    }
    for (const sg of V.splitSegments(l)) { sg.ul = V.isUnderlined(sg, ul); blocks.push([l, sg]); }
  }
  if (grid !== null) {
    for (const cell of cells) {
      const ls = cell._lines.map((s, i) => [s, i]).sort((a, b) => pyRound(a[0].oy / 2) - pyRound(b[0].oy / 2) || a[0].x0 - b[0].x0 || a[1] - b[1]).map((p) => p[0]);
      const rect = cell._rect;
      delete cell._lines; delete cell._rect;
      if (!ls.length) continue;
      const merged = [];
      for (const s_ of ls) {
        if (merged.length && Math.abs(merged[merged.length - 1].oy - s_.oy) < 2) {
          const m = merged[merged.length - 1];
          m.text += ' ' + s_.text; m.x1 = Math.max(m.x1, s_.x1);
        } else merged.push({ ...s_ });
      }
      cell.text = merged.map((m) => m.text).join('\n');
      cell.wrap = merged.length > 1;
      cell.size_pt = Math.max(...merged.map((m) => m.size));
      cell.bold = merged.reduce((a, m) => a + (m.bold ? 1 : 0), 0) * 2 > merged.length;
      cell.underline = merged.every((m) => m.ul);
      cell.color = merged[0].color;
      const tb = [Math.min(...merged.map((m) => m.x0)), Math.min(...merged.map((m) => m.y0)), Math.max(...merged.map((m) => m.x1)), Math.max(...merged.map((m) => m.y1))];
      [cell.h, cell.v] = cellAlign(tb, rect);
      if (merged.length >= 2) {
        const s0 = Math.max(...merged.map((m) => m.x0)) - Math.min(...merged.map((m) => m.x0));
        const s1 = Math.max(...merged.map((m) => m.x1)) - Math.min(...merged.map((m) => m.x1));
        if (s0 <= 1.5 && 1.5 < s1) cell.h = 'LEFT';
        else if (s1 <= 1.5 && 1.5 < s0) cell.h = 'RIGHT';
      } else if ((tb[2] - tb[0]) >= 0.8 * (rect[2] - rect[0]) && [...cell.text].filter((ch) => !/\s/.test(ch)).length > 20) cell.h = 'LEFT';
      let pt = Math.max(1, Math.trunc(cell.size_pt / 0.975 + 0.5));
      const tw = Math.max(...merged.map((m) => m.x1 - m.x0));
      if (tw * pt * 0.975 / cell.size_pt > (rect[2] - rect[0]) - 3.5 && pt > 1) pt -= 1;
      cell.sheet_pt = pt;
    }
    for (const cell of cells) { delete cell._lines; delete cell._rect; }
    table = { x_mm: xs, y_mm: ys, cells, borders: { h: bh, v: bv } };
  }
  const refL = tbPt ? tbPt[0] : 36.0;
  const refR = tbPt ? tbPt[2] : E.rect[2] - 36.0;
  const pc = (refL + refR) / 2;
  const bl = [];
  const byLine = new Map();
  for (const [l, sg] of blocks) { if (!byLine.has(l)) byLine.set(l, []); byLine.get(l).push(sg); }
  for (const segs of byLine.values()) {
    segs.sort((a, b) => a.x0 - b.x0);
    segs.forEach((sg, k) => {
      const cx = (sg.x0 + sg.x1) / 2;
      let h;
      if (segs.length === 1 && Math.abs(cx - pc) < 8) h = 'CENTER';
      else if (k === segs.length - 1 && Math.abs(sg.x1 - refR) < 14 && sg.x0 > pc) h = 'RIGHT';
      else h = 'LEFT';
      const dy = -BASE_DY_MM_PER_PT * sg.size;
      bl.push({ bbox_mm: [sg.x0 * PT_MM, sg.y0 * PT_MM + dy, sg.x1 * PT_MM, sg.y1 * PT_MM + dy], text: sg.text, size_pt: sg.size, bold: sg.bold, underline: sg.ul, font, h, color: sg.color, italic: false, v: 'MIDDLE' });
    });
  }
  const ims = (opts.images ?? []).map((im) => ({ bbox_mm: im.bbox.map((v) => v * PT_MM), png_b64: im.png_b64 }));
  const spec = buildPageSpec([W_mm, H_mm], table, bl, ims, { path: opts.path ?? '', kind: 'pdf_vector', page: pageNo });
  for (const c of spec.cells) c.size_pt = pyRound(c.size_pt * 2) / 2;
  spec.flags = [...spec.flags, ...flags];
  spec.meta.sec_geom = Math.round((performance.now() - t0)) / 1000;
  return spec;
}

// 이미지: extractPage 결과의 images -> [{bbox, png_b64}] (encodePng(w,h,rgba Uint8) -> base64)
export async function pdfImages(E, encodePng) {
  const out = [];
  for (const im of E.images) {
    const i = im.img;
    if (!i || !i.data) continue;
    let rgba;
    if (i.kind === 3) rgba = new Uint8Array(i.data.buffer, i.data.byteOffset, i.data.length);
    else if (i.kind === 2) { rgba = new Uint8Array(i.width * i.height * 4); for (let k = 0, n = i.width * i.height; k < n; k++) { rgba[k * 4] = i.data[k * 3]; rgba[k * 4 + 1] = i.data[k * 3 + 1]; rgba[k * 4 + 2] = i.data[k * 3 + 2]; rgba[k * 4 + 3] = 255; } }
    else continue;   // 1bpp 등은 미지원
    out.push({ bbox: im.bbox, png_b64: await encodePng(i.width, i.height, rgba), w: i.width, h: i.height });
  }
  return out;
}
