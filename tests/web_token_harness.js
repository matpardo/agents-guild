const fs = require("fs");
const vm = require("vm");
const readline = require("readline");
function mk(tag) {
  const o = { tag, children: [], _text: "", value: "all", options: [], style: {}, dataset: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } } };
  Object.defineProperty(o, "textContent", {
    get() { return o._text; },
    set(v) { o._text = v; o.children = []; o.options = []; },
  });
  o.appendChild = (c) => c;
  o.removeChild = () => {};
  o.setAttribute = () => {};
  o.addEventListener = () => {};
  o.focus = () => {};
  Object.defineProperty(o, "firstChild", { get() { return null; } });
  return o;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function run({ src, hash, stored }) {
  const byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  };
  const getHeaders = [];
  const replaced = [];
  const saved = {};
  const sessionStorage = {
    getItem: (key) => (stored === null ? null : stored),
    setItem: (key, value) => { saved[key] = value; },
  };
  const board = { generated_at: "now", parties: [], raids: [], asks: [], blocked: [], notices: [], projects: [],
    memory: [], merge_queues: [], drift: [], answered_asks: [] };
  function fetchStub(url, options) {
    getHeaders.push(options.headers["X-Guild-Token"]);
    return Promise.resolve({ ok: true, json: () => Promise.resolve(url === "/api/board" ? board : {}) });
  }
  const ctx = { document: doc, window: {}, location: { hash, pathname: "/", search: "" }, sessionStorage,
    history: { replaceState: (state, title, url) => replaced.push(url) },
    addEventListener() {}, console, setInterval() {}, setTimeout() {}, fetch: fetchStub };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await wait(20);
  return { getHeaders, replaced, saved };
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await run(JSON.parse(line))));
});
