// pdf.js 연산자 목록을 해석해 PyMuPDF(MuPDF) 의 get_drawings / get_text(rawdict) / get_texttrace / get_image_info 에 해당하는 데이터를 만든다.
// 좌표는 MuPDF 와 같게 페이지 좌상단 원점, pt 단위, float32 연산(Math.fround)으로 맞춘다.
import { getPdfjs } from './pdfjs.js';

const f32 = Math.fround;
const K001 = f32(0.001);   // MuPDF 의 0.001f

// ---- MuPDF float32 행렬 (fz_concat, fz_transform_point) ----
export const IDENT = [1, 0, 0, 1, 0, 0];
export function concat(one, two) {
  return [
    f32(f32(one[0] * two[0]) + f32(one[1] * two[2])),
    f32(f32(one[0] * two[1]) + f32(one[1] * two[3])),
    f32(f32(one[2] * two[0]) + f32(one[3] * two[2])),
    f32(f32(one[2] * two[1]) + f32(one[3] * two[3])),
    f32(f32(f32(one[4] * two[0]) + f32(one[5] * two[2])) + two[4]),
    f32(f32(f32(one[4] * two[1]) + f32(one[5] * two[3])) + two[5]),
  ];
}
export function tp(x, y, m) {   // fz_transform_point
  return [f32(f32(f32(x * m[0]) + f32(y * m[2])) + m[4]), f32(f32(f32(x * m[1]) + f32(y * m[3])) + m[5])];
}
const preTranslate = (m, tx, ty) => [m[0], m[1], m[2], m[3], f32(f32(f32(tx * m[0]) + f32(ty * m[2])) + m[4]), f32(f32(f32(tx * m[1]) + f32(ty * m[3])) + m[5])];
const expansion = (m) => f32(Math.sqrt(Math.abs(f32(f32(m[0] * m[3]) - f32(m[1] * m[2])))));

const hexToRgb = (h) => (typeof h === 'string' && h[0] === '#' ? [parseInt(h.slice(1, 3), 16), parseInt(h.slice(3, 5), 16), parseInt(h.slice(5, 7), 16)] : [0, 0, 0]);
const toUnit = (b) => f32(b / 255);   // 바이트 -> MuPDF float 색

// ---- 폰트 디스크립터 (MuPDF 는 FontDescriptor 의 Ascent/Descent/1000 을 쓴다) ----
export function scanFontDescriptors(bytes) {
  const s = new TextDecoder('latin1').decode(bytes);
  const out = new Map();
  for (const obj of s.split('endobj')) {
    if (!obj.includes('/FontDescriptor')) continue;
    const name = /\/FontName\s*\/([^\s/<>\[\]()]+)/.exec(obj);
    const asc = /\/Ascent\s+(-?[\d.]+)/.exec(obj), desc = /\/Descent\s+(-?[\d.]+)/.exec(obj);
    const flags = /\/Flags\s+(\d+)/.exec(obj);
    if (name) out.set(name[1], { ascent: asc ? Number(asc[1]) / 1000 : null, descent: desc ? Number(desc[1]) / 1000 : null, flags: flags ? Number(flags[1]) : 0 });
  }
  return out;
}
// MuPDF 의 폰트 이름: 서브셋 접두(ABCDEF+) 제거, 공백 제거
export const cleanFontName = (n) => (n || '').replace(/^[A-Z]{6}\+/, '').replace(/\s+/g, '').replace(/[-,]?Regular$/, '');   // PyMuPDF 는 'NanumGothic Regular' 를 'NanumGothic' 으로 돌려준다

// ---- 메인: 페이지 추출 ----
export async function extractPage(page, opts = {}) {
  const pdfjs = getPdfjs();
  const OPS = pdfjs.OPS;
  const view = page.view;
  const x0 = f32(view[0]), y0 = f32(view[1]), x1 = f32(view[2]), y1 = f32(view[3]);
  const rect = [0, 0, f32(x1 - x0), f32(y1 - y0)];
  const rot = page.rotate || 0;
  if (rot) throw new Error('rotated page not supported: ' + rot);
  const base = [1, 0, 0, -1, f32(-x0), y1];   // pdf_page_transform (rotate 0)
  const ol = await page.getOperatorList();
  const fdesc = opts.fontDescriptors ?? new Map();

  const fonts = new Map();
  async function fontInfo(id) {
    if (fonts.has(id)) return fonts.get(id);
    const f = await new Promise((res) => page.commonObjs.get(id, res));
    const raw = f.name || '';
    const clean = cleanFontName(raw);
    const d = fdesc.get(raw) ?? fdesc.get(raw.replace(/^[A-Z]{6}\+/, '')) ?? null;
    let asc = d && d.ascent !== null ? d.ascent : Math.trunc(f.ascent * 1000) / 1000;
    let desc = d && d.descent !== null ? d.descent : Math.trunc(f.descent * 1000) / 1000;
    const info = { id, raw, name: clean, ascender: f32(asc), descender: f32(desc), composite: !!f.composite, vertical: !!f.vertical, descFlags: d ? d.flags : 0, bbox: f.bbox ? Array.from(f.bbox) : null,
      bold: /bold/i.test(clean) || !!(d && (d.flags & 0x40000)) };
    fonts.set(id, info);
    return info;
  }

  // 그래픽 상태
  let ctm = base.slice();
  let clipRect = null, pendingClip = false;   // 축 평행 클립 사각형(장치 좌표)의 교집합
  const stack = [];
  let fill = [0, 0, 0], stroke = [0, 0, 0], lineWidth = 1;
  // 텍스트 상태
  let font = null, fsize = 0, tc = 0, tw = 0, th = 1, tr = 0, rise = 0, leading = 0;
  let tm = IDENT.slice(), tlm = IDENT.slice();
  const drawings = [], glyphs = [], images = [];
  let seq = 0;
  let curPath = null;

  const colorOf = (rgb) => rgb.map(toUnit);
  const rectOf = (items) => {
    let a = Infinity, b = Infinity, c = -Infinity, d = -Infinity;
    for (const it of items) {
      const pts = it[0] === 'l' || it[0] === 're' ? [[it[1], it[2]], [it[3], it[4]]] : it[0] === 'c' ? [[it[1], it[2]], [it[3], it[4]], [it[5], it[6]], [it[7], it[8]]] : [];
      for (const [x, y] of pts) { a = Math.min(a, x); b = Math.min(b, y); c = Math.max(c, x); d = Math.max(d, y); }
    }
    return items.length ? [a, b, c, d] : [0, 0, 0, 0];
  };

  function buildPath(data) {
    // data: [DrawOPS...]: 0 moveTo(x,y) 1 lineTo(x,y) 2 curveTo(6) 3 quadTo(4) 4 closePath
    const items = [];
    let cx = 0, cy = 0, sx = 0, sy = 0, i = 0;
    const T = (x, y) => tp(x, y, ctm);
    let nm = 0, nl = 0, ncl = 0;
    const sig = [];
    while (i < data.length) {
      const op = data[i++];
      if (op === 0) { [cx, cy] = T(data[i], data[i + 1]); sx = cx; sy = cy; i += 2; sig.push('m'); }
      else if (op === 1) { const [x, y] = T(data[i], data[i + 1]); items.push(['l', cx, cy, x, y]); cx = x; cy = y; i += 2; sig.push('l'); }
      else if (op === 2) { const p1 = T(data[i], data[i + 1]), p2 = T(data[i + 2], data[i + 3]), p3 = T(data[i + 4], data[i + 5]); items.push(['c', cx, cy, p1[0], p1[1], p2[0], p2[1], p3[0], p3[1]]); [cx, cy] = p3; i += 6; sig.push('c'); }
      else if (op === 3) { const p1 = T(data[i], data[i + 1]), p3 = T(data[i + 2], data[i + 3]); items.push(['c', cx, cy, p1[0], p1[1], p1[0], p1[1], p3[0], p3[1]]); [cx, cy] = p3; i += 4; sig.push('c'); }
      else if (op === 4) { if (cx !== sx || cy !== sy) { items.push(['l', cx, cy, sx, sy]); cx = sx; cy = sy; } sig.push('h'); }
      else throw new Error('unknown path op ' + op);
    }
    // pdf.js 는 `re` 를 m,l,l,l,h 로 바꾼다. 축 평행 직사각형이면 MuPDF 와 같이 're' 한 개로 본다(원문이 m/l/l/l/h 인 경우와는 구분 불가).
    const sg = sig.join('').replace(/h+$/, 'h');   // pdf.js 는 re 를 m,l,l,l,h,h 로 내보내기도 한다
    if (sg === 'mlllh' && items.length === 4) {
      const [a, b, c, d] = items;
      const axis = (a[2] === a[4] && b[1] === b[3] && c[2] === c[4] && d[1] === d[3] && a[3] === b[1] && b[4] === c[2] && c[3] === d[1] && d[4] === a[2]) || (a[1] === a[3] && b[2] === b[4] && c[1] === c[3] && d[2] === d[4]);
      // 4 번째 선은 closePath 가 만든 선이므로 시작점으로 돌아온다. 위 조건은 각 변이 수평/수직인지만 본다.
      if (axis && closedRect(items)) {
        const xs = [a[1], a[3], b[3], c[3]], ys = [a[2], a[4], b[4], c[4]];
        return [['re', Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)]];
      }
    }
    return items;
  }
  function closedRect(items) {
    const [a, b, c, d] = items;
    const horiz = (it) => it[2] === it[4], vert = (it) => it[1] === it[3];
    return ((horiz(a) && vert(b) && horiz(c) && vert(d)) || (vert(a) && horiz(b) && vert(c) && horiz(d))) && d[3] === a[1] && d[4] === a[2];
  }

  function paint(kind, paintOp) {
    // kind: 'f','s','fs'
    const items = curPath;
    const d = { type: kind, color: kind.includes('s') ? colorOf(stroke) : null, fill: kind.includes('f') ? colorOf(fill) : null, width: kind.includes('s') ? f32(lineWidth * expansion(ctm)) : null,
      items, rect: rectOf(items), closePath: null, even_odd: kind.includes('f') ? (paintOp === OPS.eoFill || paintOp === OPS.eoFillStroke || paintOp === OPS.closeEOFillStroke) : null, seq: seq++ };
    drawings.push(d);
  }

  function showGlyphs(arr, fi) {
    for (const g of arr) {
      if (typeof g === 'number') { tm = preTranslate(tm, f32(f32(f32(-g * K001) * fsize) * th), 0); continue; }
      if (g === null || g === undefined) continue;
      const tsm = [f32(fsize * th), 0, 0, fsize, 0, rise];
      const trm = concat(tsm, tm);
      const o = tp(trm[4], trm[5], ctm);
      const full = concat(concat([tsm[0], 0, 0, tsm[3], 0, 0], tm.slice(0, 4).concat([0, 0])), ctm.slice(0, 4).concat([0, 0]));
      const size = expansion(full);
      const w0 = f32(f32(g.width) * K001);
      glyphs.push({ clip: clipRect ? clipRect.slice() : null, c: g.unicode ?? '', ox: o[0], oy: o[1], w0, size, font: fi, mode: tr, color: fill.slice(), dir: size ? [full[0] / Math.hypot(full[0], full[1]), full[1] / Math.hypot(full[0], full[1])] : [1, 0], seq: seq++ });
      let tx = f32(f32(f32(w0 * fsize) + tc) * th);
      if (!fi.composite && g.originalCharCode === 32) tx = f32(tx + f32(tw * th));
      tm = preTranslate(tm, tx, 0);
    }
  }

  for (let i = 0; i < ol.fnArray.length; i++) {
    const fn = ol.fnArray[i], a = ol.argsArray[i];
    switch (fn) {
      case OPS.save: stack.push({ ctm: ctm.slice(), fill: fill.slice(), stroke: stroke.slice(), lineWidth, clipRect }); break;
      case OPS.restore: { const s = stack.pop(); if (s) { ctm = s.ctm; fill = s.fill; stroke = s.stroke; lineWidth = s.lineWidth; clipRect = s.clipRect; } break; }
      case OPS.transform: ctm = concat(a.map(f32), ctm); break;
      case OPS.setLineWidth: lineWidth = f32(a[0]); break;
      case OPS.setFillRGBColor: fill = hexToRgb(a[0]); break;
      case OPS.setStrokeRGBColor: stroke = hexToRgb(a[0]); break;
      case OPS.clip: case OPS.eoClip: pendingClip = true; break;
      case OPS.constructPath: {
        const pop = a[0], data = a[1][0];
        const items = data && data.length ? buildPath(data) : [];
        if (pendingClip) {
          pendingClip = false;
          const r = rectOf(items);
          clipRect = clipRect ? [Math.max(clipRect[0], r[0]), Math.max(clipRect[1], r[1]), Math.min(clipRect[2], r[2]), Math.min(clipRect[3], r[3])] : r;
        }
        curPath = items;
        if (pop === OPS.stroke || pop === OPS.closeStroke) paint('s', pop);
        else if (pop === OPS.fill || pop === OPS.eoFill) paint('f', pop);
        else if (pop === OPS.fillStroke || pop === OPS.eoFillStroke || pop === OPS.closeFillStroke || pop === OPS.closeEOFillStroke) paint('fs', pop);
        // endPath(클립만) 은 드로잉이 아니다
        curPath = null;
        break;
      }
      case OPS.beginText: tm = IDENT.slice(); tlm = IDENT.slice(); break;
      case OPS.endText: break;
      case OPS.setFont: font = await fontInfo(a[0]); fsize = f32(a[1]); break;
      case OPS.setTextRenderingMode: tr = a[0]; break;
      case OPS.setCharSpacing: tc = f32(a[0]); break;
      case OPS.setWordSpacing: tw = f32(a[0]); break;
      case OPS.setHScale: th = f32(a[0] / 100); break;
      case OPS.setLeading: leading = f32(a[0]); break;
      case OPS.setTextRise: rise = f32(a[0]); break;
      case OPS.setTextMatrix: tm = a[0] ? Array.from({ length: 6 }, (_, k) => f32(a[0][k])) : IDENT.slice(); tlm = tm.slice(); break;
      case OPS.moveText: tlm = preTranslate(tlm, f32(a[0]), f32(a[1])); tm = tlm.slice(); break;
      case OPS.setLeadingMoveText: leading = f32(-a[1]); tlm = preTranslate(tlm, f32(a[0]), f32(a[1])); tm = tlm.slice(); break;
      case OPS.nextLine: tlm = preTranslate(tlm, 0, f32(-leading)); tm = tlm.slice(); break;
      case OPS.showText: if (font) showGlyphs(a[0], font); break;
      case OPS.showSpacedText: if (font) showGlyphs(a[0], font); break;
      case OPS.nextLineShowText: tlm = preTranslate(tlm, 0, f32(-leading)); tm = tlm.slice(); if (font) showGlyphs(a[0], font); break;
      case OPS.paintImageXObject: case OPS.paintInlineImageXObject: {
        const bb = imageBBox(ctm);
        let img = null;
        if (fn === OPS.paintImageXObject) img = await new Promise((res) => { try { page.objs.get(a[0], res); } catch (e) { res(null); } });
        else img = a[0];
        images.push({ bbox: bb, ctm: ctm.slice(), img });
        break;
      }
      default: break;
    }
  }
  return { rect, drawings, glyphs, images, fonts: [...fonts.values()] };
}

function imageBBox(ctm) {
  const pts = [tp(0, 0, ctm), tp(1, 0, ctm), tp(1, 1, ctm), tp(0, 1, ctm)];
  const xs = pts.map((p) => p[0]), ys = pts.map((p) => p[1]);
  return [Math.min(...xs), Math.min(...ys), Math.max(...xs), Math.max(...ys)];
}
