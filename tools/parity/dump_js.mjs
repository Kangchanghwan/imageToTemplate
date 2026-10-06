// 대조용 JS 덤프: dump_py.py 와 같은 JSON 을 만든다.
// 사용: node tools/parity/dump_js.mjs <outdir> [이름...]   (outdir 에 inputs/, manifest.json 이 있어야 함)
import fs from 'node:fs';
import path from 'node:path';
import crypto from 'node:crypto';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const here = path.dirname(fileURLToPath(import.meta.url));
const webReq = createRequire(path.join(here, '../../web/package.json'));
const { PNG } = webReq('pngjs');
const { loadNodeCv } = await import('../../web/src/node_cv.js');
const cv = await loadNodeCv();
const { runFront, scanNormalize } = await import('../../web/src/front.js');
const { bgrToMat } = await import('../../web/src/cv.js');

const outdir = path.resolve(process.argv[2]);
const only = new Set(process.argv.slice(3));
fs.mkdirSync(path.join(outdir, 'js'), { recursive: true });
const manifest = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8'));

export function decodePngBgr(file) {
  const png = PNG.sync.read(fs.readFileSync(file));
  const n = png.width * png.height;
  const data = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) { data[i * 3] = png.data[i * 4 + 2]; data[i * 3 + 1] = png.data[i * 4 + 1]; data[i * 3 + 2] = png.data[i * 4]; }
  return { w: png.width, h: png.height, data };
}
function writePngBgr(file, mat) {
  const png = new PNG({ width: mat.cols, height: mat.rows });
  const d = mat.data, n = mat.cols * mat.rows;
  for (let i = 0; i < n; i++) { png.data[i * 4] = d[i * 3 + 2]; png.data[i * 4 + 1] = d[i * 3 + 1]; png.data[i * 4 + 2] = d[i * 3]; png.data[i * 4 + 3] = 255; }
  fs.writeFileSync(file, PNG.sync.write(png, { colorType: 2 }));
}
const sha = (u8) => crypto.createHash('sha256').update(u8).digest('hex');

const reps = Number(process.env.REPS || 1);
const summary = [];
for (const it of manifest.inputs) {
  if (only.size && !only.has(it.name)) continue;
  const img = decodePngBgr(path.join(outdir, it.file));
  let best = null, last = null;
  for (let rep = 0; rep < reps; rep++) {
    const src = bgrToMat(img);
    const t0 = performance.now();
    let input = src, norm = null;
    if (it.kind === 'pdf_scan') { norm = scanNormalize(src); input = norm; }
    const r = runFront(input, it.kind);
    const ms = performance.now() - t0;
    if (best === null || ms < best) best = ms;
    if (rep < reps - 1) { for (const k of ['rect', 'flat', 'fgray', 'mask', 'hb', 'vb']) r[k] && r[k].delete(); src.delete(); norm && norm.delete(); continue; }
    last = { r, src, norm, ms };
  }
  const { r, src, norm } = last;
  const d = r.info;
  d.name = it.name; d.input_shape = [(norm ?? src).rows, (norm ?? src).cols, 3];
  d.input_sha = sha(new Uint8Array((norm ?? src).data));
  if (it.kind === 'pdf_scan') d.input300_shape = [src.rows, src.cols, 3];
  d.rect_sha = sha(new Uint8Array(r.rect.data));
  d.mask = { nz: cv.countNonZero(r.mask), sha: sha(new Uint8Array(r.mask.data)), hb_nz: cv.countNonZero(r.hb), hb_sha: sha(new Uint8Array(r.hb.data)), vb_nz: cv.countNonZero(r.vb), vb_sha: sha(new Uint8Array(r.vb.data)) };
  if (r.flat) d.flat_sha = sha(new Uint8Array(r.flat.data));
  d.timing_ms = r.timing; d.sec = Math.round(best) / 1000; d.ms_best = Math.round(best);
  fs.writeFileSync(path.join(outdir, 'js', it.name + '.json'), JSON.stringify(d));
  writePngBgr(path.join(outdir, 'js', it.name + '_rect.png'), r.rect);
  if (r.flat) writePngBgr(path.join(outdir, 'js', it.name + '_flat.png'), r.flat);
  console.log(it.name, it.kind, d.rect_shape.join('x'), d.error || '', Math.round(best) + 'ms');
  for (const k of ['rect', 'flat', 'fgray', 'mask', 'hb', 'vb']) r[k] && r[k].delete();
  src.delete(); norm && norm.delete();
}
