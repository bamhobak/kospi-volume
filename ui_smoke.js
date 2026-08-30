// index.html 의 스크립트를 최소 DOM 스텁으로 실행해 탭별 render() 런타임 오류를 잡는다.
// 사용: node ui_smoke.js
const fs = require('fs');
const html = fs.readFileSync('index.html', 'utf8');
const T = JSON.parse(fs.readFileSync('site/data/table.json', 'utf8'));

const mkEl = () => ({ innerHTML: '', textContent: '', style: {}, dataset: {},
  onclick: null, classList: { add() {}, remove() {}, toggle() {} },
  querySelectorAll: () => [], querySelector: () => null, appendChild() {}, addEventListener() {} });
const doc = {
  querySelector: () => mkEl(), querySelectorAll: () => [],
  getElementById: () => mkEl(), createElement: () => mkEl(),
  addEventListener() {}, body: mkEl(), documentElement: mkEl(),
};
global.document = doc;
global.window = { addEventListener() {}, location: { href: '', search: '' }, matchMedia: () => ({ matches: false, addEventListener() {} }) };
global.localStorage = { _d: {}, getItem(k) { return this._d[k] ?? null }, setItem(k, v) { this._d[k] = String(v) }, removeItem(k) { delete this._d[k] } };
global.fetch = () => Promise.resolve({ json: () => Promise.resolve({}), ok: true });
global.alert = () => {}; global.confirm = () => true; global.prompt = () => null;

// <script> 본문만 추출 (외부 src 제외)
const scripts = [...html.matchAll(/<script(?![^>]*\bsrc=)[^>]*>([\s\S]*?)<\/script>/g)].map(m => m[1]);
const code = scripts.join('\n');

const vm = require('vm');
const ctx = vm.createContext(Object.assign({ console, document: doc, window: global.window,
  localStorage: global.localStorage, fetch: global.fetch, alert: global.alert,
  confirm: global.confirm, prompt: global.prompt, setTimeout, clearTimeout, JSON, Math, Date, Object, Array, String, Number }, {}));
try { vm.runInContext(code, ctx); } catch (e) {
  console.error('스크립트 로드 실패:', e.message); process.exit(1);
}

// 데이터 주입 — let/const 는 컨텍스트 프로퍼티가 아니므로 '안에서' 대입해야 한다
ctx.__T = T;
const rowsJs = T.rows.map(r => Object.assign({}, r, {
    ticker: r.t, name: r.n, close: r.c, change: r.ch, foreign_ratio: r.fr,
    vols: r.v, avg: 0, total: 0, ratio: 0, indiv: 0, organ: 0, frgn: 0,
    fw: (r.f || []).slice(-5).reduce((x, y) => x + (y || 0), 0),
    v5: (r.v || []).slice(-5).reduce((x, y) => x + (y || 0), 0),
    r16: (r.a1 && r.a6) ? r.a1 / r.a6 * 100 : null,
    rw1: (r.aw && r.a1) ? r.aw / r.a1 * 100 : null, last: -1, chpct: 0 }));
ctx.__rows = rowsJs;
vm.runInContext('raw = __T; view = {dates: __T.dates, rows: __rows}; live = {prices:{}, updated:""};', ctx);

let fail = 0;
for (const cur of ['all', 'pos', 'kp', 'kq', 1, 2, 3, 4]) {
  try {
    vm.runInContext(`cur = ${typeof cur === 'number' ? cur : JSON.stringify(cur)}; render()`, ctx);
    let n = '-';
    try { n = vm.runInContext('view.rows.filter(passes).length', ctx); } catch (e) { n = 'passes오류: ' + e.message }
    console.log(`  cur=${String(cur).padEnd(4)} render OK · passes ${n}건`);
  } catch (e) {
    fail++; console.log(`  cur=${String(cur).padEnd(4)} ✗ ${e.message}`);
  }
}
console.log(fail ? `\n실패 ${fail}건` : '\n전 탭 렌더 정상');
process.exit(fail ? 1 : 0);
