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
function pills(node, found) {
  if ((node.className || "").split(" ").indexOf("pill") !== -1) found.push({ text: node.textContent, cls: node.className });
  node.children.forEach((child) => pills(child, found));
  return found;
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function run({ src, model }) {
  const byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  };
  const board = { generated_at: "now", parties: [], raids: [], asks: [], blocked: [], notices: [], projects: [],
    memory: [], merge_queues: [], drift: [], answered_asks: [] };
  function fetchStub(url) {
    const body = url === "/api/board" ? board : model;
    return Promise.resolve({ ok: true, json: () => Promise.resolve(body) });
  }
  const ctx = { document: doc, window: {}, location: { hash: "#t=t", pathname: "/", search: "" }, history: { replaceState() {} }, addEventListener() {}, console, setInterval() {}, setTimeout() {}, fetch: fetchStub };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await wait(50);
  return { resources: pills(doc.getElementById("resources"), []), sidebar: pills(doc.getElementById("sidebar-resources"), []) };
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await run(JSON.parse(line))));
});
