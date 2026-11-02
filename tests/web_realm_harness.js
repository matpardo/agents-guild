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
  o.appendChild = (c) => { o.children.push(c); if (tag === "select") o.options.push(c); return c; };
  o.removeChild = (c) => { o.options = o.options.filter((x) => x !== c); o.children = o.children.filter((x) => x !== c); };
  o.setAttribute = () => {};
  o.addEventListener = (n, f) => { (o.h = o.h || {})[n] = f; };
  o.focus = () => {};
  Object.defineProperty(o, "firstChild", { get() { return o.children[0] || null; } });
  return o;
}
function findButtons(node, label) {
  const found = node.tag === "button" && node._text === label ? [node] : [];
  return found.concat(...node.children.map((child) => findButtons(child, label)));
}
function findButton(node) {
  return findButtons(node, "Refresh")[0] || null;
}
function hasClass(node, name) {
  if ((node.className || "").split(" ").includes(name)) return true;
  return node.children.some((child) => hasClass(child, name));
}
const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
async function run({ src, realm, refresh, clicks, replies, guild_name }) {
  const posts = [];
  const byId = {};
  const doc = {
    getElementById: (id) => (byId[id] = byId[id] || mk(id.endsWith("-filter") ? "select" : "div")),
    createElement: mk, createTextNode: (t) => { const n = mk("#text"); n._text = t; return n; },
    addEventListener: (n, f) => { doc.h = f; },
    activeElement: null, querySelector: () => null, querySelectorAll: () => [],
  };
  const board = { generated_at: "now", parties: [], raids: [], asks: [], blocked: [], notices: [], projects: [],
    memory: [], merge_queues: [], drift: [], ready_for_you: [], ideas: [], adventurers: [], health_jobs: [], solo_players: [], solo_pending: [],
    project_names: [], bases: [], quest_boards: [], new_notice_count: 0, realm, guild_name };
  function respond(body, ok) {
    return Promise.resolve({ ok, json: () => Promise.resolve(body) });
  }
  function fetchStub(url) {
    if (url === "/api/board") return respond(board, true);
    if (url === "/api/realm/refresh") return respond(refresh.body, refresh.ok);
    if (url.startsWith("/api/realm/")) posts.push(url);
    const reply = (replies || {})[url];
    return reply ? respond(reply.body, reply.ok) : respond({}, false);
  }
  const ctx = { document: doc, window: {}, location: { hash: "#t=t", pathname: "/", search: "" }, history: { replaceState() {} }, addEventListener() {}, console, setInterval() {}, setTimeout() {}, fetch: fetchStub, confirm: () => true };
  ctx.window = ctx;
  ctx.Date = Date;
  vm.createContext(ctx);
  vm.runInContext(fs.readFileSync(src, "utf8"), ctx);
  doc.h();
  await wait(30);
  const section = doc.getElementById("realm");
  if (refresh) {
    findButton(section).h.click();
    await wait(30);
  }
  for (const click of clicks || []) {
    findButtons(section, click.label)[click.index].h.click();
    await wait(30);
  }
  return { posts, title: doc.getElementById("board-title").textContent, text: section.textContent, red: hasClass(section, "res-bad"), hasButton: findButton(section) !== null };
}
readline.createInterface({ input: process.stdin }).on("line", async (line) => {
  console.log(JSON.stringify(await run(JSON.parse(line))));
});
