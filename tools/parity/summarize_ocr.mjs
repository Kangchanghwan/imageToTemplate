// ocr_<tag>/summary.json -> 입력별 의심 비율/전송량/시간 표
import fs from 'node:fs'; import path from 'node:path';
const outdir = path.resolve(process.argv[2]); const tag = process.argv[3] || 'srv';
const S = JSON.parse(fs.readFileSync(path.join(outdir, 'ocr_' + tag, 'summary.json'), 'utf8'));
const kb = (b) => (b / 1024).toFixed(0);
const rows = ['| 입력 | OCR 대상(칸+블록) | 의심(서버로 감) | 비율 | 전송 PNG KB | (참고) JPEG q90 KB | 서버 변경 | 클라이언트 OCR ms | 서버 재판독 ms | 전체 ms |', '|---|---|---|---|---|---|---|---|---|---|'];
let T = { n: 0, s: 0, b: 0, j: 0 }, reasons = {};
for (const r of S) {
  const n = r.ocrCells + r.blocks; T.n += n; T.s += r.suspects; T.b += r.bytes; T.j += r.bytesJpeg || 0;
  for (const [k, v] of Object.entries(r.byReason || {})) reasons[k] = (reasons[k] || 0) + v;
  rows.push(`| ${r.name} | ${n} | ${r.suspects} | ${(100 * r.suspects / n).toFixed(1)}% | ${kb(r.bytes)} | ${kb(r.bytesJpeg || 0)} | ${r.changed} | ${r.clientMs} | ${r.serverMs} | ${r.ms} |`);
}
const per = (T.b / S.length / 1024).toFixed(0), perj = (T.j / S.length / 1024).toFixed(0);
rows.push(`| **합계/평균** | ${T.n} | ${T.s} | ${(100 * T.s / T.n).toFixed(1)}% | 장당 평균 ${per} | 장당 평균 ${perj} | | | | |`);
console.log(rows.join('\n'));
console.log('\n규칙별 서버 전송 건수(중복 포함):', JSON.stringify(reasons));
const sz = S.map((r) => r.bytes).sort((a, b) => a - b);
console.log('장당 PNG 바이트 중앙값 KB', kb(sz[Math.floor(sz.length / 2)]), '최대 KB', kb(sz[sz.length - 1]));
// 원본 사진 대비
const orig = { sched: 0 };
fs.writeFileSync(path.join(outdir, 'ocr_' + tag, 'summary.md'), rows.join('\n') + '\n');
