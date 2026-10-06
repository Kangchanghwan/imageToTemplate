import test from 'node:test';
import assert from 'node:assert/strict';
import { pyRound, pyRoundN, arange, median, percentileSorted, lstsq } from '../src/npy.js';

test('pyRound = Python round() (banker)', () => {
  assert.deepEqual([0.5, 1.5, 2.5, 246.5, 611.5, 1868.5, 2.4, 2.6].map(pyRound), [0, 2, 2, 246, 612, 1868, 2, 3]);
});
test('pyRoundN = Python round(x, 1)', () => {
  assert.equal(pyRoundN(0.25, 1), 0.2);   // 정확한 중간값 -> 짝수
  assert.equal(pyRoundN(0.35, 1), 0.3);   // 0.35 = 0.34999999999999997
  assert.equal(pyRoundN(280.0, 1), 280);
});
test('arange 는 numpy 와 같은 원소/길이', () => {
  const a = arange(0.01, 0.1, 0.005), b = arange(0.01, 0.12, 0.005);
  assert.equal(a.length, 18); assert.equal(b.length, 22);
  assert.equal(a[2], 0.019999999999999997); assert.equal(a[17], 0.09499999999999999); assert.equal(b[21], 0.11499999999999998);
});
test('median', () => {
  assert.equal(median([3, 1, 2]), 2); assert.equal(median([4, 1, 2, 3]), 2.5);
});
test('percentile 90 of 0..63 = 56.7', () => {
  const s = Float64Array.from({ length: 64 }, (_, i) => i);
  assert.ok(Math.abs(percentileSorted(s, 90) - 56.7) < 1e-12);
});
test('lstsq 가 정확한 관계를 복원', () => {
  const A = [], y = [];
  for (let i = 0; i < 30; i++) { const x = i / 10; A.push([1, x, x * x]); y.push(2 + 3 * x - 0.5 * x * x); }
  const c = lstsq(A, y);
  assert.ok(Math.abs(c[0] - 2) < 1e-9 && Math.abs(c[1] - 3) < 1e-9 && Math.abs(c[2] + 0.5) < 1e-9);
});
