// Node 전용: pdfjs-dist legacy 빌드 로드 후 setPdfjs
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';
import { setPdfjs } from './pdfjs.js';
const require = createRequire(import.meta.url);
export async function loadNodePdfjs() {
  const p = require.resolve('pdfjs-dist/legacy/build/pdf.mjs');
  const m = await import(pathToFileURL(p).href);
  setPdfjs(m);
  return m;
}
