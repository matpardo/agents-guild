const fs = require("fs");
const vm = require("vm");
const [src, dataFile, partyF, raidF, outId = "drift", mode = "text"] = process.argv.slice(2);
const data = JSON.parse(fs.readFileSync(dataFile, "utf8"));
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
const byId = {};
const doc = {
  getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
  createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
  addEventListener: (n, f) => { doc.h = f; },
  activeElement: null, querySelector: () => null, querySelectorAll: () => [],
};
const ctx = { document: doc, window: {}, console, setInterval() {}, setTimeout() {},
  fetch: (url) => Promise.resolve({ json: () => Promise.resolve(url === "/api/board" ? data : { token: "t" }) }) };
ctx.window = ctx;
vm.createContext(ctx);
vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
doc.h();
setTimeout(() => {
  doc.getElementById("party-filter").value = partyF;
  doc.getElementById("raid-filter").value = raidF;
  doc.getElementById("party-filter").h.change({ target: { value: partyF } });
  doc.getElementById("raid-filter").h.change({ target: { value: raidF } });
  const tree = (n) => ({ tag: n.tag, className: n.className || "", type: n.type || "", placeholder: n.placeholder || "", text: n._text, children: n.children.map(tree) });
  setTimeout(() => {
    const out = doc.getElementById(outId);
    console.log(mode === "tree" ? JSON.stringify(tree(out)) : out.textContent);
    process.exit(0);
  }, 50);
}, 50);
