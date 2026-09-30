(function () {
  "use strict";

  var REFRESH_INTERVAL_MS = 15000;
  var BOARD_URL = "/api/board";
  var SESSION_URL = "/api/session";
  var EMPTY_ANSWER_MESSAGE = "write an answer first";
  var NO_SESSION_MESSAGE = "session token not loaded, reload the page";
  var sessionToken = null;

  var state = {
    partyFilter: "all",
    stateFilter: "all",
    raidFilter: "all",
    openParties: {},
    openContexts: {},
    drafts: {},
    statuses: {},
    busy: {},
    noticeStatuses: {},
    noticeBusy: {},
    noticeAllStatus: "",
    focusedAskId: null,
    focusStart: 0,
    focusEnd: 0,
  };

  function el(tag) {
    return document.createElement(tag);
  }

  function textEl(tag, value) {
    var node = el(tag);
    node.textContent = value;
    return node;
  }

  function classedText(tag, value, className) {
    var node = textEl(tag, value);
    node.className = className;
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

  function askUrl(askId, action) {
    return "/api/asks/" + askId + "/" + action;
  }

  function noticeUrl(noticeId, action) {
    return "/api/notices/" + noticeId + "/" + action;
  }

  function errorMessage(body) {
    if (body && typeof body.error === "string") {
      return body.error;
    }
    return "request failed";
  }

  function sendPost(url, payload) {
    return fetch(url, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Guild-Token": sessionToken,
      },
      body: JSON.stringify(payload),
    })
      .then(function (response) {
        return response.json().then(
          function (body) {
            return { ok: response.ok, body: body };
          },
          function () {
            return { ok: false, body: null };
          }
        );
      })
      .catch(function () {
        return { ok: false, body: null };
      });
  }

  function postNoticeAction(noticeId, action) {
    if (sessionToken === null) {
      state.noticeStatuses[noticeId] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.noticeBusy[noticeId] = true;
    state.noticeStatuses[noticeId] = "sending...";
    fetchBoard();
    sendPost(noticeUrl(noticeId, action), {}).then(function (result) {
      delete state.noticeBusy[noticeId];
      if (result.ok) {
        delete state.noticeStatuses[noticeId];
      } else {
        state.noticeStatuses[noticeId] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function postSeenAll() {
    if (sessionToken === null) {
      state.noticeAllStatus = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.noticeBusy.all = true;
    state.noticeAllStatus = "sending...";
    fetchBoard();
    sendPost("/api/notices/seen-all", {}).then(function (result) {
      delete state.noticeBusy.all;
      state.noticeAllStatus = result.ok ? "" : errorMessage(result.body);
      fetchBoard();
    });
  }

  function postAskAction(askId, action, payload) {
    if (sessionToken === null) {
      state.statuses[askId] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.busy[askId] = true;
    state.statuses[askId] = "sending...";
    fetchBoard();
    sendPost(askUrl(askId, action), payload).then(function (result) {
      delete state.busy[askId];
      if (result.ok) {
        delete state.drafts[askId];
        delete state.statuses[askId];
      } else {
        state.statuses[askId] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function submitAnswer(askId) {
    var text = state.drafts[askId] || "";
    if (text.trim() === "") {
      state.statuses[askId] = EMPTY_ANSWER_MESSAGE;
      fetchBoard();
      return;
    }
    postAskAction(askId, "answer", { answer: text });
  }

  function submitDismiss(askId) {
    if (!window.confirm("Dismiss ask #" + askId + "?")) {
      return;
    }
    postAskAction(askId, "dismiss", {});
  }

  function renderOptionButton(ask, optionText, area) {
    var button = textEl("button", optionText);
    button.type = "button";
    button.className = "option-button";
    button.disabled = state.busy[ask.id] === true;
    button.addEventListener("click", function () {
      state.drafts[ask.id] = optionText;
      area.value = optionText;
      area.focus();
    });
    return button;
  }

  function renderAnswerArea(ask) {
    var area = el("textarea");
    area.className = "answer-field";
    area.rows = 3;
    area.value = state.drafts[ask.id] || "";
    area.disabled = state.busy[ask.id] === true;
    area.dataset.askId = String(ask.id);
    area.addEventListener("input", function () {
      state.drafts[ask.id] = area.value;
    });
    return area;
  }

  function renderActionButton(ask, label, handler) {
    var button = textEl("button", label);
    button.type = "button";
    button.disabled = state.busy[ask.id] === true;
    button.addEventListener("click", handler);
    return button;
  }

  function renderAskControls(ask) {
    var controls = el("div");
    controls.className = "ask-controls";
    var area = renderAnswerArea(ask);
    if (ask.options.length > 0) {
      var choices = el("div");
      choices.className = "option-buttons";
      ask.options.forEach(function (optionText) {
        choices.appendChild(renderOptionButton(ask, optionText, area));
      });
      controls.appendChild(choices);
    }
    controls.appendChild(area);
    var actions = el("div");
    actions.className = "ask-actions";
    actions.appendChild(
      renderActionButton(ask, "Answer", function () {
        submitAnswer(ask.id);
      })
    );
    actions.appendChild(
      renderActionButton(ask, "Dismiss", function () {
        submitDismiss(ask.id);
      })
    );
    var status = textEl("span", state.statuses[ask.id] || "");
    status.className = "ask-status";
    actions.appendChild(status);
    controls.appendChild(actions);
    return controls;
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
    article.appendChild(renderAskControls(ask));

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
    head.appendChild(textEl("span", notice.time_left));
    if (!notice.seen) {
      var badge = textEl("span", "new");
      badge.className = "badge notice-new";
      head.appendChild(badge);
    }
    article.appendChild(head);
    article.appendChild(textEl("p", notice.text));
    article.appendChild(renderNoticeActions(notice));
    return article;
  }

  function renderNoticeActions(notice) {
    var actions = el("div");
    actions.className = "notice-actions";
    var label = notice.seen ? "Mark unseen" : "Mark seen";
    var action = notice.seen ? "unseen" : "seen";
    var button = textEl("button", label);
    button.type = "button";
    button.className = notice.seen ? "notice-unseen-button" : "notice-seen-button";
    button.disabled = state.noticeBusy[notice.id] === true;
    button.addEventListener("click", function () {
      postNoticeAction(notice.id, action);
    });
    actions.appendChild(button);
    var status = textEl("span", state.noticeStatuses[notice.id] || "");
    status.className = "ask-status";
    actions.appendChild(status);
    return actions;
  }

  function renderSeenAllControls(newCount) {
    var controls = el("div");
    controls.className = "notice-actions";
    var button = textEl("button", "Mark all seen");
    button.type = "button";
    button.disabled = state.noticeBusy.all === true || newCount === 0;
    button.addEventListener("click", postSeenAll);
    controls.appendChild(button);
    var status = textEl("span", state.noticeAllStatus);
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function renderNotices(notices) {
    var section = document.getElementById("notices");
    clear(section);
    var newCount = notices.filter(function (notice) {
      return !notice.seen;
    }).length;
    section.appendChild(textEl("h2", "notices (" + notices.length + ") · " + newCount + " new"));
    section.appendChild(renderSeenAllControls(newCount));
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

  function renderQueueEntryHead(entry) {
    var head = el("div");
    head.className = "queue-entry-head";
    head.appendChild(link(entry.url, entry.ref));
    var lifecycle = textEl("span", entry.lifecycle);
    lifecycle.className = "pill lifecycle-" + entry.lifecycle;
    head.appendChild(lifecycle);
    head.appendChild(renderChecks(entry));
    head.appendChild(textEl("span", entry.party));
    head.appendChild(textEl("span", entry.task || "-"));
    return head;
  }

  function renderQueueEntry(entry) {
    var item = el("li");
    item.className = "queue-entry";
    item.value = entry.position;
    item.appendChild(renderQueueEntryHead(entry));
    item.appendChild(classedText("p", entry.reason, "queue-reason"));
    return item;
  }

  function renderBlockedEntry(entry) {
    var item = el("li");
    item.className = "queue-entry";
    item.appendChild(renderQueueEntryHead(entry));
    item.appendChild(classedText("p", entry.reasons.join("; "), "queue-reason"));
    return item;
  }

  function renderMergeQueue(queue) {
    var article = el("article");
    article.className = "card merge-queue";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("strong", queue.scope));
    head.appendChild(textEl("span", queue.synced_label));
    article.appendChild(head);
    if (queue.queue.length === 0) {
      article.appendChild(textEl("p", "nothing ready to merge"));
    } else {
      var list = el("ol");
      list.className = "queue-list";
      appendAll(list, queue.queue.map(renderQueueEntry));
      article.appendChild(list);
    }
    if (queue.blocked.length > 0) {
      article.appendChild(textEl("h4", "blocked (" + queue.blocked.length + ")"));
      var blockedList = el("ul");
      blockedList.className = "queue-list";
      appendAll(blockedList, queue.blocked.map(renderBlockedEntry));
      article.appendChild(blockedList);
    }
    return article;
  }

  function renderMergeQueues(queues) {
    var section = document.getElementById("merge-queues");
    clear(section);
    section.appendChild(textEl("h2", "merge queue"));
    if (queues.length === 0) {
      section.appendChild(textEl("p", "no open PRs in scope"));
      return;
    }
    appendAll(section, queues.map(renderMergeQueue));
    section.appendChild(classedText("p", "guild never merges: merge in this order by hand", "muted"));
  }

  function prMatchesStateFilter(pr) {
    return state.stateFilter === "all" || pr.lifecycle === state.stateFilter;
  }

  function renderChecks(pr) {
    var checks = el("span");
    if (pr.checks_failing === 0 && pr.checks_passing === 0) {
      var none = textEl("span", "no checks");
      none.className = "checks-none";
      checks.appendChild(none);
      return checks;
    }
    var failing = textEl("span", "✗" + pr.checks_failing);
    failing.className = pr.checks_failing > 0 ? "checks-failing" : "checks-clear";
    var passing = textEl("span", "✓" + pr.checks_passing);
    passing.className = "checks-passing";
    checks.appendChild(failing);
    checks.appendChild(document.createTextNode(" "));
    checks.appendChild(passing);
    return checks;
  }

  function renderPr(pr) {
    var row = el("li");
    row.className = "pr";
    row.appendChild(link(pr.url, pr.repo + "#" + pr.number));
    var lifecycle = textEl("span", pr.lifecycle);
    lifecycle.className = "pill lifecycle-" + pr.lifecycle;
    row.appendChild(lifecycle);
    row.appendChild(renderChecks(pr));
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
    var taskState = textEl("span", task.state);
    taskState.className = "state state-" + task.state;
    head.appendChild(taskState);
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

    var raidsList = renderRaidMembershipList(party.raids);
    if (raidsList) {
      details.appendChild(textEl("h4", "raids"));
      details.appendChild(raidsList);
    }

    return details;
  }

  function renderRaidMembership(raid) {
    var item = el("li");
    item.className = "raid";
    item.appendChild(textEl("span", raid.raid));
    if (raid.lead) {
      var badge = textEl("span", "lead");
      badge.className = "badge";
      item.appendChild(badge);
    }
    return item;
  }

  function renderRaidMembershipList(raids) {
    if (raids.length === 0) {
      return null;
    }
    var list = el("ul");
    list.className = "raid-list";
    appendAll(list, raids.map(renderRaidMembership));
    return list;
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
      raids: data.raids,
      merge_queues: filterMergeQueuesByParty(data.merge_queues, state.partyFilter),
    };
  }

  function filterMergeQueuesByParty(queues, partyName) {
    var matches = function (entry) {
      return entry.party === partyName;
    };
    return queues
      .map(function (queue) {
        return {
          scope: queue.scope,
          synced_at: queue.synced_at,
          synced_label: queue.synced_label,
          queue: queue.queue.filter(matches),
          blocked: queue.blocked.filter(matches),
        };
      })
      .filter(function (queue) {
        return queue.queue.length + queue.blocked.length > 0;
      });
  }

  function refreshRaidFilterOptions(raids) {
    var select = document.getElementById("raid-filter");
    var previous = select.value;
    clear(select);
    select.appendChild(option("all"));
    raids.forEach(function (raid) {
      select.appendChild(option(raid.name));
    });
    var stillPresent = Array.prototype.some.call(select.options, function (option) {
      return option.value === previous;
    });
    select.value = stillPresent ? previous : "all";
    state.raidFilter = select.value;
  }

  function raidMembers(raids, raidName) {
    var match = raids.filter(function (raid) {
      return raid.name === raidName;
    });
    return match.length > 0 ? match[0].members : [];
  }

  function applyRaidFilter(data) {
    if (state.raidFilter === "all") {
      return data;
    }
    var members = raidMembers(data.raids, state.raidFilter);
    var scope = "raid:" + state.raidFilter;
    return {
      generated_at: data.generated_at,
      asks: data.asks.filter(function (ask) {
        return members.indexOf(ask.party) !== -1;
      }),
      notices: data.notices.filter(function (notice) {
        return notice.scope === scope;
      }),
      parties: data.parties.filter(function (party) {
        return members.indexOf(party.name) !== -1;
      }),
      drift: data.drift,
      raids: data.raids,
      merge_queues: data.merge_queues.filter(function (queue) {
        return queue.scope === "raid:" + state.raidFilter;
      }),
    };
  }

  function rememberFocus() {
    var active = document.activeElement;
    state.focusedAskId = null;
    if (active && active.dataset && active.dataset.askId) {
      state.focusedAskId = active.dataset.askId;
      state.focusStart = active.selectionStart;
      state.focusEnd = active.selectionEnd;
    }
  }

  function restoreFocus() {
    if (state.focusedAskId === null) {
      return;
    }
    var areas = document.querySelectorAll("textarea.answer-field");
    Array.prototype.forEach.call(areas, function (area) {
      if (area.dataset.askId === state.focusedAskId && !area.disabled) {
        area.focus();
        area.setSelectionRange(state.focusStart, state.focusEnd);
      }
    });
  }

  function render(data) {
    rememberFocus();
    document.getElementById("generated-at").textContent = "generated at " + data.generated_at;
    refreshPartyFilterOptions(data.parties);
    refreshRaidFilterOptions(data.raids);
    var filtered = applyRaidFilter(applyPartyFilter(data));
    renderAsks(filtered.asks);
    renderNotices(filtered.notices);
    renderMergeQueues(filtered.merge_queues);
    renderDrift(filtered.drift);
    renderParties(filtered.parties);
    restoreFocus();
  }

  function fetchSession() {
    fetch(SESSION_URL)
      .then(function (response) {
        return response.json();
      })
      .then(function (body) {
        sessionToken = body.token;
      })
      .catch(function () {});
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
    document.getElementById("raid-filter").addEventListener("change", function (event) {
      state.raidFilter = event.target.value;
      fetchBoard();
    });
    fetchSession();
    fetchBoard();
    setInterval(fetchBoard, REFRESH_INTERVAL_MS);
  });
})();
