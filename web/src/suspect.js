// 의심 칸 규칙. judge(feat) -> {suspect, reasons}. 규칙 목록/임계값은 tools/parity/suspect_eval.mjs 의 데이터로 정했다(docs/WEB_PORT.md).
import { getCv } from './cv.js';
import { percentileU8, histU8 } from './npy.js';

export const HAN = /[\u3400-\u4dbf\u4e00-\u9fff\uf900-\ufaff]/;

// ocr.est_tokens: 칸 크롭의 글줄 수 x 잉크 폭으로 서버 출력 토큰 한도 추정 (서버 재판독 요청에 동봉)
export function estTokens(crop, perChar = 1.3, margin = 1.5, floor = 8, cap = 512) {
  const cv = getCv();
  const g = new cv.Mat();
  cv.cvtColor(crop, g, cv.COLOR_BGR2GRAY);
  try {
    const H = g.rows, W = g.cols;
    if (H * W === 0) return floor;
    const gd = new Uint8Array(g.data);
    const bg = percentileU8(histU8(gd), gd.length, 80);
    const m = new cv.Mat(H, W, cv.CV_8UC1);
    m.data.set(gd.map((v) => ((bg - v) > 60 ? 1 : 0)));
    const lab = new cv.Mat(), st = new cv.Mat(), cen = new cv.Mat();
    const n = cv.connectedComponentsWithStats(m, lab, st, cen, 8, cv.CV_32S);
    const sd = new Int32Array(st.data32S);
    lab.delete(); st.delete(); cen.delete();
    const md = new Uint8Array(m.data);
    m.delete();
    const boxes = [];
    for (let i = 1; i < n; i++) if (sd[i * 5 + 4] >= 8 && sd[i * 5 + 3] >= 5) boxes.push([sd[i * 5], sd[i * 5 + 1], sd[i * 5 + 2], sd[i * 5 + 3]]);
    if (!boxes.length) return floor;
    const x0 = Math.min(...boxes.map((b) => b[0])), x1 = Math.max(...boxes.map((b) => b[0] + b[2]));
    const y0 = Math.min(...boxes.map((b) => b[1])), y1 = Math.max(...boxes.map((b) => b[1] + b[3]));
    const hs = boxes.map((b) => b[3]).sort((a, b) => a - b);
    const q = (arr, p) => { const vi = (arr.length - 1) * p / 100, pr = Math.floor(vi), nx = Math.min(pr + 1, arr.length - 1), t = vi - pr; const d = arr[nx] - arr[pr]; return t >= 0.5 ? arr[nx] - d * (1 - t) : arr[pr] + d * t; };
    const gh = Math.max(q(hs, 80), 6.0);
    const rows = [];
    for (let y = y0; y < y1; y++) { let any = 0; for (let x = x0; x < x1; x++) if (md[y * W + x]) { any = 1; break; } rows.push(any); }
    let runs = rows[0] ? 1 : 0;
    for (let i = 1; i < rows.length; i++) if (rows[i] === 1 && rows[i - 1] === 0) runs++;
    const py = Math.round;   // 은행가 반올림은 어림값이라 영향이 미미하다
    const lines = Math.max(runs, py((y1 - y0) / (1.25 * gh)), 1);
    const chars = lines * (x1 - x0) / (0.45 * gh);
    return Math.trunc(Math.max(floor, Math.min(cap, Math.ceil(chars * perChar * margin))));
  } finally { g.delete(); }
}

// det 박스에 덮이지 않은 잉크 비율: 잉크 덩어리(면적>=12, 높이>=6, inkTight 와 같은 기준) 중심이 어떤 det 박스에도 없으면 미커버
export function uncoveredInk(crop, boxes) {
  const cv = getCv();
  const g = new cv.Mat();
  cv.cvtColor(crop, g, cv.COLOR_BGR2GRAY);
  const H = g.rows, W = g.cols;
  const gd = new Uint8Array(g.data);
  g.delete();
  const bg = percentileU8(histU8(gd), gd.length, 80);
  const m = new cv.Mat(H, W, cv.CV_8UC1);
  m.data.set(gd.map((v) => ((bg - v) > 70 ? 1 : 0)));
  const lab = new cv.Mat(), st = new cv.Mat(), cen = new cv.Mat();
  const n = cv.connectedComponentsWithStats(m, lab, st, cen, 8, cv.CV_32S);
  const sd = new Int32Array(st.data32S);
  m.delete(); lab.delete(); st.delete(); cen.delete();
  let tot = 0, unc = 0;
  for (let i = 1; i < n; i++) {
    const a = sd[i * 5 + 4];
    if (a < 12 || sd[i * 5 + 3] < 6) continue;
    const cx = sd[i * 5] + sd[i * 5 + 2] / 2, cy = sd[i * 5 + 1] + sd[i * 5 + 3] / 2;
    tot += a;
    if (!(boxes || []).some((b) => cx >= b[0] && cx <= b[2] && cy >= b[1] && cy <= b[3])) unc += a;
  }
  return tot ? unc / tot : 0;
}

// ---- 규칙 (feat: {kind,text,conf,fallback,w,h,nlines,rs,cs}) ----
const T_HANGUL = /[\uac00-\ud7a3]/;
export const RULES = {
  empty: (f) => f.text === '',                                               // 잉크가 있는데 읽은 글자가 없다
  han: (f) => HAN.test(f.text),                                              // CJK 한자(한국 학교 문서에서는 거의 오독)
  digit_hangul: (f) => /[0-9]-[\uac00-\ud7a3]|[0-9][기이]/.test(f.text),             // 숫자 사이/옆에 낀 한글: '2-기'(2-7 오독), '2-1이'(2-10 오독). 7->기, 0->이 같은 모양 혼동
  digit_hangul_any: (f) => /[0-9][\uac00-\ud7a3]|[\uac00-\ud7a3][0-9]/.test(f.text),   // (비채택) 숫자와 한글이 붙기만 해도: '2교시' 같은 정상 글자에도 걸려 정밀도 15%
  low_conf: (f, p) => f.conf < (f.kind === 'block' ? p.confMinBlock : p.confMin),                                    // rec 최소 확률이 낮다
  fallback: (f) => f.fallback,                                               // det 가 글자를 못 찾아 줄분할 폴백
  long: (f, p) => f.text.replace(/\s/g, '').length >= p.longLen,             // 긴 칸
  multiline: (f) => f.nlines >= 2,
  paren: (f) => (f.text.match(/\(/g) || []).length !== (f.text.match(/\)/g) || []).length,   // 괄호 짝이 안 맞는다
  sparse: (f, p) => { const n = [...f.text.replace(/\s/g, '')].length; return f.units > 0 && !f.fallback && n > 0 && n / f.units < p.coverMin; },   // det 박스 폭에 비해 읽은 글자가 모자란다(글자 누락: '퇴근'->'퇴')
  uncovered: (f, p) => (f.uncov ?? 0) > p.uncovMax,                           // det 가 놓친 잉크가 있다                                           // 여러 줄 칸
};
export const DEFAULT_PARAMS = { confMin: 0.8, confMinBlock: 0.95, longLen: 20, uncovMax: 0.05, coverMin: 0.75, enabled: ['empty', 'han', 'digit_hangul', 'paren', 'fallback', 'sparse', 'low_conf'] };

export function makeSuspect(params = {}) {
  const p = { ...DEFAULT_PARAMS, ...params };
  return {
    params: p,
    judge(f) {
      const reasons = p.enabled.filter((k) => RULES[k](f, p));
      return { suspect: reasons.length > 0, reasons };
    },
  };
}
