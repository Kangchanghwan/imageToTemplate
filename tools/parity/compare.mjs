// Python 덤프(out/py)와 JS 덤프(out/js)를 단계별로 비교한다.
// 사용: node tools/parity/compare.mjs <outdir> [--md report.md]
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const { PNG } = createRequire(path.join(here, '../../web/package.json'))('pngjs');

const outdir = path.resolve(process.argv[2]);
const mdIdx = process.argv.indexOf('--md');
const names = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8')).inputs.map((i) => i.name);

// 깊은 비교: 숫자는 최대 절대차, 나머지(문자열/불리언/null/길이/형식)는 불일치 개수
function diff(a, b, acc = { maxd: 0, nnum: 0, nneq: 0, nstruct: 0, where: null }, p = '') {
  if (typeof a === 'number' && typeof b === 'number') {
    acc.nnum++;
    const d = Math.abs(a - b);
    if (d > 0) acc.nneq++;
    if (d > acc.maxd) { acc.maxd = d; acc.where = p; }
  } else if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) { acc.nstruct++; acc.where ??= p + '[len]'; }
    const n = Math.min(a.length, b.length);
    for (let i = 0; i < n; i++) diff(a[i], b[i], acc, p + '[' + i + ']');
  } else if (a && b && typeof a === 'object' && typeof b === 'object') {
    const ks = new Set([...Object.keys(a), ...Object.keys(b)]);
    for (const k of ks) {
      if (!(k in a) || !(k in b)) { acc.nstruct++; acc.where ??= p + '.' + k + '[missing]'; continue; }
      diff(a[k], b[k], acc, p + '.' + k);
    }
  } else if (a !== b) { acc.nstruct++; acc.where ??= p + ' ' + JSON.stringify(a) + '!=' + JSON.stringify(b); }
  return acc;
}
function readPng(f) {
  const png = PNG.sync.read(fs.readFileSync(f));
  return png;
}
function pix(fa, fb) {
  const A = readPng(fa), B = readPng(fb);
  if (A.width !== B.width || A.height !== B.height) return { shape: 'DIFF', mad: null, pct: null, max: null };
  let sum = 0, nd = 0, mx = 0;
  const n = A.width * A.height;
  for (let i = 0; i < n; i++) {
    let dif = false;
    for (let c = 0; c < 3; c++) { const d = Math.abs(A.data[i * 4 + c] - B.data[i * 4 + c]); sum += d; if (d) dif = true; if (d > mx) mx = d; }
    if (dif) nd++;
  }
  return { shape: 'ok', mad: sum / (n * 3), pct: 100 * nd / n, max: mx };
}
const flagsStr = (fl) => JSON.stringify(fl);
const rows = [];
for (const name of names) {
  const pj = path.join(outdir, 'py', name + '.json'), jj = path.join(outdir, 'js', name + '.json');
  if (!fs.existsSync(jj)) continue;
  const P = JSON.parse(fs.readFileSync(pj, 'utf8')), J = JSON.parse(fs.readFileSync(jj, 'utf8'));
  const r = { name, kind: P.kind, stages: {} };
  const S = r.stages;
  S.input = { ok: P.input_sha === J.input_sha };
  if (P.find_paper !== undefined) S.find_paper = diff(P.find_paper, J.find_paper);
  S.rectify = { ...diff(P.rectify && { shape: P.rectify.shape, pg_mm: P.rectify.pg_mm, flags: P.rectify.flags }, J.rectify && { shape: J.rectify.shape, pg_mm: J.rectify.pg_mm, flags: J.rectify.flags }) };
  if (P.table_rectify || J.table_rectify) S.table_rectify = diff(P.table_rectify && { ok: P.table_rectify.ok, origin: P.table_rectify.origin, shape: P.table_rectify.shape }, J.table_rectify && { ok: J.table_rectify.ok, origin: J.table_rectify.origin, shape: J.table_rectify.shape });
  S.rect_img = { shape_eq: JSON.stringify(P.rect_shape) === JSON.stringify(J.rect_shape), sha_eq: P.rect_sha === J.rect_sha, ...pix(path.join(outdir, 'py', name + '_rect.png'), path.join(outdir, 'js', name + '_rect.png')) };
  S.mask = { nz: [P.mask.nz, J.mask.nz], sha_eq: P.mask.sha === J.mask.sha, hb_sha_eq: P.mask.hb_sha === J.mask.hb_sha, vb_sha_eq: P.mask.vb_sha === J.mask.vb_sha, hb_nz: [P.mask.hb_nz, J.mask.hb_nz], vb_nz: [P.mask.vb_nz, J.mask.vb_nz] };
  if (P.error || J.error) { S.error = { py: P.error, js: J.error }; rows.push(r); continue; }
  S.grid_raw = diff(P.grid_raw, J.grid_raw);
  S.trim = diff(P.trim, J.trim);
  S.grid = diff(P.grid, J.grid);
  S.flags = { eq: flagsStr(P.flags) === flagsStr(J.flags), py: P.flags.map((f) => f.reason), js: J.flags.map((f) => f.reason) };
  S.flat_img = { sha_eq: P.flat_sha === J.flat_sha, ...pix(path.join(outdir, 'py', name + '_flat.png'), path.join(outdir, 'js', name + '_flat.png')) };
  // 칸: 필드별 분리
  const cellCmp = { rc: diff(P.cells.map((c) => [c.r, c.c, c.rs, c.cs]), J.cells.map((c) => [c.r, c.c, c.rs, c.cs])), rect: diff(P.cells.map((c) => c._rect), J.cells.map((c) => c._rect)), empty: diff(P.cells.map((c) => c._empty), J.cells.map((c) => c._empty)) };
  const pick = (cells, ks) => cells.map((c) => Object.fromEntries(ks.filter((k) => k in c.info).map((k) => [k, c.info[k]])));
  const intKeys = ['h', 'v', 'lbands', 'lbx', 'gl', 'gr', 'cw', 'nlines', 'size_pt', 'bold', 'ink_h', 'ink_bbox'];
  const fltKeys = ['med', 'uni', 'fill', 'stroke_ratio', 'bgr'];
  cellCmp.info = diff(pick(P.cells, intKeys), pick(J.cells, intKeys));
  cellCmp.infoF = diff(pick(P.cells, fltKeys), pick(J.cells, fltKeys));
  // 경계 스타일(두께-0.2 보정 후 style_name) 불일치 수
  const sname = (v) => (v === null ? 'NONE' : v[1] ? 'DOUBLE' : Math.max(v[0] - 0.2, 0) < 0.35 ? 'SOLID' : Math.max(v[0] - 0.2, 0) < 0.7 ? 'SOLID_MEDIUM' : 'SOLID_THICK');
  let sm = 0, sn = 0;
  for (const k of ['h', 'v']) P.grid[k].forEach((row, i) => row.forEach((v, j) => { sn++; if (sname(v) !== sname(J.grid[k][i][j])) sm++; }));
  S.border_style = { total: sn, mismatch: sm };
  // 오케스트레이션 교차확인(Python 내부): run_page(ocr=False) 의 src_bbox 와 덤프 칸 rect 가 같은지
  const sc = P.spec_check;
  if (sc && sc.src_bbox) {
    const want = P.cells.map((c) => c._rect.map((v) => { const f = Math.floor(v), d = v - f; return d < 0.5 ? f : d > 0.5 ? f + 1 : (f % 2 === 0 ? f : f + 1); }));   // 은행가 반올림 차이는 경계값에서만
    const have = new Set(sc.src_bbox.map((b) => b.join(',')));
    S.orchestration = { cells: want.length, found: want.filter((w) => have.has(w.join(','))).length };
  }
  S.cells = cellCmp;
  S.merges = diff(P.merges, J.merges);
  r.py_sec = P.sec; r.js_ms = J.ms_best; r.timing = J.timing_ms;
  r.n = { rows: P.grid.ys.length - 1, cols: P.grid.xs.length - 1, cells: P.cells.length, merges: P.merges.length, empty: P.cells.filter((c) => c._empty).length };
  rows.push(r);
}
fs.writeFileSync(path.join(outdir, 'compare.json'), JSON.stringify(rows, null, 1));

// 요약표
const structOk = (S) => ['rectify', 'trim', 'grid', 'grid_raw', 'merges'].every((k) => !S[k] || S[k].nstruct === 0) &&
  S.flags?.eq && S.cells?.rc.nstruct === 0 && S.cells?.rc.nneq === 0 && S.cells?.empty.nstruct === 0 && S.cells?.empty.nneq === 0 && S.cells.empty.maxd === 0;
const f = (x, d = 4) => (x === null || x === undefined ? '-' : Number(x.toPrecision(d)).toString());
const lines = ['| 입력 | 종류 | 행x열 | 칸/병합/빈칸 | 구조일치 | 용지꼭짓점 최대차 | 격자 좌표 최대차 | 칸 rect 최대차 | 두께 최대차(mm) | 칸 info 정수필드 불일치(개/최대차) | 칸 info 실수필드 최대차 | 경계 스타일 불일치 | run_page 교차확인 | 보정이미지 평균절대차 / 다른픽셀% / 최대 | 평탄화 평균절대차 / 다른픽셀% / 최대 | JS ms |', '|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|'];
const detail = [];
for (const r of rows) {
  const S = r.stages;
  if (S.error) { lines.push(`| ${r.name} | ${r.kind} | 격자 오류 py=${S.error.py} js=${S.error.js} |`); continue; }
  const coord = Math.max(S.grid_raw.maxd, 0);
  // 격자 좌표(xs/ys)와 두께는 분리해 보고
  const gx = (() => { const P = JSON.parse(fs.readFileSync(path.join(outdir, 'py', r.name + '.json'), 'utf8')), J = JSON.parse(fs.readFileSync(path.join(outdir, 'js', r.name + '.json'), 'utf8'));
    const a = diff({ xs: P.grid.xs, ys: P.grid.ys, ex: P.grid.extras }, { xs: J.grid.xs, ys: J.grid.ys, ex: J.grid.extras });
    const b = diff({ xs: P.grid_raw.xs, ys: P.grid_raw.ys }, { xs: J.grid_raw.xs, ys: J.grid_raw.ys });
    const th = diff({ h: P.grid_raw.h, v: P.grid_raw.v }, { h: J.grid_raw.h, v: J.grid_raw.v });
    return { xy: Math.max(a.maxd, b.maxd), th: th.maxd, thS: th.nstruct }; })();
  const ci = S.cells.info, cf = S.cells.infoF;
  const fp = S.find_paper ? f(S.find_paper.maxd) + (S.find_paper.nstruct ? ' (구조차' + S.find_paper.nstruct + ')' : '') : '-';
  lines.push(`| ${r.name} | ${r.kind} | ${r.n.rows}x${r.n.cols} | ${r.n.cells}/${r.n.merges}/${r.n.empty} | ${structOk(S) && gx.thS === 0 ? '일치' : '**불일치**'} | ${fp} | ${f(gx.xy)} | ${f(S.cells.rect.maxd)} | ${f(gx.th)} | ${ci.nneq + ci.nstruct}/${f(ci.maxd)} | ${f(cf.maxd)} | ${S.border_style.mismatch}/${S.border_style.total} | ${S.orchestration ? S.orchestration.found + '/' + S.orchestration.cells : '-'} | ${f(S.rect_img.mad)} / ${f(S.rect_img.pct)} / ${S.rect_img.max} | ${f(S.flat_img.mad)} / ${f(S.flat_img.pct)} / ${S.flat_img.max} | ${r.js_ms} |`);
  detail.push(r.name + ': ' + JSON.stringify({ border_style: S.border_style, orchestration: S.orchestration, infoF: S.cells.infoF, find_paper: S.find_paper, rectify: S.rectify, grid_raw: S.grid_raw, trim: S.trim, grid: S.grid, flags: S.flags.eq ? 'eq' : S.flags, cells_rc: S.cells.rc, cells_empty: S.cells.empty, info: S.cells.info, mask: S.mask }));
}
const md = lines.join('\n');
console.log(md);
if (mdIdx > 0) fs.writeFileSync(process.argv[mdIdx + 1], md + '\n');
if (process.env.DETAIL) console.log('\n' + detail.join('\n'));
