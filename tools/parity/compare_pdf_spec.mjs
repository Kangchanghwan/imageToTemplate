// PDF 벡터 경로: Python spec(out/pdf_py/<name>.json 의 spec) 과 JS spec 을 필드 단위로 비교한다. 텍스트 포함, 허용 오차 0(NUMTOL 로 조정).
// 사용: node tools/parity/compare_pdf_spec.mjs <outdir> <jsdir> [--md file] [--list] [이름...]
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { PNG } from './node_common.mjs';
const args = process.argv.slice(2);
const outdir = path.resolve(args[0]), jsdir = path.resolve(args[1]);
const LIST = args.includes('--list');
const mdIdx = args.indexOf('--md');
const only = new Set(args.slice(2).filter((a, i, arr) => !a.startsWith('--') && arr[i - 1] !== '--md'));
const TOL = Number(process.env.NUMTOL || 0);
const J = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));
const names = fs.readdirSync(path.join(outdir, 'pdf_py')).filter((f) => f.endsWith('.json')).map((f) => f.replace('.json', '')).filter((n) => { const d = J(path.join(outdir, 'pdf_py', n + '.json')); return d.info && d.info.is_vector && fs.existsSync(path.join(outdir, 'pdf_js', n + '.json')); }).sort();
const pixSha = (b64) => { if (!b64) return null; const p = PNG.sync.read(Buffer.from(b64, 'base64')); return crypto.createHash('sha256').update(p.data).digest('hex') + ':' + p.width + 'x' + p.height; };

// 깊은 비교: 스칼라 필드 수/불일치 수와 불일치 경로
function walk(a, b, p, acc) {
  if (typeof a === 'number' && typeof b === 'number') { acc.n++; if (Math.abs(a - b) > TOL) { acc.bad.push([p, a, b]); } return; }
  if (Array.isArray(a) && Array.isArray(b)) {
    if (a.length !== b.length) { acc.n++; acc.bad.push([p + '[len]', a.length, b.length]); }
    for (let i = 0; i < Math.min(a.length, b.length); i++) walk(a[i], b[i], p + '[' + i + ']', acc);
    return;
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    for (const k of new Set([...Object.keys(a), ...Object.keys(b)])) {
      if (!(k in a) || !(k in b)) { acc.n++; acc.bad.push([p + '.' + k, k in a ? 'py만' : '없음', k in b ? 'js만' : '없음']); continue; }
      walk(a[k], b[k], p + '.' + k, acc);
    }
    return;
  }
  acc.n++;
  if (a !== b) acc.bad.push([p, a, b]);
}
const rows = [], listing = [];
let TN = 0, TB = 0;
for (const name of names) {
  if (only.size && !only.has(name)) continue;
  const jf = path.join(jsdir, name + '.json');
  if (!fs.existsSync(jf)) continue;
  const P = J(path.join(outdir, 'pdf_py', name + '.json')).spec, S = J(jf);
  // 정규화: 이미지는 픽셀 해시로, 측정용 meta 제외, 셀은 키로 정렬
  const norm = (s) => {
    const o = JSON.parse(JSON.stringify(s));
    delete o.meta.sec_geom; delete o.meta.timing;
    o.images = (o.images || []).map((im) => ({ ...im, png_b64: undefined, pix: im.png_sha ?? pixSha(im.png_b64), png_sha: undefined }));
    return o;
  };
  const pn = norm(P);
  pn.images.forEach((im, i) => { im.pix = null; });
  const sn = norm(S);
  sn.images.forEach((im) => { im.pix = null; });
  // 이미지 픽셀 비교는 별도: Python 쪽은 pdf_py/<name>_img<k>.png 를 디코드
  const pixRes = [];
  (S.images || []).forEach((im, k) => {
    const pf = path.join(outdir, 'pdf_py', `${name}_img${k}.png`);
    pixRes.push(fs.existsSync(pf) ? pixSha(fs.readFileSync(pf).toString('base64')) === pixSha(im.png_b64) : false);
  });
  const key = (c) => [c.role, c.r, c.c, c.rs, c.cs].join(',');
  const pm = new Map(pn.cells.map((c) => [key(c), c])), sm = new Map(sn.cells.map((c) => [key(c), c]));
  const acc = { n: 0, bad: [] };
  const top = { ...pn, cells: undefined }, tops = { ...sn, cells: undefined };
  walk(top, tops, 'spec', acc);
  const common = [...pm.keys()].filter((k) => sm.has(k));
  acc.n++; if (common.length !== pn.cells.length || common.length !== sn.cells.length) acc.bad.push(['cells(role,r,c,rs,cs)', pn.cells.length, sn.cells.length]);
  const badCells = new Set();
  for (const k of common) { const before = acc.bad.length; walk(pm.get(k), sm.get(k), 'cell[' + k + ']', acc); if (acc.bad.length > before) badCells.add(k); }
  acc.n += pixRes.length; for (const ok of pixRes) if (!ok) acc.bad.push(['image pixels', 'py', 'js']);
  TN += acc.n; TB += acc.bad.length;
  const fieldsBad = {};
  for (const [p] of acc.bad) { const f = p.replace(/^cell\[[^\]]*\]\./, 'cell.').replace(/\[\d+\]/g, '[]'); fieldsBad[f] = (fieldsBad[f] || 0) + 1; }
  rows.push({ name, n: acc.n, bad: acc.bad.length, cells: [pn.cells.length, sn.cells.length], badCells: badCells.size, fieldsBad, img: pixRes.length ? pixRes.every(Boolean) : '-' });
  if (LIST) for (const [p, a, b] of acc.bad) listing.push(`${name} ${p}: py=${JSON.stringify(a)} js=${JSON.stringify(b)}`);
}
const md = ['| 입력 | 칸 수(py/js) | 비교 필드 | 불일치 | 일치율 | 불일치 칸 | 이미지 픽셀 | 불일치 필드 |', '|---|---|---|---|---|---|---|---|'];
for (const r of rows) md.push(`| ${r.name} | ${r.cells.join('/')} | ${r.n} | ${r.bad} | ${(100 * (r.n - r.bad) / r.n).toFixed(2)}% | ${r.badCells} | ${r.img === '-' ? '-' : r.img ? '일치' : '불일치'} | ${Object.entries(r.fieldsBad).map(([k, v]) => k + ':' + v).join(' ') || '-'} |`);
md.push(`| **합계** | | ${TN} | ${TB} | **${(100 * (TN - TB) / TN).toFixed(3)}%** | | | |`);
console.log(md.join('\n'));
if (mdIdx > 0) fs.writeFileSync(args[mdIdx + 1], md.join('\n') + '\n');
if (LIST) console.log('\n' + listing.slice(0, 80).join('\n'));
