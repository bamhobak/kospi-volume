/* 사이트(index.html)의 규칙 판정을 그대로 떼어 내 실행한다.
   지금까지 사이트·알림·백테스트의 조건을 '글자'로만 비교했는데, 오늘 여러 버그가
   그 사이를 빠져나갔다. 같은 데이터를 넣고 같은 답이 나오는지 실제로 돌려 봐야 한다.
   출력: {규칙id: [종목코드...]} 를 JSON 으로. selftest.py 가 읽는다. */
const fs = require('fs');
const H = fs.readFileSync('index.html', 'utf8');
const cut = (from, to) => { const a = H.indexOf(from); const b = H.indexOf(to, a + 1);
  if (a < 0 || b < 0) throw new Error('블록을 못 찾음: ' + from); return H.slice(a, b); };

const GATE_SRC = cut('const GATE={', 'const GATETXT=');
const FILT_SRC = cut('const FILTERS=', 'const LEGACY_ID');
const PREP_SRC = cut('function prep()', 'function val(');

const raw = JSON.parse(fs.readFileSync('site/data/table.json', 'utf8'));
const view = { rows: [], dates: [] };
const sandbox = { raw, view };
// 규칙 판정에 필요한 최소한만 주고 실행한다. 다른 전역을 참조하면 여기서 터지는데,
// 그것 자체가 신호다 — 규칙 판정이 화면 상태에 의존하고 있다는 뜻이기 때문이다.
const run = new Function('raw', 'view',
  GATE_SRC + '\n' + PREP_SRC + '\n' + FILT_SRC + '\n' +
  'prep();\n' +
  'const out={};\n' +
  'for(const f of FILTERS){ out[f.id]=view.rows.filter(r=>{try{return f.fn(r)}catch(e){return false}})' +
  '.map(r=>r.ticker).sort(); }\n' +
  'return {rules:out, meta:{rows:view.rows.length, dates:view.dates.length,' +
  ' ids:FILTERS.map(f=>f.id), mkt:Object.fromEntries(FILTERS.map(f=>[f.id,f.mkt||"KOSPI"])),' +
  ' hold:Object.fromEntries(FILTERS.map(f=>[f.id,(f.rule||{}).hold||null])),' +
  ' stop:Object.fromEntries(FILTERS.map(f=>[f.id,(f.rule||{}).stop??null]))}};');
process.stdout.write(JSON.stringify(run(raw, view)));
