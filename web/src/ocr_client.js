// 브라우저 OCR 제공자(run.js 의 opts.ocr 구현): PP-OCRv5 로 칸/블록/줄을 읽고, 의심 칸만 서버 재판독 콜백으로 보낸다.
//   ppocr   : createPpocr() 결과
//   suspect : suspect.js 의 judge(feat) -> {suspect:boolean, reasons:[...]}  (없으면 서버 재판독 없음)
//   server  : async (reqs:[{id, kind:'cell'|'block', png:Uint8Array, w, h, est, reasons}]) -> [{text}]   (없으면 재판독 없음)
//   encode  : (Mat) -> Uint8Array PNG (Node: pngjs, 브라우저: canvas)
//   encodeAlt: (Mat) -> Uint8Array JPEG q90 (전송량 비교용 기록만, 보내지 않음)
//   log     : 수집용 배열(칸별 특징/결과)
import { getCv } from './cv.js';
import { estTokens, uncoveredInk } from './suspect.js';

async function pmap(items, fn, n = 1) {
  const out = new Array(items.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(n, items.length) }, async () => {
    while (i < items.length) { const k = i++; out[k] = await fn(items[k], k); }
  }));
  return out;
}

export function makeClientOcr({ ppocr, suspect = null, server = null, encode = null, encodeAlt = null, log = null, concurrency = 1 }) {
  const stat = { cells: 0, blocks: 0, lines: 0, suspects: 0, bytes: 0, bytesJpeg: 0, reqs: 0, changed: 0, serverMs: 0, clientMs: 0, byReason: {} };
  const emptyRes = { text: '', conf: 0, fallback: false };

  async function readOne(crop) {
    if (!crop || crop.rows < 1 || crop.cols < 1) return { ...emptyRes };
    const r = await ppocr.read(crop);
    r.uncov = uncoveredInk(crop, r.boxes);   // 참고용 특징(규칙으로는 채택하지 않음)
    return r;
  }

  async function rereadAll(kind, items, res, ctxs) {
    if (!suspect || !server) return;
    const reqs = [];
    items.forEach((it, k) => {
      const feat = { kind, text: res[k].text, conf: res[k].conf, fallback: res[k].fallback, uncov: res[k].uncov ?? 0, units: res[k].units ?? 0, w: it.crop?.cols ?? 0, h: it.crop?.rows ?? 0, nlines: it.nlines ?? 1, rs: it.rs ?? 1, cs: it.cs ?? 1 };
      const j = suspect.judge(feat);
      res[k].suspect = j.suspect; res[k].reasons = j.reasons;
      if (j.suspect && it.crop) {
        const png = encode(it.crop);
        reqs.push({ id: k, kind, png, w: it.crop.cols, h: it.crop.rows, est: estTokens(it.crop), reasons: j.reasons });
        stat.bytes += png.length;
        if (encodeAlt) stat.bytesJpeg += encodeAlt(it.crop).length;
        stat.suspects++;
        for (const r of j.reasons) stat.byReason[r] = (stat.byReason[r] || 0) + 1;
      }
    });
    stat.reqs += reqs.length;
    if (!reqs.length) return;
    const t0 = performance.now();
    const out = await server(reqs);
    stat.serverMs += performance.now() - t0;
    reqs.forEach((rq, i) => {
      const t = out[i]?.text;
      if (t !== undefined && t !== null) {
        if (t.trim() !== res[rq.id].text) stat.changed++;
        res[rq.id].client = res[rq.id].text;
        res[rq.id].text = t;
        res[rq.id].server = true;
      }
    });
  }

  return {
    stat,
    async readCells(items) {
      const t0 = performance.now();
      const res = await pmap(items, (it) => readOne(it.crop), concurrency);
      stat.clientMs += performance.now() - t0;
      stat.cells += items.length;
      if (log) items.forEach((it, k) => log.push({ kind: 'cell', r: it.r, c: it.c, text: res[k].text, conf: res[k].conf, fallback: res[k].fallback, uncov: res[k].uncov ?? 0, units: res[k].units ?? 0, w: it.crop?.cols ?? 0, h: it.crop?.rows ?? 0, nlines: it.nlines, rs: it.rs, cs: it.cs }));
      await rereadAll('cell', items, res);
      if (log) items.forEach((it, k) => { const e = log[log.length - items.length + k]; e.suspect = !!res[k].suspect; e.reasons = res[k].reasons ?? []; e.final = res[k].text; });
      return res;
    },
    async readBlocks(items) {
      const t0 = performance.now();
      const res = await pmap(items, (it) => readOne(it.crop), concurrency);
      stat.clientMs += performance.now() - t0;
      stat.blocks += items.length;
      if (log) items.forEach((it, k) => log.push({ kind: 'block', index: it.index, text: res[k].text, conf: res[k].conf, fallback: res[k].fallback, uncov: res[k].uncov ?? 0, units: res[k].units ?? 0, w: it.crop?.cols ?? 0, h: it.crop?.rows ?? 0 }));
      await rereadAll('block', items, res);
      if (log) items.forEach((it, k) => { const e = log[log.length - items.length + k]; e.suspect = !!res[k].suspect; e.reasons = res[k].reasons ?? []; e.final = res[k].text; });
      return res.map((r) => r.text);
    },
    async readLines(items) {   // break_pass 줄 읽기: 줄바꿈 위치 판정용이라 클라이언트 OCR 만 (서버 재판독 없음)
      const t0 = performance.now();
      const res = await pmap(items, (it) => readOne(it.crop), concurrency);
      stat.clientMs += performance.now() - t0;
      stat.lines += items.length;
      return res.map((r) => (r.text === '' && false ? null : r.text));
    },
  };
}
