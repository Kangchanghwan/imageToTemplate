// Node 하네스 공용: PNG 입출력, ort 로딩, 서버 터널 호출
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { fileURLToPath, pathToFileURL } from 'node:url';
const here = path.dirname(fileURLToPath(import.meta.url));
export const root = path.join(here, '../..');
const req = createRequire(path.join(root, 'web/package.json'));
export const { PNG } = req('pngjs');
export const jpeg = req('jpeg-js');

export function decodePng(file) {
  const png = PNG.sync.read(fs.readFileSync(file));
  const n = png.width * png.height, data = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) { data[i * 3] = png.data[i * 4 + 2]; data[i * 3 + 1] = png.data[i * 4 + 1]; data[i * 3 + 2] = png.data[i * 4]; }
  return { w: png.width, h: png.height, data };
}
export function encodePngMat(mat) {   // BGR Mat -> PNG bytes
  const png = new PNG({ width: mat.cols, height: mat.rows });
  const d = mat.data, n = mat.cols * mat.rows;
  for (let i = 0; i < n; i++) { png.data[i * 4] = d[i * 3 + 2]; png.data[i * 4 + 1] = d[i * 3 + 1]; png.data[i * 4 + 2] = d[i * 3]; png.data[i * 4 + 3] = 255; }
  return new Uint8Array(PNG.sync.write(png, { colorType: 2 }));
}
export function encodeJpegMat(mat, q = 90) {
  const n = mat.cols * mat.rows, d = mat.data, rgba = Buffer.alloc(n * 4);
  for (let i = 0; i < n; i++) { rgba[i * 4] = d[i * 3 + 2]; rgba[i * 4 + 1] = d[i * 3 + 1]; rgba[i * 4 + 2] = d[i * 3]; rgba[i * 4 + 3] = 255; }
  return new Uint8Array(jpeg.encode({ data: rgba, width: mat.cols, height: mat.rows }, q).data);
}
export async function loadPpocr(threads = 4) {
  const ort = await import(pathToFileURL(req.resolve('onnxruntime-web')).href);
  const { createPpocr } = await import(path.join(root, 'web/src/ppocr.js'));
  const M = path.join(root, 'web/models');
  return createPpocr({ ort, recModel: fs.readFileSync(path.join(M, 'rec_ko.onnx')), detModel: fs.readFileSync(path.join(M, 'det_mobile.onnx')), dictText: fs.readFileSync(path.join(M, 'dict_ko.txt'), 'utf8'), threads });
}

export function encodePngRgbaB64(w, h, rgba) {
  const p = new PNG({ width: w, height: h });
  p.data = Buffer.from(rgba.buffer, rgba.byteOffset, rgba.length);
  return PNG.sync.write(p).toString('base64');
}
export async function loadPdfEnv() {
  const { loadNodeCv } = await import(path.join(root, 'web/src/node_cv.js'));
  await loadNodeCv();
  const { loadNodePdfjs } = await import(path.join(root, 'web/src/pdf/node_pdfjs.js'));
  await loadNodePdfjs();
}
