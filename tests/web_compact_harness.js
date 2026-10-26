const fs = require("fs");
const vm = require("vm");
const readline = require("readline");
function mk(tag) {
  const o = { tag, children: [], _text: "", value: "all", options: [], style: {}, dataset: {}, attrs: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } } };
  Object.defineProperty(o, "textContent", {
    get() { return o._text + o.children.map((c) => c.textContent).join(" "); },
    set(v) { o._text = v; o.children = []; o.options = []; },
  });
  o.appendChild = (c) => { o.children.push(c); if (tag === "select") o.options.push(c); return c; };
  o.removeChild = (c) => { o.options = o.options.filter((x) => x !== c); o.children = o.children.filter((x) => x !== c); };
  o.setAttribute = () => {};
  o.addEventListener = (n, f) => { (o.h = o.h || {})[n] = f; };
  o.focus = () => {};
  Object.defineProperty(o, "firstChild", { get() { return o.children[0] || null; } });
  return o;
}
function findButton(node) {
  if (node.tag === "button" && node._text === "Compact db") return node;
  for (const child of node.children) {
    const found = findButton(child);
    if (found) return found;
  }
  return null;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function run({ src, scenario }) {
  const byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  };
  let resourcesCalls = 0;
  const board = { generated_at: "now", parties: [], raids: [], asks: [], blocked: [], notices: [], projects: [],
    memory: [], merge_queues: [], drift: [], answered_asks: [] };
  const machine = { sampled_at: "t", disk_percent: null, mem_available: null, docker: null,
    load_per_core: null, guild_db_bytes: 0, untracked_growth: null };
  function respond(body, ok) {
    return Promise.resolve({ ok, json: () => Promise.resolve(body) });
  }
  function fetchStub(url, options) {
    if (url === "/api/board") return respond(board, true);
    if (url === "/api/session") return respond({ token: "t" }, true);
    if (url === "/api/compact") {
      return new Promise((resolve, reject) => setTimeout(() => {
        if (scenario === "dropped") return reject(new Error("connection reset"));
        return resolve({ ok: true, json: () => Promise.resolve({ ok: true, message: "backup done\nvacuum done" }) });
      }, 10));
    }
    resourcesCalls += 1;
    if (resourcesCalls <= 2) return respond({ machine, since: "1d", projects: [], unattributed: null }, true);
    return respond({ error: "database is locked" }, false);
  }
  const ctx = { document: doc, window: {}, location: { hash: "" }, addEventListener() {}, console, setInterval() {}, setTimeout() {}, fetch: fetchStub };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await wait(50);
  findButton(doc.getElementById("resources")).h.click();
  await wait(50);
  const after = findButton(doc.getElementById("resources"));
  return { disabled: after.disabled, text: doc.getElementById("resources").textContent };
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await run(JSON.parse(line))));
});
