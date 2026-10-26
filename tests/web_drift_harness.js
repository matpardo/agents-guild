const fs = require("fs");
const readline = require("readline");
const vm = require("vm");
function mk(tag) {
  const o = { tag, children: [], _text: "", value: "all", options: [], style: {}, dataset: {}, attrs: {},
    classList: { add() {}, remove() {}, toggle() {}, contains() { return false; } } };
  Object.defineProperty(o, "textContent", {
    get() { return o._text + o.children.map((c) => c.textContent).join(" "); },
    set(v) { o._text = v; o.children = []; o.options = []; },
  });
  o.appendChild = (c) => { o.children.push(c); if (tag === "select") o.options.push(c);  return c; };
  o.removeChild = (c) => { o.options = o.options.filter((x) => x !== c); o.children = o.children.filter((x) => x !== c); };
  o.setAttribute = () => {};
  o.addEventListener = (n, f) => { (o.h = o.h || {})[n] = f; };
  o.focus = () => {};
  Object.defineProperty(o, "firstChild", { get() { return o.children[0] || null; } });
  return o;
}
const tree = (n) => ({ tag: n.tag, className: n.className || "", type: n.type || "", placeholder: n.placeholder || "", title: n.title || "", text: n._text, children: n.children.map(tree) });
const tick = () => new Promise((resolve) => setImmediate(resolve));
async function render({ src, data, hash, outId, mode }) {
  const byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  };
  const ctx = { document: doc, window: {}, location: { hash }, addEventListener(n, f) { ctx.hashchange = f; }, console, setInterval() {}, setTimeout() {},
    fetch: (url) => Promise.resolve({ json: () => Promise.resolve(url === "/api/board" ? data : { token: "t" }) }) };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await tick();
  await tick();
  const out = doc.getElementById(outId);
  if (mode === "hidden") return JSON.stringify(Object.keys(byId).filter((id) => byId[id].hidden === true).sort());
  return mode === "tree" ? JSON.stringify(tree(out)) : out.textContent;
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await render(JSON.parse(line))));
});
