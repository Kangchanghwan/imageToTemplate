// 의심 칸 규칙 근거: 클라이언트 OCR 로그(ocr_client0)를 정답과 비교해 규칙별 재현율/정밀도/비율을 계산한다.
// 정답: PDF 6건/합성 12건은 칸 단위 GT(out/gt), 나머지(일정표 4, 서식 3)는 현행 서버 paddle 결과(회귀셋에서 100%)를 정답으로 대용.
// 사용: node tools/parity/suspect_eval.mjs <outdir> [--list] [--tag=client0]
import fs from 'node:fs';
import path from 'node:path';
import { root } from './node_common.mjs';
const { RULES, DEFAULT_PARAMS } = await import(path.join(root, 'web/src/suspect.js'));
const outdir = path.resolve(process.argv[2]);
const LIST = process.argv.includes('--list');
const tagArg = process.argv.find((a) => a.startsWith('--tag='));
const tag = tagArg ? tagArg.split('=')[1] : 'client0';
const norm = (s) => (s ?? '').replace(/\s+/g, '');
const names = JSON.parse(fs.readFileSync(path.join(outdir, 'manifest.json'), 'utf8')).inputs.map((i) => i.name);
const J = (f) => JSON.parse(fs.readFileSync(f, 'utf8'));
const data = [];
for (const name of names) {
  const lf = path.join(outdir, 'ocr_' + tag, name + '.log.json');
  if (!fs.existsSync(lf)) continue;
  const log = J(lf);
  const rec = J(path.join(outdir, 'spec_py', name + '_ocr.json'));
  const srv = new Map(rec.cells.map(([r, c, t]) => [r + ',' + c, t]));
  const gtf = path.join(outdir, 'gt', name + '.json');
  const gt = fs.existsSync(gtf) ? new Map(J(gtf).map(([r, c, rs, cs, t]) => [[r, c, rs, cs].join(','), t])) : null;
  let bi = 0;
  for (const e of log) {
    let truth, src;
    if (e.kind === 'cell') {
      const k = [e.r, e.c, e.rs, e.cs].join(',');
      if (gt && gt.has(k)) { truth = gt.get(k); src = 'gt'; } else { truth = srv.get(e.r + ',' + e.c) ?? ''; src = 'srv'; }
    } else { truth = rec.blocks[bi++]?.text ?? ''; src = 'srv'; }
    data.push({ name, ...e, truth, src, wrong: norm(e.text) !== norm(truth) });
  }
}
const cells = data.filter((d) => d.kind === 'cell'), blocks = data.filter((d) => d.kind === 'block');
const out = [];
const P = (s) => { out.push(s); console.log(s); };
P(`## 클라이언트 OCR 단독 (정답 대비) — 칸 ${cells.length}개, 블록 ${blocks.length}개`);
const wc = cells.filter((d) => d.wrong), wb = blocks.filter((d) => d.wrong);
P(`칸 오류 ${wc.length}/${cells.length} (${(100 * (1 - wc.length / cells.length)).toFixed(2)}% 일치), 블록 오류 ${wb.length}/${blocks.length}`);
if (LIST) for (const d of [...wc, ...wb]) P(`  ${d.name} ${d.kind} r${d.r ?? d.index} c${d.c ?? ''} [${d.src}] 정답=${JSON.stringify(d.truth)} 읽음=${JSON.stringify(d.text)} conf=${d.conf.toFixed(3)} fb=${d.fallback} nl=${d.nlines}`);
const confs = [0.8, 0.9, 0.95, 0.97, 0.99];
const evalRule = (label, pred, set) => {
  const fl = set.filter(pred), tp = fl.filter((d) => d.wrong).length, bad = set.filter((d) => d.wrong).length;
  return `| ${label} | ${fl.length} (${(100 * fl.length / set.length).toFixed(1)}%) | ${tp}/${bad} (${bad ? (100 * tp / bad).toFixed(0) : '-'}%) | ${fl.length ? (100 * tp / fl.length).toFixed(0) : '-'}% |`;
};
const P0 = { ...DEFAULT_PARAMS };
for (const [title, set] of [['칸', cells], ['블록', blocks]]) {
  P(`\n### ${title}: 규칙별 (플래그 수 / 오류 재현율 / 정밀도)`);
  P('| 규칙 | 의심(전체 대비) | 재현율(잡은 오류/전체 오류) | 정밀도 |');
  P('|---|---|---|---|');
  for (const [k, f] of Object.entries(RULES)) {
    if (k === 'low_conf') { for (const c of confs) P(evalRule(`low_conf conf<${c}`, (d) => f(d, { ...P0, confMin: c }), set)); }
    else if (k === 'long') P(evalRule('long (공백 제외 20자 이상)', (d) => f(d, { ...P0, longLen: 20 }), set));
    else P(evalRule(k, (d) => f(d, P0), set));
  }
}
// 조합
const B5 = ['empty', 'han', 'digit_hangul', 'paren', 'fallback', 'sparse'];
const combos = [
  ['empty+han+digit_hangul+paren+fallback+sparse', B5, 0],
  ['위 + low_conf<0.8', [...B5, 'low_conf'], 0.8],
  ['위 + low_conf<0.9', [...B5, 'low_conf'], 0.9],
  ['위 + low_conf<0.95', [...B5, 'low_conf'], 0.95],
  ['위 + low_conf<0.97', [...B5, 'low_conf'], 0.97],
  ['위 + low_conf<0.99', [...B5, 'low_conf'], 0.99],
  ['위(0.9) + multiline', [...B5, 'low_conf', 'multiline'], 0.9],
  ['위(0.9) + long', [...B5, 'low_conf', 'long'], 0.9],
  ['위(0.9) + uncovered>5%', [...B5, 'low_conf', 'uncovered'], 0.9],
  ['**채택**: 위 + low_conf(칸<' + DEFAULT_PARAMS.confMin + ', 블록<' + DEFAULT_PARAMS.confMinBlock + ')', DEFAULT_PARAMS.enabled, 'adopt'],
];
for (const [title, set] of [['칸', cells], ['블록', blocks]]) {
  P(`\n### ${title}: 조합`);
  P('| 조합 | 의심(전체 대비) | 재현율 | 정밀도 |');
  P('|---|---|---|---|');
  for (const [l, en, cm] of combos) P(evalRule(l, (d) => en.some((k) => RULES[k](d, cm === 'adopt' ? P0 : { ...P0, confMin: cm, confMinBlock: cm })), set));
}
// 오류 칸이 어떤 규칙에 걸리는지, 놓친 오류
const chosen = DEFAULT_PARAMS.enabled;
const param = { ...P0 };
P(`\n### 오류 칸 상세 (채택 규칙: ${chosen.join(',')}, 칸 conf<${param.confMin}, 블록 conf<${param.confMinBlock})`);
for (const d of [...wc, ...wb]) {
  const r = chosen.filter((k) => RULES[k](d, param));
  P(`  ${d.name} ${d.kind} ${d.kind === 'cell' ? 'r' + d.r + 'c' + d.c : '#' + d.index}: ${JSON.stringify(d.truth)} <- ${JSON.stringify(d.text)} conf=${d.conf.toFixed(3)} 걸린 규칙=${r.join('+') || '없음(놓침)'}`);
}
fs.writeFileSync(path.join(outdir, 'suspect_eval.md'), out.join('\n') + '\n');
