// photopage.find_blocks / _bands / _blk_corr / _syllable_h 이식
import { getCv, tracker } from './cv.js';
import { percentile, median } from './npy.js';

const PPM = 10;

export function blkCorr(t, bold, inkMm = 0.0) {
  if (t.includes('(') || t.includes(')')) return 0.88;
  return (bold || inkMm >= 5.5) ? 1 / 1.07 : 1.0;
}

export function syllableH(bx) {
  const iv = bx.map((r) => [r[0], r[0] + r[2], r[1], r[1] + r[3]]).sort((a, b) => a[0] - b[0] || a[1] - b[1] || a[2] - b[2] || a[3] - b[3]);
  const merged = [];
  for (const [x0, x1, y0, y1] of iv) {
    if (merged.length && x0 < merged[merged.length - 1][1] - 1) {
      const m = merged[merged.length - 1];
      merged[merged.length - 1] = [m[0], Math.max(m[1], x1), Math.min(m[2], y0), Math.max(m[3], y1)];
    } else merged.push([x0, x1, y0, y1]);
  }
  return percentile(merged.map((m) => m[3] - m[2]), 75);
}

// img: BGR Mat(평탄화), fgray: gray Mat, tb: [x0,y0,x1,y1] -> blocks[]
export function findBlocks(img, fgray, tb) {
  const cv = getCv();
  const T = tracker();
  try {
    const H = fgray.rows, W = fgray.cols;
    const [x0, y0, x1, y1] = tb.map((v) => Math.trunc(v));
    const hsv = T.add(new cv.Mat());
    cv.cvtColor(img, hsv, cv.COLOR_BGR2HSV);
    const paper0 = T.add(new cv.Mat(H, W, cv.CV_8UC1));
    {   // 주의: Mat.data 는 wasm 힙 뷰라 이후 할당으로 힙이 커지면 무효화된다. 쓰기 직전에 가져온다.
      const hd = hsv.data, pd = paper0.data;
      for (let i = 0; i < H * W; i++) pd[i] = (hd[i * 3 + 2] > 120 && hd[i * 3 + 1] < 70) ? 1 : 0;
    }
    const k15 = T.add(cv.Mat.ones(15, 15, cv.CV_8U));
    const paperO = T.add(new cv.Mat());
    cv.morphologyEx(paper0, paperO, cv.MORPH_OPEN, k15, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const labP = T.add(new cv.Mat());
    const nP = cv.connectedComponents(paperO, labP, 8, cv.CV_32S);
    const cnt = new Float64Array(nP);
    {
      const lp = labP.data32S;
      for (let i = 0; i < H * W; i++) cnt[lp[i]]++;
    }
    cnt[0] = 0;
    let best = 0;
    for (let i = 1; i < nP; i++) if (cnt[i] > cnt[best]) best = i;
    if (cnt[best] === 0) return [];
    const pm = T.add(new cv.Mat(H, W, cv.CV_8UC1));
    {
      const pmd = pm.data, lp = labP.data32S;
      for (let i = 0; i < H * W; i++) pmd[i] = lp[i] === best ? 1 : 0;
    }
    const cnts = T.add(new cv.MatVector()), hier = T.add(new cv.Mat());
    cv.findContours(pm, cnts, hier, cv.RETR_EXTERNAL, cv.CHAIN_APPROX_SIMPLE);
    let bi = -1, ba = -1;
    for (let i = 0; i < cnts.size(); i++) { const c = cnts.get(i); const a = cv.contourArea(c); c.delete(); if (a > ba) { ba = a; bi = i; } }
    const one = T.add(new cv.MatVector());
    one.push_back(cnts.get(bi));
    const paper = T.add(cv.Mat.zeros(H, W, cv.CV_8UC1));
    cv.drawContours(paper, one, -1, new cv.Scalar(1), -1, cv.LINE_8);
    const paperE = T.add(new cv.Mat());
    cv.erode(paper, paperE, k15, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const sm = T.add(new cv.Mat());
    cv.resize(fgray, sm, new cv.Size(Math.floor(W / 4), Math.floor(H / 4)), 0, 0, cv.INTER_AREA);
    const smb = T.add(new cv.Mat());
    cv.medianBlur(sm, smb, 71);
    const bgm = T.add(new cv.Mat());
    cv.resize(smb, bgm, new cv.Size(W, H), 0, 0, cv.INTER_LINEAR);
    const ink = T.add(new cv.Mat(H, W, cv.CV_8UC1));
    {
      const idd = ink.data, bd = bgm.data, gd = fgray.data, ped = paperE.data;
      for (let i = 0; i < H * W; i++) idd[i] = (((bd[i] - gd[i]) > 60) && gd[i] < 200 && ped[i] > 0) ? 1 : 0;
      const m = Math.trunc(1.5 * PPM);
      for (let y = Math.max(y0 - m, 0); y < Math.min(y1 + m, H); y++) idd.fill(0, y * W + Math.max(x0 - m, 0), y * W + Math.min(x1 + m, W));
    }
    const lab = T.add(new cv.Mat()), stM = T.add(new cv.Mat()), cen = T.add(new cv.Mat());
    const n = cv.connectedComponentsWithStats(ink, lab, stM, cen, 8, cv.CV_32S);
    const sdv = new Int32Array(stM.data32S);   // 힙 뷰가 아닌 복사본(이후 할당에 안전)
    const st = (i, j) => sdv[i * 5 + j];
    const keep = new Uint8Array(n);
    const thin = [];
    for (let i = 1; i < n; i++) {
      const x = st(i, 0), y = st(i, 1), w = st(i, 2), h = st(i, 3), a = st(i, 4);
      if (h <= 6 && 8 * PPM <= w && w <= 120 * PPM && a >= 0.5 * w * h) thin.push([x, y, w, h]);
      if (a < 12 || h < 0.8 * PPM || h > 14 * PPM || w > 60 * PPM) continue;
      if (w > 40 * PPM && h < 2 * PPM) continue;
      if (h > 7.5 * PPM && w < 2.5 * PPM) continue;
      keep[i] = 1;
    }
    const ld = new Int32Array(lab.data32S);   // 복사본
    const km = T.add(new cv.Mat(H, W, cv.CV_8UC1));
    {
      const kmd0 = km.data;
      for (let i = 0; i < H * W; i++) kmd0[i] = keep[ld[i]];
    }
    const dil = T.add(new cv.Mat());
    const kern = T.add(cv.Mat.ones(Math.trunc(1.0 * PPM), Math.trunc(14 * PPM), cv.CV_8U));
    cv.dilate(km, dil, kern, new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
    const lab2 = T.add(new cv.Mat());
    const n2 = cv.connectedComponents(dil, lab2, 8, cv.CV_32S);
    const l2 = new Int32Array(lab2.data32S);
    const kmd = new Uint8Array(km.data);
    const sets = Array.from({ length: n2 }, () => new Set());
    for (let i = 0; i < H * W; i++) if (kmd[i] > 0 && l2[i] > 0) { const L = ld[i]; if (L > 0) sets[l2[i]].add(L); }
    let out = [];
    for (let k = 1; k < n2; k++) {
      const ids0 = [...sets[k]].sort((a, b) => a - b);
      if (ids0.length < 2) continue;
      let ext;
      if (ids0.length >= 8) ext = percentile(ids0.map((i) => st(i, 1) + st(i, 3)), 90) - percentile(ids0.map((i) => st(i, 1)), 10);
      else ext = Math.max(...ids0.map((i) => st(i, 1) + st(i, 3))) - Math.min(...ids0.map((i) => st(i, 1)));
      const order = ids0.map((id, idx) => [id, idx]).sort((a, b) => st(a[0], 0) - st(b[0], 0) || a[1] - b[1]).map((p) => p[0]);
      const groups = [];
      let cur = [order[0]], cmx = st(order[0], 0) + st(order[0], 2);
      const maxRight = Math.max(...order.map((i) => st(i, 0) + st(i, 2)));
      for (let q = 1; q < order.length; q++) {
        const i_ = order[q];
        if (st(i_, 0) - cmx > 1.25 * ext && groups.length === 0 && st(i_, 0) > (x0 + x1) / 2 && maxRight >= x1 - 14 * PPM) {
          groups.push(cur); cur = [];
        }
        cur.push(i_); cmx = Math.max(cmx, st(i_, 0) + st(i_, 2));
      }
      groups.push(cur);
      for (const grp of groups) {
        let ids = grp.slice();
        if (ids.length < 2) continue;
        const bxAll = ids.map((i) => [st(i, 0), st(i, 1), st(i, 2), st(i, 3)]);
        let bx = bxAll;
        if (bx.length >= 4) {
          const mh = median(bx.map((b) => b[3]));
          const okk = bx.map((b) => b[3] <= 2.2 * mh);
          ids = ids.filter((_, j) => okk[j]); bx = bx.filter((_, j) => okk[j]);
          if (ids.length < 2) continue;
        }
        const hs = bx.map((b) => b[3]);
        const p90 = percentile(hs, 90);
        const tallIdx = [];
        hs.forEach((h, j) => { if (h >= 0.6 * p90 && h <= 1.5 * p90) tallIdx.push(j); });
        const top = Math.min(...tallIdx.map((j) => bx[j][1]));
        const bot = Math.max(...tallIdx.map((j) => bx[j][1] + bx[j][3]));
        const coreH = percentile(tallIdx.map((j) => hs[j]), 70);
        const coreH2 = bot - top;
        const xa = Math.min(...bxAll.map((b) => b[0])), xb = Math.max(...bxAll.map((b) => b[0] + b[2]));
        const ya = Math.min(...bxAll.map((b) => b[1])), yb = Math.max(...bxAll.map((b) => b[1] + b[3]));
        const idset = new Set(ids);
        const sw = xb - xa, sh = yb - ya;
        const sub = new cv.Mat(sh, sw, cv.CV_8UC1);
        const sbuf = new Uint8Array(sw * sh);
        let ssum = 0;
        for (let y = 0; y < sh; y++) for (let x = 0; x < sw; x++) { const v = idset.has(ld[(ya + y) * W + xa + x]) ? 1 : 0; sbuf[y * sw + x] = v; ssum += v; }
        sub.data.set(sbuf);
        const cs = new cv.MatVector(), hh = new cv.Mat();
        cv.findContours(sub, cs, hh, cv.RETR_LIST, cv.CHAIN_APPROX_NONE);
        let per = 0;
        for (let q = 0; q < cs.size(); q++) { const c = cs.get(q); per += cv.arcLength(c, true); c.delete(); }
        cs.delete(); hh.delete(); sub.delete();
        const stroke = per ? 2.0 * ssum / per : 0;
        const ih = bot - top;
        const ul = thin.some((t) => t[2] >= 0.6 * (xb - xa) && t[0] >= xa - 3 * PPM && t[0] + t[2] <= xb + 3 * PPM && 0 <= t[1] - bot && t[1] - bot <= 4 * PPM);
        out.push({ bbox: [xa, ya, xb, yb], ink_h: coreH, ink_h2: coreH2, ext_small: false, line: k, nc: bx.length, bold: !!(ih && stroke / ih > 0.135), underline: ul, stroke_ratio: ih ? stroke / ih : 0.0 });
      }
    }
    let merged = true;
    while (merged) {
      merged = false;
      outer:
      for (let i = 0; i < out.length; i++) {
        for (let j = i + 1; j < out.length; j++) {
          const a = out[i], b = out[j];
          const ay0 = a.bbox[1], ay1 = a.bbox[3], by0 = b.bbox[1], by1 = b.bbox[3];
          const ov = Math.min(ay1, by1) - Math.max(ay0, by0);
          const gap = Math.max(a.bbox[0], b.bbox[0]) - Math.min(a.bbox[2], b.bbox[2]);
          if (ov >= 0.6 * Math.min(ay1 - ay0, by1 - by0) && gap <= Math.min(20 * PPM, 2.0 * Math.min(a.ink_h, b.ink_h) / 0.88)) {
            const bb = [Math.min(a.bbox[0], b.bbox[0]), Math.min(ay0, by0), Math.max(a.bbox[2], b.bbox[2]), Math.max(ay1, by1)];
            const big = (a.bbox[3] - a.bbox[1]) >= (b.bbox[3] - b.bbox[1]) ? a : b;
            out[i] = { bbox: bb, ink_h: big.ink_h, ink_h2: big.ink_h2 ?? big.ink_h, ext_small: big.ext_small, line: big.line, nc: (a.nc || 0) + (b.nc || 0), bold: big.bold, underline: a.underline || b.underline, stroke_ratio: big.stroke_ratio ?? 0.0 };
            out.splice(j, 1);
            merged = true;
            break outer;
          }
        }
      }
    }
    out = out.map((o, i) => [o, i]).sort((p, q) => {
      const kp = [Math.floor(p[0].bbox[1] / (3 * PPM)), p[0].bbox[0]], kq = [Math.floor(q[0].bbox[1] / (3 * PPM)), q[0].bbox[0]];
      return kp[0] - kq[0] || kp[1] - kq[1] || p[1] - q[1];
    }).map((p) => p[0]);
    return out;
  } finally { T.free(); }
}

export function bands(blocks, my = 30) {
  const out = [];
  blocks.forEach((b, i) => {
    const [x0, y0, x1, y1] = b.bbox;
    let lo = y0 - my, hi = y1 + my;
    blocks.forEach((o, j) => {
      if (i === j || o.bbox[2] <= x0 || o.bbox[0] >= x1) return;
      const [, oy0, , oy1] = o.bbox;
      if ((oy0 + oy1) / 2 < (y0 + y1) / 2) { if (oy1 > lo) lo = Math.max(lo, (oy1 + y0) / 2); }
      else if (oy0 < hi) hi = Math.min(hi, (y1 + oy0) / 2);
    });
    out.push([lo, hi]);
  });
  return out;
}
