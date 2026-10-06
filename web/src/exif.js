// JPEG EXIF Orientation 읽기/적용. cv2.imread 는 기본으로 EXIF 방향을 적용한다(IMREAD_COLOR).
// 브라우저에서는 createImageBitmap(blob)/<img> 가 자동 적용하므로(imageOrientation: 'from-image') 이 모듈은 Node 하네스/폴백용.
export function readJpegOrientation(u8) {
  if (u8[0] !== 0xff || u8[1] !== 0xd8) return 1;
  let p = 2;
  while (p + 4 < u8.length) {
    if (u8[p] !== 0xff) break;
    const marker = u8[p + 1];
    const len = (u8[p + 2] << 8) | u8[p + 3];
    if (marker === 0xe1 && u8[p + 4] === 0x45 && u8[p + 5] === 0x78) {   // 'Ex'
      const t = p + 10;   // TIFF 헤더 시작
      const le = u8[t] === 0x49;
      const rd16 = (o) => (le ? u8[o] | (u8[o + 1] << 8) : (u8[o] << 8) | u8[o + 1]);
      const rd32 = (o) => (le ? (u8[o] | (u8[o + 1] << 8) | (u8[o + 2] << 16) | (u8[o + 3] << 24)) >>> 0 : ((u8[o] << 24) | (u8[o + 1] << 16) | (u8[o + 2] << 8) | u8[o + 3]) >>> 0);
      const ifd = t + rd32(t + 4);
      const n = rd16(ifd);
      for (let i = 0; i < n; i++) {
        const e = ifd + 2 + i * 12;
        if (rd16(e) === 0x0112) return rd16(e + 8);
      }
      return 1;
    }
    if (marker === 0xda) break;
    p += 2 + len;
  }
  return 1;
}

// img: {w,h,data(BGR 인터리브)} -> 방향 적용된 새 img
export function applyOrientation(img, o) {
  if (!o || o === 1) return img;
  const { w, h, data } = img;
  const swap = o >= 5;
  const W = swap ? h : w, H = swap ? w : h;
  const out = new Uint8Array(W * H * 3);
  for (let y = 0; y < h; y++) {
    for (let x = 0; x < w; x++) {
      let nx, ny;
      switch (o) {
        case 2: nx = w - 1 - x; ny = y; break;
        case 3: nx = w - 1 - x; ny = h - 1 - y; break;
        case 4: nx = x; ny = h - 1 - y; break;
        case 5: nx = y; ny = x; break;
        case 6: nx = h - 1 - y; ny = x; break;
        case 7: nx = h - 1 - y; ny = w - 1 - x; break;
        case 8: nx = y; ny = w - 1 - x; break;
        default: nx = x; ny = y;
      }
      const s = (y * w + x) * 3, d = (ny * W + nx) * 3;
      out[d] = data[s]; out[d + 1] = data[s + 1]; out[d + 2] = data[s + 2];
    }
  }
  return { w: W, h: H, data: out };
}
