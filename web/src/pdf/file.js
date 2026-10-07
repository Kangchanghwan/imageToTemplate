// 파일 진입점의 PDF 판별/분기: detect, 첫 페이지 처리. (다중 페이지 PDF 는 Python convert 와 같이 첫 페이지만 처리한다.)
import { openPdf } from './pdfjs.js';
import { extractPage, scanFontDescriptors } from './extract.js';
import { isVector } from './pdfvec.js';

export const isPdfBytes = (bytes, name = '') => (bytes.length >= 5 && bytes[0] === 0x25 && bytes[1] === 0x50 && bytes[2] === 0x44 && bytes[3] === 0x46) || /\.pdf$/i.test(name);

// convert.detect: 'pdf_vector' | 'pdf_scan'  (이미지는 호출측에서 'photo')
export async function openFirstPage(bytes) {
  const doc = await openPdf(bytes);
  const page = await doc.getPage(1);
  const E = await extractPage(page, { fontDescriptors: scanFontDescriptors(bytes) });
  return { doc, page, E, pageCount: doc.numPages, kind: isVector(E) ? 'pdf_vector' : 'pdf_scan' };
}
