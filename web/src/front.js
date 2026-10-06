// photopage._run_page 앞부분(입력 -> 보정 -> 격자 -> 칸 생성, OCR 없음) 이식.
// 입력: img0 = BGR Mat (photo: 원본 디코드, pdf_scan: 이미 10px/mm 로 줄인 용지 이미지)
import { getCv, tracker, copyMat } from './cv.js';
import * as PP from './preprocess.js';
import * as G from './grid.js';
import * as ST from './style.js';
import { pyRoundN } from './npy.js';

const PPM = PP.PPM;

// pdf_scan 입력(300dpi 렌더) -> 10px/mm 정규화 (convert._render_scan 의 resize 부분)
export function scanNormalize(img300, dpi = 300) {
  const cv = getCv();
  const k = PPM / (dpi / 25.4);
  const out = new cv.Mat();
  cv.resize(img300, out, new cv.Size(0, 0), k, k, cv.INTER_AREA);
  return out;
}

const now = () => performance.now();

// 반환: { info(JSON 가능 덤프), rect(Mat), flat(Mat), mask, hb, vb (Mat), timing }  — Mat 은 호출자가 delete
export function runFront(img0, kind = 'photo', fixed = null) {
  const cv = getCv();
  const timing = {};
  let t = now();
  const lap = (k) => { const n = now(); timing[k] = Math.round((n - t) * 10) / 10; t = n; };
  const info = { kind };
  let img, pgMm, flags;
  if (fixed) {   // 모드 (i): Python 이 만든 보정 이미지/페이지 mm/flags 를 그대로 사용 (rectify, table_rectify 생략)
    img = copyMat(fixed.img); pgMm = fixed.pgMm; flags = fixed.flags.map((f) => ({ ...f }));
    info.rectify = { shape: [img.rows, img.cols, 3], pg_mm: pgMm, flags: flags.map((f) => ({ ...f })) };
  } else {
  if (kind === 'photo') {
    const fp = PP.findPaper(img0);
    info.find_paper = fp === null ? null : { quad: fp.quad, touch: fp.touch };
    lap('find_paper');
    const r = PP.rectify(img0);
    img = r.img; pgMm = r.pageMm; flags = r.flags;
    lap('rectify');
  } else {
    img = copyMat(img0);
    pgMm = [pyRoundN(img0.cols / PPM, 1), pyRoundN(img0.rows / PPM, 1)];
    flags = [{ reason: 'pdf_scan_no_perspective' }];
  }
  info.rectify = { shape: [img.rows, img.cols, 3], pg_mm: pgMm, flags: flags.map((f) => ({ ...f })) };
  if (kind !== 'pdf_scan' && flags.some((f) => f.reason.startsWith('no_paper') || f.reason.startsWith('paper_'))) {
    const tr = PP.tableRectify(img, true);
    img.delete(); img = tr.img;
    flags.push({ reason: tr.ok ? 'table_quad_rectified' : 'table_quad_failed' });
    flags.push({ reason: 'mm_scale_from_table_estimate' });
    pgMm = [210, pyRoundN(img.rows / PPM, 1)];
    info.table_rectify = { ok: tr.ok, origin: tr.origin, shape: [img.rows, img.cols, 3] };
    lap('table_rectify');
  }
  }
  info.rect_shape = [img.rows, img.cols, 3];
  info.pg_mm = pgMm;
  const mask = PP.lineMask(img);
  lap('line_mask');
  const { hb, vb } = G.lineMasks(mask, PPM);
  lap('line_masks');
  const out = { info, rect: img, mask, hb, vb, timing, flags, pgMm };
  let grid;
  try { grid = G.buildGrid(mask, PPM); } catch (e) { info.error = 'grid_failed:' + e.message; return out; }
  lap('build_grid');
  info.grid_raw = { xs: grid.xs, ys: grid.ys, h: grid.h, v: grid.v, cells: grid.cells, extras: grid.extras, ext_left: false };
  const tr = G.trimOuter(grid);
  grid = tr.grid;
  info.trim = { removed: tr.removed, grid: { xs: grid.xs, ys: grid.ys, h: grid.h, v: grid.v, cells: grid.cells, extras: grid.extras, ext_left: false } };
  if (Object.values(tr.removed).some((v) => v)) {
    flags.push({ reason: 'outer_rows_cols_trimmed:' + Object.entries(tr.removed).filter(([, v]) => v).map(([k, v]) => `${k}=${v}`).join(',') });
  }
  grid = G.extendLeft(grid, mask, PPM);
  if (grid.ext_left) flags.push({ reason: 'table_clipped_left_column_added' });
  info.grid = { xs: grid.xs, ys: grid.ys, h: grid.h, v: grid.v, cells: grid.cells, extras: grid.extras, ext_left: !!grid.ext_left };
  info.flags = flags;
  lap('trim_extend');
  const xsMm = grid.xs.map((x) => x / PPM), ysMm = grid.ys.map((y) => y / PPM);
  const tb = [grid.xs[0], grid.ys[0], grid.xs[grid.xs.length - 1], grid.ys[grid.ys.length - 1]];
  const flat = PP.flatten(img, tb);
  out.flat = flat;
  lap('flatten');
  const fgray = new cv.Mat();
  cv.cvtColor(flat, fgray, cv.COLOR_BGR2GRAY);
  const cells = [];
  for (const [r, c, rs, cs] of grid.cells) {
    const rect = [xsMm[c] * PPM, ysMm[r] * PPM, xsMm[c + cs] * PPM, ysMm[r + rs] * PPM];
    const inf = ST.analyze(flat, fgray, rect);
    const { empty, ...rest } = inf;
    cells.push({ r, c, rs, cs, _rect: rect, _empty: !!empty, info: rest });
  }
  out.fgray = fgray;
  info.cells = cells;
  out.grid = grid; out.tb = tb; out.cellsRaw = cells;
  info.merges = cells.filter((c) => c.rs > 1 || c.cs > 1).map((c) => [c.r, c.c, c.rs, c.cs]);
  lap('analyze_cells');
  return out;
}
