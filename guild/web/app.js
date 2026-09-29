(function () {
  "use strict";

  var REFRESH_INTERVAL_MS = 15000;
  var BOARD_URL = "/api/board";

  var state = {
    partyFilter: "all",
    stateFilter: "all",
    openParties: {},
    openContexts: {},
  };

  function el(tag) {
    return document.createElement(tag);
  }

  function textEl(tag, value) {
    var node = el(tag);
    node.textContent = value;
    return node;
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function appendAll(node, children) {
    children.forEach(function (child) {
      node.appendChild(child);
    });
  }

  function partyOpen(name) {
    return state.openParties[name] !== false;
  }

  function contextOpen(id) {
    return state.openContexts[id] === true;
  }

  function link(href, label) {
    var anchor = el("a");
    anchor.href = href;
    anchor.textContent = label;
    anchor.target = "_blank";
    anchor.rel = "noopener noreferrer";
    return anchor;
  }

  function blocksText(ask) {
    if (ask.blocked > 0) {
      return "blocks: " + ask.blocked + " of " + ask.total_refs + " refs still open";
    }
    return "blocks: 0 of " + ask.total_refs + " refs still open (may be stale)";
  }

  function renderAsk(ask) {
    var article = el("article");
    article.className = "card ask";

    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("span", "#" + ask.id));
    head.appendChild(textEl("span", ask.party));
    head.appendChild(textEl("strong", ask.question));
    article.appendChild(head);

    if (ask.options.length > 0) {
      article.appendChild(textEl("p", "options: " + ask.options.join(" | ")));
    }
    article.appendChild(textEl("p", "refs: " + ask.refs.join(", ")));
    article.appendChild(textEl("p", blocksText(ask)));

    var details = el("details");
    details.open = contextOpen(ask.id);
    details.appendChild(textEl("summary", "context"));
    details.appendChild(textEl("p", ask.context));
    details.addEventListener("toggle", function () {
      state.openContexts[ask.id] = details.open;
    });
    article.appendChild(details);

    return article;
  }

  function renderAsks(asks) {
    var section = document.getElementById("asks");
    clear(section);
    section.appendChild(textEl("h2", "asks (" + asks.length + ")"));
    if (asks.length === 0) {
      section.appendChild(textEl("p", "nothing needs you"));
      return;
    }
    appendAll(section, asks.map(renderAsk));
  }

  function renderNotice(notice) {
    var article = el("article");
    article.className = "card notice";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("span", "#" + notice.id));
    head.appendChild(textEl("span", notice.party || "human"));
    head.appendChild(textEl("span", notice.scope));
    article.appendChild(head);
    article.appendChild(textEl("p", notice.text));
    return article;
  }

  function renderNotices(notices) {
    var section = document.getElementById("notices");
    clear(section);
    section.appendChild(textEl("h2", "notices (" + notices.length + ")"));
    appendAll(section, notices.map(renderNotice));
  }

  function renderDriftEntry(entry) {
    var article = el("article");
    article.className = "card drift";
    article.appendChild(textEl("h3", entry.project));
    article.appendChild(textEl("p", entry.scope));
    var ruleNames = Object.keys(entry.findings);
    if (ruleNames.length === 0) {
      article.appendChild(textEl("p", "no drift"));
      return article;
    }
    ruleNames.forEach(function (rule) {
      var findings = entry.findings[rule];
      article.appendChild(textEl("h4", rule + " (" + findings.length + ")"));
      var list = el("ul");
      findings.forEach(function (finding) {
        list.appendChild(textEl("li", finding));
      });
      article.appendChild(list);
    });
    return article;
  }

  function renderDrift(drift) {
    var section = document.getElementById("drift");
    clear(section);
    section.appendChild(textEl("h2", "drift"));
    if (drift.length === 0) {
      section.appendChild(textEl("p", "no projects in scope"));
      return;
    }
    appendAll(section, drift.map(renderDriftEntry));
  }

  function prMatchesStateFilter(pr) {
    return state.stateFilter === "all" || pr.lifecycle === state.stateFilter;
  }

  function renderPr(pr) {
    var row = el("li");
    row.className = "pr";
    row.appendChild(link(pr.url, pr.repo + "#" + pr.number));
    row.appendChild(textEl("span", pr.lifecycle));
    row.appendChild(textEl("span", "checks ✗" + pr.checks_failing + " ✓" + pr.checks_passing));
    row.appendChild(textEl("span", pr.what));
    if (pr.waits) {
      row.appendChild(textEl("span", "waits: " + pr.waits));
    }
    return row;
  }

  function renderPrList(prs) {
    var visible = prs.filter(prMatchesStateFilter);
    if (visible.length === 0) {
      return null;
    }
    var list = el("ul");
    list.className = "pr-list";
    appendAll(list, visible.map(renderPr));
    return list;
  }

  function renderTask(task) {
    var item = el("li");
    item.className = "task task-" + task.state;
    var head = el("div");
    head.className = "task-head";
    head.appendChild(textEl("span", task.tid));
    head.appendChild(textEl("span", task.title));
    head.appendChild(textEl("span", task.state));
    if (task.card_url) {
      head.appendChild(link(task.card_url, task.tid + " card"));
    }
    item.appendChild(head);
    if (task.summary) {
      item.appendChild(textEl("p", task.summary));
    }
    if (task.blocked_reason) {
      item.appendChild(textEl("p", "blocked: " + task.blocked_reason));
    }
    var prList = renderPrList(task.prs);
    if (prList) {
      item.appendChild(prList);
    }
    return item;
  }

  function renderQuest(quest) {
    var article = el("div");
    article.className = "quest";
    article.appendChild(textEl("h4", quest.slug + " — " + quest.title));
    var list = el("ul");
    list.className = "task-list";
    appendAll(list, quest.tasks.map(renderTask));
    article.appendChild(list);
    return article;
  }

  function renderParty(party) {
    var details = el("details");
    details.className = "party";
    details.open = partyOpen(party.name);
    details.addEventListener("toggle", function () {
      state.openParties[party.name] = details.open;
    });

    var summary = el("summary");
    summary.appendChild(textEl("strong", party.name));
    summary.appendChild(textEl("span", party.state));
    summary.appendChild(textEl("span", "gen " + party.generation));
    summary.appendChild(textEl("span", party.leader_session_name || "no leader"));
    details.appendChild(summary);

    appendAll(details, party.quests.map(renderQuest));

    var orphanPrs = renderPrList(party.prs);
    if (orphanPrs) {
      details.appendChild(textEl("h4", "PRs outside active tasks"));
      details.appendChild(orphanPrs);
    }

    if (party.claims.length > 0) {
      var claimsText = party.claims
        .map(function (claim) {
          return claim.area;
        })
        .join(", ");
      details.appendChild(textEl("p", "claims: " + claimsText));
    }

    if (party.raids.length > 0) {
      var raidsText = party.raids
        .map(function (raid) {
          return raid.raid;
        })
        .join(", ");
      details.appendChild(textEl("p", "raids: " + raidsText));
    }

    return details;
  }

  function renderParties(parties) {
    var section = document.getElementById("parties");
    clear(section);
    section.appendChild(textEl("h2", "parties"));
    appendAll(section, parties.map(renderParty));
  }

  function option(value) {
    var node = el("option");
    node.value = value;
    node.textContent = value;
    return node;
  }

  function refreshPartyFilterOptions(parties) {
    var select = document.getElementById("party-filter");
    var previous = select.value;
    clear(select);
    select.appendChild(option("all"));
    parties.forEach(function (party) {
      select.appendChild(option(party.name));
    });
    var stillPresent = Array.prototype.some.call(select.options, function (option) {
      return option.value === previous;
    });
    select.value = stillPresent ? previous : "all";
    state.partyFilter = select.value;
  }

  function applyPartyFilter(data) {
    if (state.partyFilter === "all") {
      return data;
    }
    return {
      generated_at: data.generated_at,
      asks: data.asks.filter(function (ask) {
        return ask.party === state.partyFilter;
      }),
      notices: data.notices.filter(function (notice) {
        return notice.party === state.partyFilter;
      }),
      parties: data.parties.filter(function (party) {
        return party.name === state.partyFilter;
      }),
      drift: data.drift,
    };
  }

  function render(data) {
    document.getElementById("generated-at").textContent = "generated at " + data.generated_at;
    refreshPartyFilterOptions(data.parties);
    var filtered = applyPartyFilter(data);
    renderAsks(filtered.asks);
    renderNotices(filtered.notices);
    renderDrift(filtered.drift);
    renderParties(filtered.parties);
  }

  function fetchBoard() {
    fetch(BOARD_URL)
      .then(function (response) {
        return response.json();
      })
      .then(render)
      .catch(function () {});
  }

  document.addEventListener("DOMContentLoaded", function () {
    document.getElementById("party-filter").addEventListener("change", function (event) {
      state.partyFilter = event.target.value;
      fetchBoard();
    });
    document.getElementById("state-filter").addEventListener("change", function (event) {
      state.stateFilter = event.target.value;
      fetchBoard();
    });
    fetchBoard();
    setInterval(fetchBoard, REFRESH_INTERVAL_MS);
  });
})();
