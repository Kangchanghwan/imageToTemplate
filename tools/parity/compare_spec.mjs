// 최종 spec 필드 단위 대조: node tools/parity/compare_spec.mjs <outdir> <i|ii> [--md file] [--list]
import fs from 'node:fs';
import path from 'node:path';
const outdir = path.resolve(process.argv[2]);
const mode = process.argv[3];
const mdIdx = process.argv.indexOf('--md');
const LIST = process.argv.includes('--list');
const names = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8')).inputs.map((i) => i.name);
const J = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));
const eqv = (a, b) => (typeof a === 'number' && typeof b === 'number') ? a === b : JSON.stringify(a) === JSON.stringify(b);
const TOL = Number(process.env.NUMTOL || 0);   // 좌표 허용치(기본 0)
const same = (a, b) => (typeof a === 'number' && typeof b === 'number') ? Math.abs(a - b) <= TOL : JSON.stringify(a) === JSON.stringify(b);

const CELL_FIELDS = ['text', 'h', 'v', 'size_pt', 'bold', 'bg', 'wrap', 'font', 'underline', 'italic', 'color', 'src_bbox', 'sheet_pt', '_lay_pt', '_ink_w_mm', '_stroke', '_line', '_nc'];
const rows = [], lists = [];
const tot = { fields: 0, ok: 0 };
for (const name of names) {
  const pf = path.join(outdir, 'spec_py', name + '.json'), jf = path.join(outdir, 'spec_js_' + mode, name + '.json');
  if (!fs.existsSync(jf)) continue;
  const P = J(pf), S = J(jf);
  const r = { name, page: eqv(P.page_mm, S.page_mm), colw: eqv(P.columns, S.columns), rowh: eqv(P.rows, S.rows), xy: eqv(P.meta.x_mm, S.meta.x_mm) && eqv(P.meta.y_mm, S.meta.y_mm),
    borders: eqv(P.borders, S.borders), flags: eqv(P.flags, S.flags), images: eqv(P.images, S.images) };
  const key = (c) => [c.role, c.r, c.c, c.rs, c.cs].join(',');
  const pm = new Map(P.cells.map((c) => [key(c), c])), sm = new Map(S.cells.map((c) => [key(c), c]));
  const common = [...pm.keys()].filter((k) => sm.has(k));
  r.ncells = [P.cells.length, S.cells.length];
  r.structOk = common.length === P.cells.length && common.length === S.cells.length;
  const bad = {};
  let nf = 0, nok = 0;
  const badCells = new Set();
  for (const k of common) {
    const a = pm.get(k), b = sm.get(k);
    for (const f of CELL_FIELDS) {
      if (!(f in a) && !(f in b)) continue;
      nf++;
      if (same(a[f], b[f])) nok++;
      else { bad[f] = (bad[f] || 0) + 1; badCells.add(k); if (LIST) lists.push(`${name} [${k}] ${f}: py=${JSON.stringify(a[f])} js=${JSON.stringify(b[f])}`); }
    }
  }
  // 구조 항목(행높이/열폭/병합/테두리/flags/x_mm,y_mm)도 필드 수에 포함
  for (const f of ['page', 'colw', 'rowh', 'xy', 'borders', 'flags', 'images']) { nf++; if (r[f]) nok++; else if (LIST) lists.push(`${name} ${f}: py/js 다름`); }
  nf++; if (r.structOk) nok++; else if (LIST) lists.push(`${name} 칸 목록(role,r,c,rs,cs) 불일치 py=${P.cells.length} js=${S.cells.length} 공통=${common.length}`);
  r.nf = nf; r.nok = nok; r.bad = bad; r.badCells = badCells.size; r.ms = S.meta.ms_best;
  tot.fields += nf; tot.ok += nok;
  rows.push(r);
}
const pct = (a, b) => (b ? (100 * a / b).toFixed(2) + '%' : '-');
const md = ['| 입력 | 칸 수(py/js) | 칸 목록 | 행높이 | 열폭 | 테두리 | flags | 비교 필드 일치 | 불일치 칸 | 불일치 필드 |', '|---|---|---|---|---|---|---|---|---|---|'];
for (const r of rows) md.push(`| ${r.name} | ${r.ncells.join('/')} | ${r.structOk ? 'O' : 'X'} | ${r.rowh ? 'O' : 'X'} | ${r.colw ? 'O' : 'X'} | ${r.borders ? 'O' : 'X'} | ${r.flags ? 'O' : 'X'} | ${r.nok}/${r.nf} (${pct(r.nok, r.nf)}) | ${r.badCells} | ${Object.entries(r.bad).map(([k, v]) => k + ':' + v).join(' ') || '-'} |`);
md.push(`| **합계** | | | | | | | **${tot.ok}/${tot.fields} (${pct(tot.ok, tot.fields)})** | | |`);
console.log(md.join('\n'));
if (mdIdx > 0) fs.writeFileSync(process.argv[mdIdx + 1], md.join('\n') + '\n');
if (LIST) console.log('\n' + lists.join('\n'));
