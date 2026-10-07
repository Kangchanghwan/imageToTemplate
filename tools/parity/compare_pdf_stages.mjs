// PDF 벡터 경로 중간 산출물 단계별 비교. 사용: node tools/parity/compare_pdf_stages.mjs <outdir> [--md file]
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { PNG } from './node_common.mjs';
const args = process.argv.slice(2);
const outdir = path.resolve(args[0]);
const mdIdx = args.indexOf('--md');
const J = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));
const names = fs.readdirSync(path.join(outdir, 'pdf_py')).filter((f) => f.endsWith('.json')).map((f) => f.replace('.json', '')).filter((n) => { const d = J(path.join(outdir, 'pdf_py', n + '.json')); return d.info && d.info.is_vector && fs.existsSync(path.join(outdir, 'pdf_js', n + '.json')); }).sort();
const eq = (a, b) => JSON.stringify(a) === JSON.stringify(b);
const f32 = Math.fround;
const rows = [];
for (const name of names) {
  const jf = path.join(outdir, 'pdf_js', name + '_stages.json');
  if (!fs.existsSync(jf)) continue;
  const P = J(path.join(outdir, 'pdf_py', name + '.json')), S = J(jf);
  const r = { name };
  // 드로잉: 종류/색(hex)/선폭/항목 수/좌표. 're' 의 x1,y1 은 float32 한 칸(x+w 반올림) 차이를 허용하고 건수를 센다
  let dn = P.drawings.length === S.drawings.length ? 0 : 1, dRe = 0, dBad = 0, maxd = 0;
  const hx = (c) => (c ? c.map((v) => Math.round(v * 255)).join(',') : null);
  P.drawings.forEach((d, i) => {
    const e = S.drawings[i]; if (!e) return;
    if (d.type !== e.type || hx(d.color) !== hx(e.color) || hx(d.fill) !== hx(e.fill) || (d.width ?? null) !== (e.width ?? null) || d.items.length !== e.items.length) { dBad++; return; }
    d.items.forEach((it, k) => {
      const t = e.items[k];
      if (it[0] !== t[0]) { dBad++; return; }
      for (let q = 1; q < it.length; q++) { const df = Math.abs(it[q] - t[q]); if (df > 0) { if (it[0] === 're') { dRe++; maxd = Math.max(maxd, df); } else dBad++; } }
    });
  });
  r.drawings = { n: P.drawings.length, bad: dBad + dn, re_ulp: dRe, re_maxd: maxd };
  // 글리프(원점/글자)
  const pg = []; for (const l of P.rawlines) for (const s of l.spans) for (const c of s.chars) pg.push([c[0], c[1][0], c[1][1]]);
  let gb = pg.length === S.glyphs.length ? 0 : 1;
  pg.forEach((g, i) => { const t = S.glyphs[i]; if (t && (g[0] !== t[0] || g[1] !== t[1] || g[2] !== t[2])) gb++; });
  r.glyphs = { n: pg.length, bad: gb };
  // 텍스트 줄
  let lb = P.text_lines.length === S.text_lines.length ? 0 : 1, nch = 0;
  P.text_lines.forEach((l, i) => { const t = S.text_lines[i]; if (!t) return; nch += l.chars.length; if (!eq(l, t)) lb++; });
  r.lines = { n: P.text_lines.length, chars: nch, bad: lb };
  r.underline = eq(P.underline, S.underline);
  r.fills = { n: P.fills.length, bad: eq(P.fills, S.fills) ? 0 : 1 };
  r.mask = { shape: eq(P.mask.shape, S.mask.shape), nz: [P.mask.nz, S.mask.nz], sha: P.mask.sha === S.mask.sha };
  r.images = { n: P.images.length, bbox: eq(P.images.map((i) => i.bbox.map(f32)), S.images.map((i) => i.bbox)) };
  r.info = eq(P.info.rect, S.info.rect) && P.info.ndrawings === S.info.ndrawings && P.info.is_vector === S.info.is_vector;
  rows.push(r);
}
const md = ['| 입력 | 드로잉 수/불일치(re ulp) | 글리프 수/불일치 | 텍스트 줄 수/글자 수/불일치 | 밑줄 | 채움 | 마스크(shape, nz py/js, 해시) | 이미지 bbox | 페이지/is_vector |', '|---|---|---|---|---|---|---|---|---|'];
for (const r of rows) md.push(`| ${r.name} | ${r.drawings.n}/${r.drawings.bad} (${r.drawings.re_ulp}) | ${r.glyphs.n}/${r.glyphs.bad} | ${r.lines.n}/${r.lines.chars}/${r.lines.bad} | ${r.underline ? '일치' : '불일치'} | ${r.fills.n}/${r.fills.bad} | ${r.mask.shape ? 'O' : 'X'} ${r.mask.nz.join('/')} ${r.mask.sha ? '해시 일치' : '해시 불일치'} | ${r.images.n ? (r.images.bbox ? '일치' : '불일치') : '-'} | ${r.info ? '일치' : '불일치'} |`);
console.log(md.join('\n'));
if (mdIdx > 0) fs.writeFileSync(args[mdIdx + 1], md.join('\n') + '\n');
