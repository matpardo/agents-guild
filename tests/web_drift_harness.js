const fs = require("fs");
const readline = require("readline");
const vm = require("vm");
let byId = {};
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
  Object.defineProperty(o, "id", { get() { return o._id; }, set(v) { o._id = v; byId[v] = o; } });
  Object.defineProperty(o, "firstChild", { get() { return o.children[0] || null; } });
  return o;
}
const tree = (n) => ({ tag: n.tag, className: n.className || "", type: n.type || "", value: n.value, placeholder: n.placeholder || "", title: n.title || "", text: n._text, children: n.children.map(tree) });
const tick = () => new Promise((resolve) => setImmediate(resolve));
const walk = (n) => [n].concat(...n.children.map(walk));
async function openDetails(root, summaries) {
  for (const node of walk(root)) {
    if (node.tag === "details" && node.children[0] && summaries.includes(node.children[0]._text)) {
      node.open = true;
      node.h.toggle();
      await tick();
      await tick();
    }
  }
}
async function render({ src, data, hash, outId, mode, responses, open }) {
  byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  };
  const ctx = { document: doc, window: {}, location: { hash }, addEventListener(n, f) { ctx.hashchange = f; }, console, setInterval() {}, setTimeout() {},
    fetch: (url) => Promise.resolve({ json: () => Promise.resolve(responses && url in responses ? responses[url] : url === "/api/board" ? data : { token: "t" }) }) };
  ctx.window = ctx;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await tick();
  await tick();
  const out = doc.getElementById(outId);
  if (open) await openDetails(out, open);
  if (mode === "hidden") return JSON.stringify(Object.keys(byId).filter((id) => byId[id].hidden === true).sort());
  return mode === "tree" ? JSON.stringify(tree(out)) : out.textContent;
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await render(JSON.parse(line))));
});
