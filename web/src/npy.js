// numpy / Python 내장 의미를 맞추기 위한 도우미.

// Python round(x) (ndigits 없음): 가장 가까운 정수, 정확히 .5 면 짝수 (banker's rounding)
export function pyRound(x) {
  const f = Math.floor(x);
  const d = x - f;
  if (d < 0.5) return f;
  if (d > 0.5) return f + 1;
  return f % 2 === 0 ? f : f + 1;
}

// Python round(x, nd): 정확한 십진 값 기준 반올림, 정확히 중간이면 짝수. (toFixed 는 정확한 값 기준이나 중간이면 올림)
export function pyRoundN(x, nd) {
  // toFixed 는 정확한 이진 값 기준(정확히 중간이면 올림). 정확한 중간값은 긴 자릿수 전개로 판별해 짝수로 보낸다.
  const long = Math.abs(x).toFixed(Math.min(100, nd + 30));
  const tail = long.slice(long.length - 30);
  if (/^50*$/.test(tail)) {
    const p = 10 ** nd;
    const lo = Math.floor(Math.abs(x) * p);   // 내림값(정확한 중간이므로 곱셈 오차 없음)
    const n = lo % 2 === 0 ? lo : lo + 1;
    return Math.sign(x) * n / p;
  }
  return Number(x.toFixed(nd));
}

// Python int(x): 0 방향 절삭
export const pyInt = (x) => Math.trunc(x);

// numpy arange(start, stop, step) (float): len=ceil((stop-start)/step), delta=(start+step)-start, v[i]=start+i*delta
export function arange(start, stop, step) {
  const delta = (start + step) - start;
  const n = Math.ceil((stop - start) / step);   // 길이는 step 기준(numpy: _calc_length), 값은 delta 기준
  const out = [];
  for (let i = 0; i < n; i++) out.push(start + i * delta);
  return out;
}

// numpy float64 pairwise sum (n<8 순차, <=128 은 8개 누산기, 그 이상 재귀 이분)
export function npSum(a, lo = 0, n = a.length) {
  if (n < 8) {
    let res = 0;
    for (let i = 0; i < n; i++) res += a[lo + i];
    return res;
  }
  if (n <= 128) {
    const r = [];
    for (let k = 0; k < 8; k++) r.push(a[lo + k]);
    let i;
    for (i = 8; i < n - (n % 8); i += 8) for (let k = 0; k < 8; k++) r[k] += a[lo + i + k];
    let res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
    for (; i < n; i++) res += a[lo + i];
    return res;
  }
  let n2 = Math.floor(n / 2);
  n2 -= n2 % 8;
  return npSum(a, lo, n2) + npSum(a, lo + n2, n - n2);
}

// np.median (float64 입력): 정렬 후 중앙(짝수면 두 값 평균)
export function median(arr) {
  const s = Float64Array.from(arr).sort();
  const n = s.length;
  if (n === 0) return NaN;
  return n % 2 ? s[(n - 1) / 2] : (s[n / 2 - 1] + s[n / 2]) / 2;
}

// 같은 길이 정수 배열(uint8 값) 중앙값 — 히스토그램 방식
export function medianU8(vals /* array-like of 0..255 */) {
  const hist = new Int32Array(256);
  for (let i = 0; i < vals.length; i++) hist[vals[i]]++;
  const n = vals.length;
  const kth = (k) => { let c = 0; for (let v = 0; v < 256; v++) { c += hist[v]; if (c > k) return v; } return 255; };
  return n % 2 ? kth((n - 1) / 2) : (kth(n / 2 - 1) + kth(n / 2)) / 2;
}

// np.percentile(q=90, 선형 보간) — 정렬된 float 배열. 계산은 float64 후 호출측에서 float32 로 저장
export function percentileSorted(s, q) {
  const n = s.length;
  const vi = (n - 1) * (q / 100);
  const prev = Math.floor(vi);
  const next = Math.min(prev + 1, n - 1);
  const t = vi - prev;
  const a = s[prev], b = s[next];
  const d = b - a;
  return t >= 0.5 ? b - d * (1 - t) : a + d * t;
}

// 안정 argsort (JS Array.prototype.sort 는 안정)
export function argsort(a) {
  return Array.from(a.keys()).sort((i, j) => (a[i] < a[j] ? -1 : a[i] > a[j] ? 1 : 0));
}

// 열 우선 최소제곱 (Householder QR, float64). A: n x m (행 배열), y: n. numpy lstsq(rcond=None) 와 같은 해(풀랭크일 때)
export function lstsq(A, y) {
  const n = A.length, m = A[0].length;
  const Q = A.map((r) => Float64Array.from(r));
  const b = Float64Array.from(y);
  for (let k = 0; k < m; k++) {
    let nrm = 0;
    for (let i = k; i < n; i++) nrm += Q[i][k] * Q[i][k];
    nrm = Math.sqrt(nrm);
    const alpha = Q[k][k] > 0 ? -nrm : nrm;
    const v = new Float64Array(n - k);
    for (let i = k; i < n; i++) v[i - k] = Q[i][k];
    v[0] -= alpha;
    let vv = 0;
    for (let i = 0; i < v.length; i++) vv += v[i] * v[i];
    if (vv === 0) continue;
    for (let j = k; j < m; j++) {
      let s = 0;
      for (let i = k; i < n; i++) s += v[i - k] * Q[i][j];
      s = 2 * s / vv;
      for (let i = k; i < n; i++) Q[i][j] -= s * v[i - k];
    }
    let s = 0;
    for (let i = k; i < n; i++) s += v[i - k] * b[i];
    s = 2 * s / vv;
    for (let i = k; i < n; i++) b[i] -= s * v[i - k];
  }
  const x = new Float64Array(m);
  for (let k = m - 1; k >= 0; k--) {
    let s = b[k];
    for (let j = k + 1; j < m; j++) s -= Q[k][j] * x[j];
    x[k] = s / Q[k][k];
  }
  return x;
}
