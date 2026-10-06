// 대조 A: Python 의 OCR 결과(spec_py/*_ocr.json)를 주입해 JS 로 최종 spec 을 만든다.
// 사용: node tools/parity/spec_js.mjs <outdir> <i|ii> [이름...]
//   i  = Python 보정 PNG(out/py/<name>_rect.png) 고정 입력 (보정 단계 생략)
//   ii = JS 자체 보정 (입력 PNG -> 용지 검출 ... 전부)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const { PNG } = createRequire(path.join(here, '../../web/package.json'))('pngjs');
const { loadNodeCv } = await import('../../web/src/node_cv.js');
await loadNodeCv();
const { runPage } = await import('../../web/src/run.js');
const { scanNormalize } = await import('../../web/src/front.js');
const { bgrToMat } = await import('../../web/src/cv.js');

const outdir = path.resolve(process.argv[2]);
const mode = process.argv[3];
const only = new Set(process.argv.slice(4));
const dst = path.join(outdir, 'spec_js_' + mode);
fs.mkdirSync(dst, { recursive: true });

function decode(file) {
  const png = PNG.sync.read(fs.readFileSync(file));
  const n = png.width * png.height, data = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) { data[i * 3] = png.data[i * 4 + 2]; data[i * 3 + 1] = png.data[i * 4 + 1]; data[i * 3 + 2] = png.data[i * 4]; }
  return { w: png.width, h: png.height, data };
}
const manifest = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8'));
const REPS = Number(process.env.REPS || 1);
for (const it of manifest.inputs) {
  if (only.size && !only.has(it.name)) continue;
  const rec = JSON.parse(fs.readFileSync(path.join(outdir, 'spec_py', it.name + '_ocr.json'), 'utf8'));
  const pyDump = JSON.parse(fs.readFileSync(path.join(outdir, 'py', it.name + '.json'), 'utf8'));
  const cellMap = new Map(rec.cells.map(([r, c, t]) => [r + ',' + c, t]));
  const used = new Set();
  const ocr = {
    readCells: async (items) => items.map((it2) => ({ text: cellMap.get(it2.r + ',' + it2.c) ?? '' })),
    readBlocks: async (items) => items.map((_, k) => rec.blocks[k]?.text ?? ''),
    readLines: async (items) => items.map((it2) => {
      const j = rec.breaks.findIndex((b, bi) => !used.has(bi) && b.text === it2.cell.text);
      if (j < 0) return null;
      if (it2.k === 0) { used.add(j); it2._j = j; }
      const bj = rec.breaks.findIndex((b, bi) => b.text === it2.cell.text && (used.has(bi) || bi === j));
      return rec.breaks[bj >= 0 ? bj : j].lines[it2.k] ?? null;
    }),
  };
  // readLines: 칸 단위로 같은 break 기록을 가리키도록 단순화
  ocr.readLines = async (items) => {
    const out = [];
    const pick = new Map();
    for (const it2 of items) {
      const key = it2.cell.r + ',' + it2.cell.c;
      if (!pick.has(key)) {
        const j = rec.breaks.findIndex((b, bi) => !used.has(bi) && b.text === it2.cell.text);
        if (j >= 0) used.add(j);
        pick.set(key, j);
      }
      const j = pick.get(key);
      out.push(j < 0 ? null : (rec.breaks[j].lines[it2.k] ?? null));
    }
    return out;
  };
  const img = decode(path.join(outdir, it.file));
  let best = null, res = null;
  for (let rep = 0; rep < REPS; rep++) {
    used.clear();
    const src = bgrToMat(img);
    let opts = { ocr, sourcePath: pyDump.src };
    let input = src, norm = null, fixedMat = null;
    const t0 = performance.now();
    if (mode === 'i') {
      const rimg = decode(path.join(outdir, 'py', it.name + '_rect.png'));
      fixedMat = bgrToMat(rimg);
      const fl = pyDump.flags.filter((f) => !f.reason.startsWith('outer_rows_cols_trimmed') && !f.reason.startsWith('table_clipped_left'));
      opts.fixed = { img: fixedMat, pgMm: pyDump.pg_mm, flags: fl };
    }
    if (it.kind === 'pdf_scan' && mode !== 'i') { norm = scanNormalize(src); input = norm; }
    res = await runPage(input, it.kind, opts);
    const ms = performance.now() - t0;
    if (best === null || ms < best) best = ms;
    src.delete(); norm && norm.delete(); fixedMat && fixedMat.delete();
  }
  res.spec.source.kind = it.kind;
  res.spec.meta.ms_best = Math.round(best);
  fs.writeFileSync(path.join(dst, it.name + '.json'), JSON.stringify(res.spec));
  console.log(it.name, mode, 'cells', res.spec.cells.length, Math.round(best) + 'ms');
}
