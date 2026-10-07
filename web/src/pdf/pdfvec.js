// sheetparser/pdfvec.py 이식. 입력 E 는 extract.js extractPage() 결과(PyMuPDF 의 drawings/rawdict/texttrace 대응).
import { getCv, tracker } from '../cv.js';
import { pyRound } from '../npy.js';

const f32 = Math.fround;
export const MASK_PPM = 20;
export const PT_MM = 25.4 / 72;

// ---------------- stext 줄 구성 (MuPDF stext-device 의 줄 분리 규칙을 데이터로 맞춘 것) ----------------
// 같은 줄: 방향이 같고 |세로 이동| <= LINE_DIST*size, 가로 간격(이전 글자 끝 -> 새 원점)/size 가 [SPACE_NEG, SPACE_MAX] 안.
// (15개 PDF, 2,997 글자쌍에서 같은 줄 간격 -0.063~0.773, 새 줄 간격 >=0.85 또는 <=-2.3, 같은 줄 |dy|<=0.563 size, 새 줄 |dy|>=0.959 size)
export const STEXT = { SPACE_MAX: 0.8, SPACE_NEG: -0.15, LINE_DIST: 0.9 };

function charGeom(g) {
  // MuPDF: ascender/descender 합이 1 보다 작으면 합이 1 이 되게 늘린다 (Gulim .858/-.141 -> .85886/-.14114)
  let a = g.font.ascender, d = g.font.descender;
  const s = f32(a - d);
  if (s < 1) { a = f32(a / s); d = f32(d / s); }
  return { y0: f32(g.oy - f32(a * g.size)), y1: f32(g.oy - f32(d * g.size)) };
}

const fontBold = (g) => g.font.bold;
const colorInt = (rgb) => (rgb[0] << 16) | (rgb[1] << 8) | rgb[2];

export function rawLines(E) {
  const lines = [];
  let cur = null, prev = null;
  for (const g of E.glyphs) {
    const adv = f32(g.w0 * g.size);
    let newLine = true;
    if (cur && prev) {
      const sameDir = Math.abs(g.dir[0] - prev.dir[0]) < 1e-3 && Math.abs(g.dir[1] - prev.dir[1]) < 1e-3;
      const spacing = (g.ox - (prev.ox + prev.adv)) / g.size;
      const dy = (g.oy - prev.oy) / g.size;
      newLine = !(sameDir && Math.abs(dy) <= STEXT.LINE_DIST && spacing <= STEXT.SPACE_MAX && spacing >= STEXT.SPACE_NEG);
    }
    const geo = charGeom(g);
    const ch = { c: g.c, x0: g.ox, x1: f32(g.ox + adv), oy: g.oy, size: g.size, font: g.font, color: colorInt(g.color), bold: fontBold(g), y0: geo.y0, y1: geo.y1, adv, ox: g.ox, dir: g.dir, mode: g.mode };
    if (newLine) { cur = { chars: [ch] }; lines.push(cur); } else cur.chars.push(ch);
    prev = ch;
  }
  // 스팬: 폰트/크기/색이 바뀌면 나눈다
  for (const l of lines) {
    const spans = [];
    let sp = null;
    for (const ch of l.chars) {
      if (!sp || sp.font !== ch.font || sp.size !== ch.size || sp.color !== ch.color) { sp = { font: ch.font, size: ch.size, color: ch.color, chars: [] }; spans.push(sp); }
      sp.chars.push(ch);
    }
    for (const s of spans) {
      s.origin = [s.chars[0].ox, s.chars[0].oy];
      s.y0 = Math.min(...s.chars.map((c) => c.y0)); s.y1 = Math.max(...s.chars.map((c) => c.y1));
      s.x0 = Math.min(...s.chars.map((c) => c.x0)); s.x1 = Math.max(...s.chars.map((c) => c.x1));
    }
    l.spans = spans;
  }
  return lines;
}

// ---------------- fake bold ----------------
// texttrace type 1: 글자 외곽선을 그린 글자(렌더 모드 1,2,5,6)의 원점
export function fakeBoldKeys(E) {
  const keys = new Set();
  for (const g of E.glyphs) if ([1, 2, 5, 6].includes(g.mode)) keys.add(pyRound(g.ox * 4) + ',' + pyRound(g.oy * 4));
  return keys;
}
function isFake(keys, ox, oy) {
  const x = pyRound(ox * 4), y = pyRound(oy * 4);
  for (let dx = -1; dx <= 1; dx++) for (let dy = -1; dy <= 1; dy++) if (keys.has((x + dx) + ',' + (y + dy))) return true;
  return false;
}

const isWs = (c) => /^\s*$/.test(c);   // Python str.strip() 가 비는 글자
const rgbHexInt = (c) => '#' + (c >>> 0).toString(16).padStart(6, '0');

// 줄: {chars:[[c,x0,x1,size,bold,color(int),font]], y0,y1,oy}
export function textLines(E) {
  const fk = fakeBoldKeys(E);
  const out = [];
  for (const l of rawLines(E)) {
    const chars = [];
    let y0 = 1e9, y1 = -1e9, oy = null;
    for (const sp of l.spans) {
      for (const ch of sp.chars) chars.push([ch.c, ch.x0, ch.x1, sp.size, ch.bold || isFake(fk, ch.ox, ch.oy), sp.color, ch.font.name]);
      if (sp.chars.some((c) => !isWs(c.c))) { y0 = Math.min(y0, sp.y0); y1 = Math.max(y1, sp.y1); if (oy === null) oy = sp.origin[1]; }
    }
    if (!chars.some((c) => !isWs(c[0]))) continue;
    out.push({ chars, y0, y1, oy });
  }
  return out;
}

function seg(chars, y0, y1, oy) {
  const ink = chars.filter((c) => !isWs(c[0]));
  const txt = chars.map((c) => c[0]).join('').replace(/^\s+|\s+$/g, '');
  const nb = ink.filter((c) => c[4]).length;
  const fonts = {};
  for (const c of ink) fonts[c[6]] = (fonts[c[6]] || 0) + 1;
  // color: 가장 많은 색(동률이면 Python max(set, key) 의 집합 순서에 의존해 정의되지 않음: 먼저 나온 것)
  const cnt = new Map();
  for (const c of ink) cnt.set(c[5], (cnt.get(c[5]) || 0) + 1);
  let col = null, best = -1;
  for (const [k, v] of cnt) if (v > best) { best = v; col = k; }
  return { text: txt, x0: Math.min(...ink.map((c) => c[1])), x1: Math.max(...ink.map((c) => c[2])), y0, y1, oy, size: Math.max(...ink.map((c) => c[3])), bold: nb * 2 > ink.length, color: rgbHexInt(col), fonts };
}

export function splitSegments(line, minSpaces = 3) {
  const segs = [];
  let cur = [], sp = 0;
  for (const c of line.chars) {
    if (c[0] === ' ') { sp++; cur.push(c); continue; }
    if (cur.length && sp >= minSpaces) {
      const sg = cur.slice();
      while (sg.length && sg[sg.length - 1][0] === ' ') sg.pop();
      if (sg.some((x) => !isWs(x[0]))) segs.push(seg(sg, line.y0, line.y1, line.oy));
      cur = [];
    }
    sp = 0;
    cur.push(c);
  }
  if (cur.some((x) => !isWs(x[0]))) segs.push(seg(cur, line.y0, line.y1, line.oy));
  return segs;
}
export const wholeLine = (line) => seg(line.chars, line.y0, line.y1, line.oy);

export function underlineSegs(E, lines) {
  const ids = new Set(), ul = [];
  E.drawings.forEach((d, i) => {
    if (d.color === null || d.items.length !== 1 || d.items[0][0] !== 'l') return;
    const [, px, py, qx, qy] = d.items[0];
    if (Math.abs(py - qy) > 0.5) return;
    const x0 = Math.min(px, qx), x1 = Math.max(px, qx), y = py;
    for (const l of lines) {
      const h = l.y1 - l.y0;
      const ink = l.chars.filter((c) => !isWs(c[0]));
      const lx0 = Math.min(...ink.map((c) => c[1])), lx1 = Math.max(...ink.map((c) => c[2]));
      if (l.y0 + 0.6 * h <= y && y <= l.y1 + 1.5 && x1 > lx0 - 1 && x0 < lx1 + 1) { ids.add(i); ul.push([x0, x1, y]); break; }
    }
  });
  return { ids, ul };
}
export function isUnderlined(sg, ul) {
  let cov = 0;
  for (const [x0, x1, y] of ul) if (sg.y0 + 0.6 * (sg.y1 - sg.y0) <= y && y <= sg.y1 + 1.5) cov += Math.max(0, Math.min(x1, sg.x1) - Math.max(x0, sg.x0));
  return cov >= 0.6 * (sg.x1 - sg.x0);
}

// ---------------- 마스크 ----------------
// mask_v2(page, skip_ids) / vec_mask(page) (skip 없음). 반환 cv.Mat CV_8UC1
export function maskV2(E, skip = new Set(), ppm = MASK_PPM) {
  const cv = getCv();
  const s = ppm * PT_MM;
  const W = pyRound(E.rect[2] * s), H = pyRound(E.rect[3] * s);
  const m = cv.Mat.zeros(H, W, cv.CV_8UC1);
  const P = (x, y) => new cv.Point(pyRound(x * s), pyRound(y * s));
  const white = new cv.Scalar(255);
  E.drawings.forEach((d, i) => {
    if (skip.has(i)) return;
    const w = d.width || 0;
    const th = Math.max(1, pyRound(w * s) - 2);   // cv2 선은 지정값보다 ~2px 굵게 그려짐
    for (const it of d.items) {
      if (it[0] === 'l' && d.color !== null) cv.line(m, P(it[1], it[2]), P(it[3], it[4]), white, th, cv.LINE_8, 0);
      else if (it[0] === 're') {
        const [, x0, y0, x1, y1] = it;
        if (d.color !== null) cv.rectangle(m, P(x0, y0), P(x1, y1), white, th, cv.LINE_8, 0);
        else if (d.fill !== null && Math.min(x1 - x0, y1 - y0) * PT_MM < 1.2) cv.rectangle(m, P(x0, y0), P(x1, y1), white, -1, cv.LINE_8, 0);
      }
    }
  });
  return m;
}
export const vecMask = (E, ppm = MASK_PPM) => maskV2(E, new Set(), ppm);

// ---------------- 채움/이미지 ----------------
export const rgbHex = (c) => '#' + c.map((v) => pyRound(v * 255).toString(16).padStart(2, '0')).join('');
export function fills(E) {
  const out = [];
  for (const d of E.drawings) {
    const f = d.fill;
    if (f === null || Math.min(...f) > 0.985 || d.color !== null) continue;
    out.push([d.rect[0], d.rect[1], d.rect[2], d.rect[3], rgbHex(f)]);
  }
  return out;
}

// is_vector: 드로잉 4개 이상 + 글자(단어) 1개 이상
export function isVector(E) {
  return E.drawings.length >= 4 && E.glyphs.some((g) => !isWs(g.c));
}

// PV.spans (v1): get_text("dict") 스팬 중 공백뿐이 아닌 것
export function spansV1(E) {
  const out = [];
  for (const l of rawLines(E)) {
    for (const sp of l.spans) {
      const text = sp.chars.map((c) => c.c).join('');
      if (isWs(text)) continue;
      const fn = sp.font.name.toLowerCase();
      const bold = sp.font.bold || fn.includes('bold') || fn.endsWith('b');
      out.push({ text, bbox: [sp.x0, sp.y0, sp.x1, sp.y1], size: sp.size, bold, origin: sp.origin });
    }
  }
  return out;
}
