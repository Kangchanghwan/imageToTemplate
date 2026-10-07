// pdf.js 핸들 (브라우저/Node 공용): setPdfjs(mod) 로 주입. Node 는 loadNodePdfjs() 가 legacy 빌드를 로드한다.
let _pdfjs = null;
export function setPdfjs(m) { _pdfjs = m; }
export function getPdfjs() {
  if (!_pdfjs) throw new Error('pdf.js 가 주입되지 않았다: setPdfjs(pdfjsLib) 먼저 호출');
  return _pdfjs;
}
// 문서 열기 옵션: 폰트 데이터를 얻기 위해 fontExtraProperties, 코드 실행 금지
export async function openPdf(bytes) {
  const pdfjs = getPdfjs();
  const task = pdfjs.getDocument({ data: bytes instanceof Uint8Array ? bytes.slice() : new Uint8Array(bytes), fontExtraProperties: true, isEvalSupported: false, useSystemFonts: false, verbosity: 0 });
  return task.promise;
}
