// 브라우저 전용 입출력 도우미 (Node 하네스에서는 쓰지 않는다): 이미지 디코드(EXIF 방향 자동 적용), 캔버스 생성, PNG 인코드.
export async function decodeImage(bytes, name = '') {
  const blob = new Blob([bytes]);
  const bmp = await createImageBitmap(blob, { imageOrientation: 'from-image' });   // EXIF 방향 자동 적용(cv2.imread 와 같은 결과 방향)
  const cv = new OffscreenCanvas(bmp.width, bmp.height);
  const ctx = cv.getContext('2d', { willReadFrequently: true });
  ctx.drawImage(bmp, 0, 0);
  const id = ctx.getImageData(0, 0, bmp.width, bmp.height).data;
  const n = bmp.width * bmp.height, data = new Uint8Array(n * 3);
  for (let i = 0; i < n; i++) { data[i * 3] = id[i * 4 + 2]; data[i * 3 + 1] = id[i * 4 + 1]; data[i * 3 + 2] = id[i * 4]; }
  bmp.close?.();
  return { w: bmp.width, h: bmp.height, data };
}
export const createCanvas = (w, h) => new OffscreenCanvas(w, h);
export async function encodePng(w, h, rgba) {
  const c = new OffscreenCanvas(w, h);
  c.getContext('2d').putImageData(new ImageData(new Uint8ClampedArray(rgba.buffer, rgba.byteOffset, rgba.length), w, h), 0, 0);
  const blob = await c.convertToBlob({ type: 'image/png' });
  const buf = new Uint8Array(await blob.arrayBuffer());
  let s = '';
  for (let i = 0; i < buf.length; i += 0x8000) s += String.fromCharCode(...buf.subarray(i, i + 0x8000));
  return btoa(s);
}
