// 서버 재판독 콜백(Node 하네스용): 맥의 ssh -L 터널(127.0.0.1:18003 paddle, 18001 32B)로 elgrim 에 보낸다.
// 의미는 sheetparser/ocr.py 의 paddle_read(= _paddle_one + 잘림 재요청 + 한자면 32B) 와 같다.
//   서버 한 번 호출 = {png, est} -> 텍스트.  Python 코드는 호출만 흉내내고 바꾸지 않았다.
import { PNG } from './node_common.mjs';

const PADDLE = process.env.PADDLE_URL || 'http://127.0.0.1:18003/v1/chat/completions';
const VLM = process.env.VLM_URL || 'http://127.0.0.1:18001/v1/chat/completions';
const HAN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;
const b64 = (u8) => Buffer.from(u8).toString('base64');
export const serverStats = { paddleCalls: 0, vlmCalls: 0, trunc: 0, retryOk: 0, to32: 0, han: 0, hanFixed: 0, sec: 0 };

async function post(url, body, timeoutMs = 120000) {
  const r = await fetch(url, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body), signal: AbortSignal.timeout(timeoutMs) });
  if (!r.ok) throw new Error('http ' + r.status);
  return r.json();
}

// _paddle_one(crop, max_tokens, with_fin): "OCR:" 프롬프트, logprobs
async function paddleOne(png, maxTokens) {
  const body = { model: 'paddle', temperature: 0, max_tokens: maxTokens, logprobs: true,
    messages: [{ role: 'user', content: [{ type: 'image_url', image_url: { url: 'data:image/png;base64,' + b64(png) } }, { type: 'text', text: 'OCR:' }] }] };
  const t0 = performance.now();
  const r = await post(PADDLE, body);
  serverStats.paddleCalls++; serverStats.sec += (performance.now() - t0) / 1000;
  const ch = r.choices[0];
  const lp = ((ch.logprobs || {}).content || []).filter((t) => 'logprob' in t).map((t) => t.logprob);
  return { text: ch.message.content.split(/\s+/).filter(Boolean).join(' '), p: lp.length ? Math.exp(Math.min(...lp)) : 1.0, fin: ch.finish_reason };
}

// _pad43: 4:1 이내 + 짧은 변 64px 이상 (흰색 패딩만)
function pad43(png) {
  const im = PNG.sync.read(Buffer.from(png));
  const h = im.height, w = im.width, minside = 64;
  const nh = Math.max(h, minside, Math.floor((w + 3) / 4)), nw = Math.max(w, minside, Math.floor((h + 3) / 4));
  if (nh === h && nw === w) return png;
  const t = Math.floor((nh - h) / 2), l = Math.floor((nw - w) / 2);
  const out = new PNG({ width: nw, height: nh });
  out.data.fill(255);
  for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) { const s = (y * w + x) * 4, d = ((y + t) * nw + x + l) * 4; out.data[d] = im.data[s]; out.data[d + 1] = im.data[s + 1]; out.data[d + 2] = im.data[s + 2]; out.data[d + 3] = 255; }
  return { png: new Uint8Array(PNG.sync.write(out, { colorType: 2 })), h: nh, w: nw };
}
const CELL = String.raw`[^|\n<>\u2600-\u27bf\U0001f000-\U0001faff]{0,160}`;
const GRAMMAR = 'root ::= l0\nl0 ::= cell "\\n"?\ncell ::= ' + CELL + '\n';
const PROMPT32 = '이미지의 글자를 보이는 그대로 적어라. 줄이 바뀌면 공백 하나로 잇는다. 주변 선이나 물체는 무시한다. 글자가 없으면 빈 줄.';

async function ask32(png, h, w, maxTokens) {
  const imgTok = Math.floor((h + 31) / 32) * Math.floor((w + 31) / 32) + 8;
  if (imgTok + [...PROMPT32].length + 40 + maxTokens > 8192 * 0.9) return { over: 'too_big' };
  const body = { model: 'vlm', temperature: 0, max_tokens: maxTokens, grammar: GRAMMAR,
    messages: [{ role: 'user', content: [{ type: 'image_url', image_url: { url: 'data:image/png;base64,' + b64(png) } }, { type: 'text', text: PROMPT32 }] }] };
  for (let k = 0; k < 3; k++) {
    try {
      const r = await post(VLM, body, 300000);
      serverStats.vlmCalls++;
      return { text: r.choices[0].message.content, fin: r.choices[0].finish_reason };
    } catch (e) { await new Promise((res) => setTimeout(res, 2000)); }
  }
  return null;
}
// read_crop32 -> 텍스트 | null  (_ask_retry: 잘리면 한도 2배 1회)
async function readCrop32(png, w0, h0, est) {
  const p = pad43(png);
  const pp = typeof p === 'object' && p.png ? p : { png: p, h: h0, w: w0 };
  const lim = Math.max(120, est);
  let r = await ask32(pp.png, pp.h, pp.w, lim);
  if (r === null) return null;
  if (r.over === 'too_big') return null;
  if (r.fin === 'length') {
    const r2 = await ask32(pp.png, pp.h, pp.w, lim * 2);
    if (r2 === null || r2.over) return r.text ? r.text.split(/\s+/).filter(Boolean).join(' ') : null;
    r = r2;
  }
  return r.text.split(/\s+/).filter(Boolean).join(' ');
}

// _paddle_read_raw + paddle_read
async function paddleRead(png, w, h, est) {
  const mt = Math.min(512, Math.max(64, est ?? 64));
  let { text: t, p, fin } = await paddleOne(png, mt);
  if (fin === 'length') {
    serverStats.trunc++;
    let done = false;
    if (mt < 512) {
      const r2 = await paddleOne(png, Math.min(512, mt * 2));
      if (r2.fin !== 'length') { serverStats.retryOk++; t = r2.text; p = r2.p; done = true; }
    }
    if (!done) {
      serverStats.to32++;
      const t3 = await readCrop32(png, w, h, est ?? 64);
      if (t3) { t = t3; p = 1.0; }
    }
  }
  if (t && HAN.test(t)) {
    serverStats.han++;
    const t2 = await readCrop32(png, w, h, est ?? 64);
    if (t2 && !HAN.test(t2)) { serverStats.hanFixed++; return t2; }
  }
  return t;
}

// ocr_client 의 server 콜백: reqs -> [{text}]  (동시 4 호출: PADDLE_WORKERS=4 와 동일)
export async function serverReread(reqs) {
  const out = new Array(reqs.length);
  let i = 0;
  await Promise.all(Array.from({ length: Math.min(4, reqs.length) }, async () => {
    while (i < reqs.length) {
      const k = i++;
      const rq = reqs[k];
      let txt = null;
      for (let a = 0; a < 2 && txt === null; a++) {
        try { txt = await paddleRead(rq.png, rq.w, rq.h, rq.est); } catch (e) { await new Promise((r) => setTimeout(r, 1000)); }
      }
      out[k] = { text: txt };   // 실패하면 null: 클라이언트 결과 유지
    }
  }));
  return out;
}
