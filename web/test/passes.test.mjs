import test from 'node:test';
import assert from 'node:assert/strict';
import { lev, cut, mostCommon, maj } from '../src/passes.js';
import { sizeFromInk, unifySizes } from '../src/style.js';
import { makeSuspect } from '../src/suspect.js';

test('lev', () => { assert.equal(lev('kitten', 'sitting'), 3); assert.equal(lev('', 'abc'), 3); });
test('cut: 줄바꿈 위치 복원', () => {
  assert.equal(cut('정보 수업 보조: 2교시 2-10(장현진), 3교시 2-9(장현진), 5교시 2-7(장현진)', ['정보수업보조:2교시2-10(장현진),3교시2-9(장현진),5교시2-7', 'x']), '정보 수업 보조: 2교시 2-10(장현진), 3교시 2-9(장현진), 5교시 2-7\n(장현진)');
  assert.equal(cut('abc', ['', 'x']), null);
});
test('mostCommon 은 동률이면 먼저 나온 값', () => { assert.deepEqual(mostCommon([2, 1, 1, 2, 3]), [[2, 2], [1, 2], [3, 1]]); });
test('maj', () => { assert.equal(maj([true, false]), false); assert.equal(maj([true, true, false]), true); });
test('sizeFromInk / unifySizes', () => {
  assert.ok(Math.abs(sizeFromInk(40, '가나', 10, null) - (4.0 / 0.88 * 72 / 25.4)) < 1e-9);
  assert.equal(unifySizes([10, 10.5]).get(10.5), 10);   // 중앙값 10.25 -> 0.5pt 반올림(은행가) = 10
});
test('의심 규칙', () => {
  const sp = makeSuspect();
  const base = { kind: 'cell', text: '2-기', conf: 0.99, fallback: false, units: 0, nlines: 1 };
  assert.deepEqual(sp.judge(base).reasons, ['digit_hangul']);
  assert.deepEqual(sp.judge({ ...base, text: '' }).reasons.includes('empty'), true);
  assert.ok(sp.judge({ ...base, text: '(서경' }).reasons.includes('paren'));
  assert.ok(sp.judge({ ...base, text: '退勤' }).reasons.includes('han'));
  assert.ok(sp.judge({ ...base, text: '퇴', units: 2.4 }).reasons.includes('sparse'));
  assert.equal(sp.judge({ ...base, text: '근무', conf: 0.99 }).suspect, false);
});
