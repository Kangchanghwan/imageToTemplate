// OpenCV.js 핸들. 브라우저/Node 모두 setCv(cv)로 주입한다. (Node 는 node_cv.js 가 로드)
let _cv = null;
export function setCv(cv) { _cv = cv; }
export function getCv() {
  if (!_cv) throw new Error('OpenCV.js 가 아직 주입되지 않았다: setCv(cv) 먼저 호출');
  return _cv;
}

// Mat 수명 관리: const T = tracker(); const m = T.add(new cv.Mat()); ... T.free()
export function tracker() {
  const list = [];
  return {
    add(m) { list.push(m); return m; },
    free() { for (const m of list) { try { m.delete(); } catch (e) { /* 이미 해제 */ } } list.length = 0; },
  };
}

// 이미지 컨테이너(Node/브라우저 공용): {w,h,data:Uint8Array BGR 인터리브}
export function bgrToMat(img) {
  const cv = getCv();
  const m = new cv.Mat(img.h, img.w, cv.CV_8UC3);
  m.data.set(img.data);
  return m;
}
export function matToBgr(m) {
  return { w: m.cols, h: m.rows, data: new Uint8Array(m.data) };
}
