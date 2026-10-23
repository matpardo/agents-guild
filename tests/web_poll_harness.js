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
  o.focus = () => { o.focused = true; };
  o.setSelectionRange = (start, end) => { o.selection = [start, end]; };
  Object.defineProperty(o, "firstChild", { get() { return o.children[0] || null; } });
  return o;
}
function matches(node, selector) {
  if (selector === "[data-focus-key]") return node.dataset.focusKey !== undefined;
  const [tag, cls] = selector.split(".");
  return node.tag === tag && (node.className || "").split(" ").indexOf(cls) !== -1;
}
function walk(node, selector, found) {
  if (matches(node, selector)) found.push(node);
  node.children.forEach((child) => walk(child, selector, found));
  return found;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function run({ src, scenario }) {
  const byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null,
    querySelectorAll: (selector) => Object.values(byId).reduce((found, root) => walk(root, selector, found), []),
  };
  const idea = { id: 1, title: "Dark mode", description: "night owls", requester: null, deadline: null,
    project: null, overdue: false, parties: [] };
  let board = { generated_at: "now", parties: [], raids: [], asks: [], blocked: [], notices: [], projects: [],
    memory: [], merge_queues: [], drift: [], ready_for_you: [], ideas: [], adventurers: [], health_jobs: [], project_names: [] };
  const intervals = [];
  const ctx = { document: doc, window: {}, console, setTimeout,
    setInterval(fn) { intervals.push(fn); },
    fetch: (url) => Promise.resolve({ ok: true, json: () => Promise.resolve(url === "/api/board" ? board : { token: "t" }) }) };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await wait(50);
  function titleInput() {
    return walk(doc.getElementById("ideas"), "input.idea-title", [])[0];
  }
  const before = titleInput();
  before.value = "half typed";
  before.h.input();
  before.selectionStart = 4;
  before.selectionEnd = 4;
  doc.activeElement = before;
  board = Object.assign({}, board, { generated_at: "later", ideas: scenario === "changed" ? [idea] : [] });
  intervals.forEach((fn) => fn());
  await wait(50);
  const after = titleInput();
  return { sameNode: after === before, focused: after.focused === true,
    selection: after.selection || null, value: after.value };
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await run(JSON.parse(line))));
});
