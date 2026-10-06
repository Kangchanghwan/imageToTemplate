// 브라우저 OCR: PP-OCRv5 korean mobile rec + PP-OCRv5 mobile det (onnxruntime-web). tools/browserocr/backend.py 의 최선 구성
// (pp_det2f_mob: 표선 제거 + det(DB) -> 줄 묶기 -> rec, det 가 빈 결과면 줄 분할 rec 폴백) 이식.
// ort 는 주입: Node/브라우저 모두 `import * as ort from 'onnxruntime-web'` (같은 패키지, wasm EP).
import { getCv, tracker, copyMat } from './cv.js';
import { pyRound, percentileU8, histU8, f32 } from './npy.js';

export async function createPpocr({ ort, recModel, detModel, dictText, threads = 4 }) {
  ort.env.wasm.numThreads = threads;
  const opt = { executionProviders: ['wasm'], graphOptimizationLevel: 'all' };
  const rec = await ort.InferenceSession.create(recModel, opt);
  const det = await ort.InferenceSession.create(detModel, opt);
  const lines = dictText.replace(/\r\n?/g, '\n').split('\n');
  if (lines[lines.length - 1] === '') lines.pop();
  const D = ['blank', ...lines, ' '];
  return new Ppocr(ort, rec, det, D);
}

function grayU8(crop) {
  const cv = getCv();
  const g = new cv.Mat();
  cv.cvtColor(crop, g, cv.COLOR_BGR2GRAY);
  return g;
}

export class Ppocr {
  constructor(ort, rec, det, D) { this.ort = ort; this.rec = rec; this.det = det; this.D = D; this.stats = { recCalls: 0, detCalls: 0, recMs: 0, detMs: 0 }; }

  // clean_rules: 긴 가로선(>=50px)/세로선(크롭 높이 80% 이상, >=45px) 잔재를 흰색으로
  cleanRules(crop) {
    const cv = getCv();
    const T = tracker();
    try {
      const g = T.add(grayU8(crop));
      const H = g.rows, W = g.cols;
      const gd = new Uint8Array(g.data);
      const bg = percentileU8(histU8(gd), gd.length, 80);
      const m = T.add(new cv.Mat(H, W, cv.CV_8UC1));
      m.data.set(gd.map((v) => ((bg - v) > 50 ? 1 : 0)));
      const bv = cv.morphologyDefaultBorderValue(), anc = new cv.Point(-1, -1);
      const hz = T.add(new cv.Mat());
      cv.morphologyEx(m, hz, cv.MORPH_OPEN, T.add(cv.Mat.ones(1, 50, cv.CV_8U)), anc, 1, cv.BORDER_CONSTANT, bv);
      const vl = T.add(H >= 45 ? new cv.Mat() : cv.Mat.zeros(H, W, cv.CV_8UC1));
      if (H >= 45) cv.morphologyEx(m, vl, cv.MORPH_OPEN, T.add(cv.Mat.ones(Math.max(45, Math.trunc(0.8 * H)), 1, cv.CV_8U)), anc, 1, cv.BORDER_CONSTANT, bv);
      const orm = T.add(new cv.Mat());
      cv.bitwise_or(hz, vl, orm);
      const r = T.add(new cv.Mat());
      cv.dilate(orm, r, T.add(cv.Mat.ones(3, 3, cv.CV_8U)), anc, 1, cv.BORDER_CONSTANT, bv);
      const rd = new Uint8Array(r.data);
      if (!rd.some((v) => v)) return copyMat(crop);
      const out = copyMat(crop);
      const od = out.data;
      for (let i = 0; i < rd.length; i++) if (rd[i]) { od[i * 3] = 255; od[i * 3 + 1] = 255; od[i * 3 + 2] = 255; }
      return out;
    } finally { T.free(); }
  }

  async recLine(img, h = 48) {
    const cv = getCv();
    const ih = img.rows, iw = img.cols;
    if (ih < 2 || iw < 2) return ['', 0.0];
    let w = Math.max(Math.ceil(h * iw / ih), 8);
    w = Math.min(w, 3200);
    const small = new cv.Mat();
    cv.resize(img, small, new cv.Size(w, h), 0, 0, cv.INTER_LINEAR);
    const sd = small.data, n = w * h;
    const x = new Float32Array(3 * n);
    for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) x[c * n + i] = f32(f32(f32(sd[i * 3 + c] / 255) - 0.5) / 0.5);
    small.delete();
    const t0 = performance.now();
    const out = await this.rec.run({ [this.rec.inputNames[0]]: new this.ort.Tensor('float32', x, [1, 3, h, w]) });
    this.stats.recCalls++; this.stats.recMs += performance.now() - t0;
    const o = out[this.rec.outputNames[0]];
    const [, Tn, K] = o.dims, a = o.data;
    let prev = 0;
    const txt = [], ps = [];
    for (let t = 0; t < Tn; t++) {
      let bi = 0, bv = a[t * K];
      for (let k = 1; k < K; k++) if (a[t * K + k] > bv) { bv = a[t * K + k]; bi = k; }
      if (bi !== 0 && bi !== prev && bi < this.D.length) { txt.push(this.D[bi]); ps.push(bv); }
      prev = bi;
    }
    return [txt.join(''), ps.length ? ps.reduce((s, v) => s + v, 0) / ps.length : 0.0];
  }

  // CV 가로 투영 줄 분할 -> 줄 크롭 Mat 목록(호출자가 delete)
  splitLines(crop) {
    const cv = getCv();
    const T = tracker();
    try {
      const g = T.add(grayU8(crop));
      const H = g.rows, W = g.cols;
      const gd = new Uint8Array(g.data);
      const bg = percentileU8(histU8(gd), gd.length, 80);
      const m = T.add(new cv.Mat(H, W, cv.CV_8UC1));
      m.data.set(gd.map((v) => ((bg - v) > 50 ? 1 : 0)));
      const mo = T.add(new cv.Mat());
      cv.morphologyEx(m, mo, cv.MORPH_OPEN, T.add(cv.Mat.ones(2, 2, cv.CV_8U)), new cv.Point(-1, -1), 1, cv.BORDER_CONSTANT, cv.morphologyDefaultBorderValue());
      const md = new Uint8Array(mo.data);
      const rows = [];
      for (let y = 0; y < H; y++) { let s = 0; for (let x = 0; x < W; x++) s += md[y * W + x]; if (s > 0) rows.push(y); }
      if (!rows.length) return [copyMat(crop)];
      const runs = [];
      let s = rows[0], p = rows[0];
      for (const r of rows.slice(1)) { if (r !== p + 1) { runs.push([s, p]); s = r; } p = r; }
      runs.push([s, p]);
      const mh = Math.max(...runs.map(([a, b]) => b - a + 1));
      let mg = [];
      for (const [a, b] of runs) { if (mg.length && a - mg[mg.length - 1][1] - 1 < 0.25 * mh) mg[mg.length - 1][1] = b; else mg.push([a, b]); }
      mg = mg.filter(([a, b]) => b - a + 1 >= 3);
      const pad = 4;
      const outs = mg.map(([a, b]) => { const y0 = Math.max(a - pad, 0), y1 = Math.min(b + pad + 1, H); const r = crop.roi(new cv.Rect(0, y0, W, y1 - y0)); const c = copyMat(r); r.delete(); return c; });
      return outs.length ? outs : [copyMat(crop)];
    } finally { T.free(); }
  }

  async detBoxes(crop) {
    const cv = getCv();
    const h = crop.rows, w = crop.cols;
    let sc = 1.0;
    if (Math.min(h, w) < 64) sc = 64.0 / Math.min(h, w);
    if (Math.max(h, w) * sc > 960) sc = 960.0 / Math.max(h, w);
    const nh = Math.max(32, pyRound(h * sc / 32) * 32), nw = Math.max(32, pyRound(w * sc / 32) * 32);
    const small = new cv.Mat();
    cv.resize(crop, small, new cv.Size(nw, nh), 0, 0, cv.INTER_LINEAR);
    const sd = small.data, n = nw * nh;
    const mean = [0.485, 0.456, 0.406].map(f32), std = [0.229, 0.224, 0.225].map(f32);
    const x = new Float32Array(3 * n);
    for (let i = 0; i < n; i++) for (let c = 0; c < 3; c++) x[c * n + i] = f32(f32(f32(sd[i * 3 + c] / 255) - mean[c]) / std[c]);
    small.delete();
    const t0 = performance.now();
    const out = await this.det.run({ [this.det.inputNames[0]]: new this.ort.Tensor('float32', x, [1, 3, nh, nw]) });
    this.stats.detCalls++; this.stats.detMs += performance.now() - t0;
    const pm = out[this.det.outputNames[0]].data;   // [1,1,nh,nw]
    const b = new cv.Mat(nh, nw, cv.CV_8UC1);
    const bd = b.data;
    for (let i = 0; i < n; i++) bd[i] = pm[i] > 0.3 ? 1 : 0;
    const cs = new cv.MatVector(), hh = new cv.Mat();
    cv.findContours(b, cs, hh, cv.RETR_LIST, cv.CHAIN_APPROX_SIMPLE);
    const boxes = [];
    for (let i = 0; i < cs.size(); i++) {
      const c = cs.get(i);
      const r = cv.boundingRect(c);
      c.delete();
      const { x: x0, y: y0, width: bw, height: bh } = r;
      if (bw < 3 || bh < 3) continue;
      let sum = 0;
      for (let yy = y0; yy < y0 + bh; yy++) for (let xx = x0; xx < x0 + bw; xx++) sum += pm[yy * nw + xx];
      if (sum / (bw * bh) < 0.5) continue;
      const d = pyRound(bw * bh * 1.5 / (2 * (bw + bh)));
      const a0 = x0 - d, b0 = y0 - d, a1 = x0 + bw + d, b1 = y0 + bh + d;
      boxes.push([Math.max(Math.trunc(a0 / nw * w), 0), Math.max(Math.trunc(b0 / nh * h), 0), Math.min(Math.trunc(a1 / nw * w), w), Math.min(Math.trunc(b1 / nh * h), h)]);
    }
    cs.delete(); hh.delete(); b.delete();
    return boxes;
  }

  async detRec(crop) {
    const cv = getCv();
    const bx = await this.detBoxes(crop);
    if (!bx.length) return ['', 0.0, []];
    const boxesOut = bx.map((b) => [...b]);
    bx.sort((a, b) => (a[1] + a[3]) / 2 - (b[1] + b[3]) / 2);
    const lines = [];
    for (const b of bx) {
      let placed = false;
      for (const L of lines) {
        const ly0 = L[0][1], ly1 = L[0][3];
        const ov = Math.min(ly1, b[3]) - Math.max(ly0, b[1]);
        if (ov > 0.5 * Math.min(ly1 - ly0, b[3] - b[1])) { L.push(b); placed = true; break; }
      }
      if (!placed) lines.push([b]);
    }
    const txt = [], ps = [];
    for (const L of [...lines].sort((a, b) => a[0][1] - b[0][1])) {
      const parts = [];
      for (const b of [...L].sort((p, q) => p[0] - q[0])) {
        let t = '', p = 0;
        if (b[3] > b[1] && b[2] > b[0]) {
          const r = crop.roi(new cv.Rect(b[0], b[1], b[2] - b[0], b[3] - b[1]));
          const c = copyMat(r); r.delete();
          [t, p] = await this.recLine(c);
          c.delete();
        }
        if (t) { parts.push(t); ps.push(p); }
      }
      txt.push(parts.join(' '));
    }
    return [txt.join(' '), ps.length ? Math.min(...ps) : 0.0, boxesOut];
  }

  // 칸/줄 크롭 1개 -> {text, conf, fallback}  (backend.make_read(pp_det2f_mob))
  async read(crop) {
    const cleaned = this.cleanRules(crop);
    let [t, p, boxes] = await this.detRec(cleaned);
    let fallback = false;
    if (!t) {   // det 가 아무것도 못 찾은 칸은 칸 전체를 줄 분할 rec 로 다시 읽는다
      fallback = true;
      const ls = this.splitLines(cleaned);
      const ts = [];
      for (const L of ls) { ts.push((await this.recLine(L))[0]); L.delete(); }
      t = ts.filter((x) => x).join(' ');
    }
    cleaned.delete();
    return { text: t.split(/\s+/).filter(Boolean).join(' '), conf: p, fallback, boxes, units: (boxes || []).reduce((a, b) => a + (b[2] - b[0]) / Math.max(1, b[3] - b[1]), 0) };
  }
}
