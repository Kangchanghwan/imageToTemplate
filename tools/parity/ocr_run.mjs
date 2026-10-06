// 대조 B: JS 파이프라인(자체 보정) + 브라우저 OCR(PP-OCRv5) [+ 의심 칸 서버 재판독]. 입력은 1단계와 같은 26개.
// 사용: node tools/parity/ocr_run.mjs <outdir> <tag> [--server] [--rules=a,b,c] [--conf=0.9] [이름...]
//   결과: <outdir>/ocr_<tag>/<name>.json (spec), <name>.log.json (칸별 특징), summary.json
import fs from 'node:fs';
import path from 'node:path';
import { root, decodePng, encodePngMat, encodeJpegMat, loadPpocr } from './node_common.mjs';
const { loadNodeCv } = await import(path.join(root, 'web/src/node_cv.js'));
await loadNodeCv();
const { runPage } = await import(path.join(root, 'web/src/run.js'));
const { scanNormalize } = await import(path.join(root, 'web/src/front.js'));
const { bgrToMat } = await import(path.join(root, 'web/src/cv.js'));
const { makeClientOcr } = await import(path.join(root, 'web/src/ocr_client.js'));
const { makeSuspect, DEFAULT_PARAMS } = await import(path.join(root, 'web/src/suspect.js'));

const args = process.argv.slice(2);
const outdir = path.resolve(args[0]), tag = args[1];
const flag = (k) => args.find((a) => a.startsWith('--' + k));
const useServer = !!flag('server');
const rules = flag('rules') ? flag('rules').split('=')[1].split(',') : DEFAULT_PARAMS.enabled;
const confMin = flag('conf') ? Number(flag('conf').split('=')[1]) : DEFAULT_PARAMS.confMin;
const only = new Set(args.slice(2).filter((a) => !a.startsWith('--')));
const dst = path.join(outdir, 'ocr_' + tag);
fs.mkdirSync(dst, { recursive: true });
const manifest = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8'));

let server = null;
if (useServer) { const m = await import('./server_mock.mjs'); server = m.serverReread; }
const ppocr = await loadPpocr(Number(process.env.THREADS || 4));
const suspect = makeSuspect({ enabled: rules, confMin });
const summary = [];
for (const it of manifest.inputs) {
  if (only.size && !only.has(it.name)) continue;
  const log = [];
  const ocr = makeClientOcr({ ppocr, suspect: useServer || flag('judge') ? suspect : null, server: useServer ? server : null, encode: encodePngMat, encodeAlt: (m) => encodeJpegMat(m, 90), log, concurrency: 1 });
  if (!useServer && flag('judge')) { /* 판정만(서버 없이): rereadAll 은 server 가 없으면 건너뛰므로 별도 평가 스크립트가 로그의 특징으로 판정한다 */ }
  const img = decodePng(path.join(outdir, it.file));
  const src = bgrToMat(img);
  let input = src, norm = null;
  if (it.kind === 'pdf_scan') { norm = scanNormalize(src); input = norm; }
  const pyDump = JSON.parse(fs.readFileSync(path.join(outdir, 'py', it.name + '.json'), 'utf8'));
  const t0 = performance.now();
  const res = await runPage(input, it.kind, { ocr, sourcePath: pyDump.src, keepRect: !!flag('crops') });
  const ms = performance.now() - t0;
  res.spec.source.kind = it.kind;
  res.spec.meta.ms_total = Math.round(ms);
  res.spec.meta.ocr_client_stat = ocr.stat;
  fs.writeFileSync(path.join(dst, it.name + '.json'), JSON.stringify(res.spec));
  fs.writeFileSync(path.join(dst, it.name + '.log.json'), JSON.stringify(log));
  const nonEmpty = ocr.stat.cells;
  const cellsAll = res.spec.cells.filter((c) => c.role === 'table').length;
  summary.push({ name: it.name, ms: Math.round(ms), cellsAll, ocrCells: nonEmpty, blocks: ocr.stat.blocks, suspects: ocr.stat.suspects, bytes: ocr.stat.bytes, bytesJpeg: ocr.stat.bytesJpeg, byReason: ocr.stat.byReason, changed: ocr.stat.changed, serverMs: Math.round(ocr.stat.serverMs), clientMs: Math.round(ocr.stat.clientMs), timing: res.timing });
  console.log(it.name, 'ms', Math.round(ms), 'ocr cells', nonEmpty, 'blocks', ocr.stat.blocks, 'suspects', ocr.stat.suspects, 'bytes', ocr.stat.bytes);
  src.delete(); norm && norm.delete();
}
fs.writeFileSync(path.join(dst, 'summary.json'), JSON.stringify(summary, null, 1));
