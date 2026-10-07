// 3단계 대조(PDF 벡터): JS 로 최종 spec + 단계별 산출물을 만든다. 사용: node tools/parity/pdf_js.mjs <outdir> [이름...]
//   <outdir>/pdf_js/<name>.json (spec), <name>_stages.json (drawings, rawlines, text_lines, underline, fills, mask, images)
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { root, loadPdfEnv, encodePngRgbaB64 } from './node_common.mjs';
await loadPdfEnv();
const { openPdf } = await import(path.join(root, 'web/src/pdf/pdfjs.js'));
const { extractPage, scanFontDescriptors } = await import(path.join(root, 'web/src/pdf/extract.js'));
const V = await import(path.join(root, 'web/src/pdf/pdfvec.js'));
const { runPdfPage, pdfImages } = await import(path.join(root, 'web/src/pdf/pipeline.js'));

const outdir = path.resolve(process.argv[2]);
const only = new Set(process.argv.slice(3));
const dst = path.join(outdir, 'pdf_js');
fs.mkdirSync(dst, { recursive: true });
export const JOBS = [['activity_09', 'data/pdfs/activity_09.pdf'], ['attendance_09', 'data/pdfs/attendance_09.pdf'], ['meal_09', 'data/pdfs/meal_09.pdf'],
  ...Array.from({ length: 12 }, (_, i) => ['s' + String(i).padStart(2, '0'), `data/synth/s${String(i).padStart(2, '0')}.pdf`])];
const REPS = Number(process.env.REPS || 1);
// 추가 입력: out/extra_pdfs/xNN.pdf (runs/ 의 구글 시트 내보내기 등), 스캔 PDF 3개(detect 만)
const extraDir = path.join(outdir, 'extra_pdfs');
if (fs.existsSync(extraDir)) for (const f of fs.readdirSync(extraDir).filter((x) => /^x\d+\.pdf$/.test(x)).sort()) JOBS.push([f.replace('.pdf', ''), path.relative(root, path.join(extraDir, f))]);
for (const n of ['activity', 'attendance', 'meal']) JOBS.push(['scan_' + n + '_09', `data/pdfs/scan_${n}_09.pdf`]);
const detectAll = {};
const { openFirstPage } = await import(path.join(root, 'web/src/pdf/file.js'));
const sha = (u8) => crypto.createHash('sha256').update(u8).digest('hex');
for (const [name, p] of JOBS) {
  if (only.size && !only.has(name)) continue;
  const bytes = new Uint8Array(fs.readFileSync(path.join(root, p)));
  {
    const o = await openFirstPage(bytes);
    detectAll[name] = o.kind;
    if (o.kind !== 'pdf_vector') { console.log(name, 'detect', o.kind); continue; }
  }
  let best = null, spec, stages, tm = {};
  for (let rep = 0; rep < REPS; rep++) {
    const t0 = performance.now();
    const doc = await openPdf(bytes);
    const page = await doc.getPage(1);
    const t1 = performance.now();
    const E = await extractPage(page, { fontDescriptors: scanFontDescriptors(bytes) });
    const t2 = performance.now();
    const images = await pdfImages(E, encodePngRgbaB64);
    spec = runPdfPage(E, { path: p, images });
    const t3 = performance.now();
    const ms = t3 - t0;
    if (best === null || ms < best) { best = ms; tm = { open_ms: Math.round(t1 - t0), extract_ms: Math.round(t2 - t1), pipeline_ms: Math.round(t3 - t2), total_ms: Math.round(ms) }; }
    if (rep === REPS - 1) {
      const lines = V.textLines(E);
      const { ids, ul } = V.underlineSegs(E, lines);
      const mk = V.maskV2(E, ids);
      const stagesMask = { shape: [mk.rows, mk.cols], nz: (await import(path.join(root, 'web/src/cv.js'))).getCv().countNonZero(mk), sha: sha(new Uint8Array(mk.data)) };
      mk.delete();
      stages = { info: { rect: E.rect, ndrawings: E.drawings.length, is_vector: V.isVector(E) }, drawings: E.drawings, glyphs: E.glyphs.map((g) => [g.c, g.ox, g.oy, f(g.size), g.font.name]), text_lines: lines.map((l) => ({ chars: l.chars.map((c) => [c[0], c[1], c[2], c[3], c[4], c[5], c[6]]), y0: l.y0, y1: l.y1, oy: l.oy })),
        underline: { ids: [...ids].sort((a, b) => a - b), ul }, fills: V.fills(E), mask: stagesMask, images: E.images.map((im) => ({ bbox: im.bbox, w: im.img?.width, h: im.img?.height })) };
    }
  }
  spec.meta.timing = tm;
  fs.writeFileSync(path.join(dst, name + '.json'), JSON.stringify(spec));
  fs.writeFileSync(path.join(dst, name + '_stages.json'), JSON.stringify(stages));
  console.log(name, 'cells', spec.cells.length, JSON.stringify(tm));
}
function f(v) { return v; }

fs.writeFileSync(path.join(dst, 'detect.json'), JSON.stringify(detectAll, null, 1));
