// JPEG 디코더 차이 실험: 원본 jpg 를 jpeg-js 로 디코드해 파이프라인(JS)을 돌리고, Python 덤프(cv2.imread 디코드)와 비교한다.
// 사용: node tools/parity/jpegdiff.mjs <outdir> [이름...]
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
const req = createRequire(path.join(here, '../../web/package.json'));
const jpeg = req('jpeg-js');
const { PNG } = req('pngjs');
const { loadNodeCv } = await import('../../web/src/node_cv.js');
await loadNodeCv();
const { runFront } = await import('../../web/src/front.js');
const { bgrToMat } = await import('../../web/src/cv.js');
const { readJpegOrientation, applyOrientation } = await import('../../web/src/exif.js');
const outdir = path.resolve(process.argv[2]);
const only = new Set(process.argv.slice(3));
const man = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8')).inputs;
const srcOf = (n) => (n.startsWith('s') && n.endsWith('_photo') ? `data/synth/${n}.jpg` : `data/photos/${n}.jpg`);
const root = path.join(here, '../..');
for (const it of man) {
  if (it.kind !== 'photo' || it.name.includes('300dpi')) continue;
  if (only.size && !only.has(it.name)) continue;
  const jp = path.join(root, srcOf(it.name));
  if (!fs.existsSync(jp)) continue;
  const bytes = fs.readFileSync(jp);
  const raw = jpeg.decode(bytes, { useTArray: true, formatAsRGBA: false });
  const n0 = raw.width * raw.height;
  const bgr0 = new Uint8Array(n0 * 3);
  for (let i = 0; i < n0; i++) { bgr0[i * 3] = raw.data[i * 3 + 2]; bgr0[i * 3 + 1] = raw.data[i * 3 + 1]; bgr0[i * 3 + 2] = raw.data[i * 3]; }
  const oriented = applyOrientation({ w: raw.width, h: raw.height, data: bgr0 }, readJpegOrientation(bytes));
  raw.width = oriented.w; raw.height = oriented.h;
  const bgr = oriented.data;
  const n = raw.width * raw.height;
  // 디코드 차이(cv2.imread 결과 PNG 와 비교)
  const ref = PNG.sync.read(fs.readFileSync(path.join(outdir, it.file)));
  let sum = 0, nd = 0, mx = 0;
  for (let i = 0; i < n; i++) {
    let dif = false;
    for (let c = 0; c < 3; c++) { const d = Math.abs(bgr[i * 3 + c] - ref.data[i * 4 + 2 - c]); sum += d; if (d) dif = true; if (d > mx) mx = d; }
    if (dif) nd++;
  }
  const m = bgrToMat({ w: raw.width, h: raw.height, data: bgr });
  const r = runFront(m, 'photo');
  const J = r.info;
  const P = JSON.parse(fs.readFileSync(path.join(outdir, 'py', it.name + '.json'), 'utf8'));
  const gridSame = JSON.stringify(P.grid.cells) === JSON.stringify(J.grid?.cells);
  let dx = 0;
  if (J.grid && P.grid.xs.length === J.grid.xs.length && P.grid.ys.length === J.grid.ys.length) {
    for (const k of ['xs', 'ys']) P.grid[k].forEach((v, i) => { dx = Math.max(dx, Math.abs(v - J.grid[k][i])); });
  } else dx = NaN;
  const emptySame = J.cells && J.cells.length === P.cells.length && J.cells.every((c, i) => c._empty === P.cells[i]._empty);
  const flagsSame = JSON.stringify(P.flags) === JSON.stringify(J.flags);
  console.log([it.name, 'decode 평균절대차', (sum / (n * 3)).toFixed(4), '다른픽셀%', (100 * nd / n).toFixed(2), '최대', mx, '| 격자 cells 동일', gridSame, 'xs/ys 최대차', dx, '빈칸판정 동일', emptySame, 'flags 동일', flagsSame, flagsSame ? '' : JSON.stringify([P.flags.map((f) => f.reason).slice(0, 1), (J.flags || []).map((f) => f.reason).slice(0, 1)])].join(' '));
  for (const k of ['rect', 'flat', 'mask', 'hb', 'vb']) r[k] && r[k].delete();
  m.delete();
}
