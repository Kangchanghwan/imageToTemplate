// 이미지 -> 최종 spec (photopage._run_page 전체 이식). 브라우저/Node 공용(파일 입출력 없음).
// OCR 은 주입식:
//   opts.ocr = {
//     readCells(items, ctx)  async. items=[{r,c,crop(Mat BGR, ink-tight)}] -> [{text, conf?}] 같은 순서. Mat 소유권은 호출자(run.js)가 해제.
//     readBlocks(items, ctx) async. items=[{index, crop, bbox, band}] -> [text]
//     readLines(items, ctx)  async. items=[{cell:{r,c}, k, crop}] -> [text|null]   (break_pass 줄 읽기)
//   }
// opts.ocr 가 없으면 OCR 없는 모드(Python ocr=False 와 같음: 칸 텍스트 빈 문자열, 블록 텍스트 'x').
import { getCv, tracker } from './cv.js';
import { runFront } from './front.js';
import * as ST from './style.js';
import * as B from './blocks.js';
import * as P from './passes.js';
import * as L from './layout.js';
import * as O from './ocr_cv.js';
import { pyRound, pyRoundN, percentile, median } from './npy.js';

const PPM = 10;
const THICK_BIAS_MM = 0.2;
const BG_MIN_DROP = 12, BG_MAX_GRAY = 245, BG_MIN_UNIFORM = 0.65;
const FONT = 'Calibri';

const hex = (bgr) => {
  const [b, g, r] = bgr.map((v) => Math.trunc(Math.max(0, Math.min(255, pyRound(v)))));
  return '#' + [r, g, b].map((v) => v.toString(16).padStart(2, '0')).join('');
};
const pyStrip = (s) => s.replace(/^\s+|\s+$/g, '');
const HAS_ALNUM = /[\p{L}\p{N}]/u;

function modeOf(vals) {
  const q = vals.map((v) => pyRound(v * 2) / 2);
  const cnt = P.mostCommon(q);
  const top = cnt.filter(([, n]) => n === cnt[0][1]).map(([v]) => v);
  return top.length > 1 ? median(top) : top[0];
}

export async function runPage(img0, kind = 'photo', opts = {}) {
  const cv = getCv();
  const t00 = performance.now();
  const timing = {};
  let tl = performance.now();
  const lap = (k) => { const n = performance.now(); timing[k] = Math.round((n - tl) * 10) / 10; tl = n; };
  const front = runFront(img0, kind, opts.fixed ?? null);
  Object.assign(timing, front.timing); tl = performance.now();
  if (front.info.error) { front.rect.delete(); front.mask.delete(); front.hb.delete(); front.vb.delete(); throw new Error(front.info.error); }
  const { grid, tb, flat, fgray } = front;
  const flags = front.flags;
  let pgMm = front.pgMm;
  const xsMm = grid.xs.map((x) => x / PPM), ysMm = grid.ys.map((y) => y / PPM);
  const R = ysMm.length - 1, C = xsMm.length - 1;
  const sn = (i) => ST.styleName(i === null ? null : [Math.max(i[0] - THICK_BIAS_MM, 0), i[1]]);
  const borders = {
    h: Array.from({ length: R + 1 }, (_, i) => Array.from({ length: C }, (_, c) => sn(grid.h[i][c]))),
    v: Array.from({ length: R }, (_, r) => Array.from({ length: C + 1 }, (_, j) => sn(grid.v[r][j]))),
  };
  let nbg = 0;
  const cells = front.cellsRaw.map((fc) => {
    const info = fc.info;
    return {
      r: fc.r, c: fc.c, rs: fc.rs, cs: fc.cs, text: '', h: info.h ?? 'LEFT', v: info.v ?? 'MIDDLE', size_pt: 10, bold: info.bold ?? false, bg: null,
      wrap: true, font: FONT, underline: false, italic: false, color: '#000000',
      src_bbox: fc._rect.map((a) => pyRound(a)), _rect: fc._rect, _info: info, _empty: fc._empty,
    };
  });
  const meds = cells.filter((c) => 'med' in c._info).map((c) => c._info.med);
  const pref = meds.length ? percentile(meds, 75) : 255.0;
  for (const c of cells) {
    const i = c._info;
    if (i.bgr && (i.uni ?? 0) >= BG_MIN_UNIFORM && pref - i.med >= BG_MIN_DROP && i.med <= BG_MAX_GRAY) { c.bg = hex(i.bgr); nbg++; }
  }
  const meta = { calls: 0, bg_pref: pyRound(pref) };
  const cflags = [];
  lap('cells_build');
  const ocr = opts.ocr ?? null;
  const ocrStat = { cells: 0, blocks: 0, lines: 0 };
  // --- 내용 ---
  if (ocr) {
    const todo = cells.filter((c) => !c._empty);
    const items = [], owned = [];
    for (const c of todo) {
      const crop = O.cellCrop(flat, c._rect);
      items.push({ r: c.r, c: c.c, crop, rect: c._rect, nlines: c._info.nlines ?? 1, rs: c.rs, cs: c.cs });
      if (crop) owned.push(crop);
    }
    const res = await ocr.readCells(items, { cells: todo });
    owned.forEach((m) => m.delete());
    todo.forEach((c, k) => { c.text = pyStrip(res[k]?.text ?? ''); c._ocr = res[k]; });
    ocrStat.cells = todo.length;
    meta.calls += todo.length;
    lap('ocr_cells');
  }
  // --- 글자 크기 ---
  for (const c of cells) {
    if (c.text && c._info.ink_h) {
      const nl = pyStrip(c.text).length >= 12 ? c._info.nlines : null;
      c._sz = ST.sizeFromInk(c._info.ink_h, c.text, PPM, nl);
    }
  }
  const HR = 1;
  const bycol = new Map(), hdr = [];
  for (const c of cells) {
    if (!('_sz' in c)) continue;
    if (c.r < HR) hdr.push(c._sz);
    else if (c.cs === 1) { if (!bycol.has(c.c)) bycol.set(c.c, []); bycol.get(c.c).push(c._sz); }
  }
  const hdrM = hdr.length ? modeOf(hdr) : null;
  const colM = new Map([...bycol.entries()].map(([k, v]) => [k, modeOf(v)]));
  const allbody = [...bycol.values()].flat();
  const bodyM = allbody.length ? modeOf(allbody) : null;
  const hdrB = P.maj(cells.filter((c) => c.r < HR && c.text).map((c) => c.bold));
  let colB = new Map();
  for (const c of cells) if (c.r >= HR && c.cs === 1 && c.text) { if (!colB.has(c.c)) colB.set(c.c, []); colB.get(c.c).push(c.bold); }
  const bodyB = P.maj([...colB.values()].flat());
  colB = new Map([...colB.entries()].map(([k, v]) => [k, v.length >= 3 ? P.maj(v) : bodyB]));
  meta.bold_dbg = { hdr: hdrB, cols: Object.fromEntries([...colB.entries()].map(([k, v]) => [String(k), v])) };
  for (const c of cells) {
    if (!c.text) continue;
    if (c.r < HR) { c.size_pt = hdrM ? hdrM : c.size_pt; c.bold = hdrB; }
    else if (c.cs === 1) { c.size_pt = colM.has(c.c) ? colM.get(c.c) : (bodyM ? bodyM : c.size_pt); c.bold = colB.has(c.c) ? colB.get(c.c) : bodyB; }
    else if ('_sz' in c) c.size_pt = pyRound(c._sz * 2) / 2;
  }
  lap('sizes');
  // --- 칸 안 줄바꿈 위치 (break_pass) ---
  if (ocr) {
    const brk = cells.filter((c) => (c._info.lbands || []).length >= 2 && [...c.text].filter((ch) => !/\s/.test(ch)).length >= 4 && !c.text.includes('\n'));
    if (brk.length) {
      const items = [], owned = [];
      for (const c of brk) for (let k = 0; k < c._info.lbands.length - 1; k++) {
        const crop = O.lineCrop(flat, c._rect, c._info.lbands, k);
        items.push({ cell: { r: c.r, c: c.c, text: c.text }, k, crop });
        if (crop) owned.push(crop);
      }
      const res = await ocr.readLines(items, { cells: brk });
      owned.forEach((m) => m.delete());
      let p = 0, nb = 0;
      meta.calls += items.length;
      ocrStat.lines = items.length;
      for (const c of brk) {
        const n = c._info.lbands.length - 1;
        const lines = res.slice(p, p + n); p += n;
        if (lines.some((x) => x === null || x === undefined)) { meta.break_fail = (meta.break_fail || 0) + 1; continue; }
        const t = P.cut(c.text, [...lines, 'x']);
        if (t) { c.text = t; nb++; }
      }
      meta.breaks = nb;
    }
    lap('ocr_lines');
  }
  // --- 표 밖 텍스트 ---
  const blocks = [];
  {
    const fb = B.findBlocks(flat, fgray, tb);
    lap('find_blocks');
    const bnds = B.bands(fb);
    const keepIdx = [];
    fb.forEach((b, i) => {
      const [x0, y0, x1, y1] = b.bbox;
      if ((x1 - x0) < 8 * PPM || x0 > tb[2] + 15 * PPM || x1 < tb[0] - 15 * PPM) {
        flags.push({ reason: 'block_dropped_outside_paper_or_tiny', bbox_mm: b.bbox.map((v) => pyRoundN(v / PPM, 1)) });
      } else keepIdx.push(i);
    });
    // Python 은 블록마다 순서대로 읽고 버림 판정을 하므로 flags 순서를 맞추려고 읽기 결과를 모은 뒤 같은 순서로 처리한다.
    let texts = keepIdx.map(() => 'x');
    if (ocr) {
      const items = [], owned = [];
      for (const i of keepIdx) {
        const crop = O.blockCrop(flat, fb[i].bbox, bnds[i]);
        items.push({ index: i, crop, bbox: fb[i].bbox, band: bnds[i] });
        if (crop) owned.push(crop);
      }
      texts = await ocr.readBlocks(items, { blocks: fb });
      owned.forEach((m) => m.delete());
      meta.calls += keepIdx.length;
      ocrStat.blocks = keepIdx.length;
    }
    lap('ocr_blocks');
    // flags 순서: Python 은 루프 안에서 drop 사유를 순서대로 추가. 위 첫 번째 사유(작음)와 섞이므로 재구성한다.
    const dropSmall = new Set(fb.map((_, i) => i).filter((i) => !keepIdx.includes(i)));
    const flagsSmall = flags.splice(flags.length - dropSmall.size, dropSmall.size);
    let fsi = 0;
    for (let i = 0; i < fb.length; i++) {
      const b = fb[i];
      if (dropSmall.has(i)) { flags.push(flagsSmall[fsi++]); continue; }
      const t0 = texts[keepIdx.indexOf(i)];
      const t = t0 == null ? '' : t0;
      const [x0, y0, x1, y1] = b.bbox;
      const band = bnds[i];
      if (!t || !HAS_ALNUM.test(t)) { flags.push({ reason: 'block_dropped_unreadable', bbox_mm: b.bbox.map((v) => pyRoundN(v / PPM, 1)) }); continue; }
      const ty0 = tb[1] / PPM, ty1 = tb[3] / PPM;
      let by0 = y0 / PPM - 1.2, by1 = y1 / PPM + 1.2;
      by0 = Math.max(by0, band[0] / PPM); by1 = Math.min(by1, band[1] / PPM);
      if (by1 > ty0 - 0.3 && y1 / PPM <= ty0 + 1) by1 = ty0 - 0.3;
      if (by0 < ty1 + 0.3 && y0 / PPM >= ty1 - 1) by0 = ty1 + 0.3;
      const bx1 = Math.min(x1 / PPM + 0.12 * (x1 - x0) / PPM, pgMm[0] - 1.0);
      const bb = [x0 / PPM, by0, Math.max(bx1, x1 / PPM), by1];
      let hh = 'LEFT';
      const tx0 = tb[0] / PPM, tx1 = tb[2] / PPM;
      if (Math.abs((x0 + x1) / 2 / PPM - (tx0 + tx1) / 2) < 0.06 * (tx1 - tx0) && x0 / PPM > tx0 - 3 && x1 / PPM < tx1 + 3) { bb[0] = tx0; bb[2] = tx1; hh = 'CENTER'; }
      blocks.push({
        bbox_mm: bb, text: pyStrip(t),
        _lay_pt: ST.sizeFromInk(b.ink_h * ((b.ext_small && (t.includes('(') || t.includes(')'))) ? 0.88 : 1.0), t),
        size_pt: ST.sizeFromInk((b.ink_h2 ?? b.ink_h) * B.blkCorr(t, b.bold, (b.ink_h2 ?? 0) / PPM), t),
        bold: b.bold, underline: b.underline, font: FONT, italic: false, color: '#000000', h: hh, v: 'MIDDLE',
        _ink_w_mm: (x1 - x0) / PPM, _stroke: pyRoundN(b.stroke_ratio ?? 0, 3), _line: b.line ?? null, _nc: b.nc ?? 0,
      });
    }
  }
  lap('blocks_build');
  // 같은 글줄에서 갈라진 조각
  const byl = new Map();
  for (const b of blocks) if (b._line !== null && b._line !== undefined) { if (!byl.has(b._line)) byl.set(b._line, []); byl.get(b._line).push(b); }
  for (const grp of byl.values()) {
    if (grp.length >= 2) {
      let ref = grp[0];
      for (const b of grp) if (b._nc > ref._nc) ref = b;   // max(key) 첫 최대
      for (const b of grp) { b.size_pt = ref.size_pt; b._lay_pt = ref._lay_pt; }
      grp.sort((a, b) => a.bbox_mm[0] - b.bbox_mm[0]);
      const last = grp[grp.length - 1];
      const tx0 = tb[0] / PPM, tx1 = tb[2] / PPM;
      if (last.h === 'LEFT' && last.bbox_mm[0] > (tx0 + tx1) / 2 && last.bbox_mm[2] >= tx1 - 14) last.h = 'RIGHT';
    }
  }
  for (const [grp] of [[cells.filter((c) => c.text), 'c'], [blocks, 'b']].map((x) => [x[0]])) {
    if (grp.length) {
      const mp = ST.unifySizes(grp.map((g) => pyRound(g.size_pt * 2) / 2));
      for (const g of grp) g.size_pt = mp.get(pyRound(g.size_pt * 2) / 2);
    }
  }
  P.fitBlocks(blocks, meta);
  P.boldPass(cells.filter((c) => c.text), HR, meta);
  P.alignPass(cells.filter((c) => c.text), HR);
  P.fitPass(cells, meta);
  const bsz = cells.filter((c) => c.r >= HR && c.text && c.cs === 1).map((c) => c.size_pt);
  if (bsz.length) {
    const bm = median(bsz);
    for (const b of blocks) if (b.h === 'CENTER' && b.size_pt >= 1.2 * bm && b._stroke >= 0.08) b.bold = true;
  }
  meta.tb = tb.map((v) => Math.trunc(v));
  meta.bg_cells = nbg;
  lap('passes');
  const outCells = cells.map((c) => {
    const { _rect, _info, _empty, _sz, _est, _ocr, ...rest } = c;
    return rest;
  });
  const table = { x_mm: xsMm, y_mm: ysMm, cells: outCells, borders };
  const src = { path: opts.sourcePath ?? '', kind, page: 0 };
  const spec = L.buildPageSpec(pgMm, table, blocks, [], src);
  spec.flags = [...(spec.flags || []), ...flags, ...cflags];
  for (const e of grid.extras) spec.flags.push({ reason: 'extra_table_ignored', bbox: e.map((a) => Math.trunc(a / PPM * 10)) });
  Object.assign(spec.meta, meta);
  spec.meta.blocks = blocks.map((b) => ({ text: b.text, bbox_mm: b.bbox_mm.map((v) => pyRoundN(v, 1)), size_pt: b.size_pt }));
  lap('layout');
  timing.total = Math.round((performance.now() - t00) * 10) / 10;
  spec.meta.timing_ms = timing;
  spec.meta.ocr_stat = ocrStat;
  const rect = front.rect;
  const result = { spec, timing, cellsDbg: cells.map((c) => ({ r: c.r, c: c.c, ocr: c._ocr })) };
  for (const m of [opts.keepRect ? null : front.rect, front.flat, front.fgray, front.mask, front.hb, front.vb]) if (m) m.delete();
  if (opts.keepRect) result.rect = rect;
  return result;
}
