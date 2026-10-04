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

  function deepFreeze(value) {
    Object.keys(value).forEach(function (key) {
      if (typeof value[key] === "object") {
        deepFreeze(value[key]);
      }
    });
    return Object.freeze(value);
  }

  var TOOLTIPS = deepFreeze({
    partyStatus: {
      "waiting-permission": "The leader session is blocked on a Claude Code permission prompt; approve or deny it in that session.",
      "waiting-ask": "The party has an open ask and its leader is not working; answer the ask below.",
      "waiting-input": "The leader session is idle and waiting for you to type something in it.",
      "stopped-with-work": "The leader session stopped but the party still has unfinished work; resume it.",
      working: "The leader session is running.",
      done: "The leader session stopped and the party has no work left.",
      unknown: "The leader session never reported its status, so guild cannot tell what it is doing.",
      "awaiting-leader": "The party has no running leader; start or resume a session to lead it.",
      closed: "The party is closed and its work is over.",
    },
    partyState: {
      active: "The party has a leader session bound to it.",
      "awaiting-leader": "The party lost its leader and waits for a new session to take over.",
      closed: "The party was closed.",
    },
    lifecycle: {
      draft: "The PR is a draft; mark it ready for review when the work is complete.",
      converging: "The PR is a draft that is being polished toward ready for review.",
      ready: "The PR is ready for review and can be merged once its checks pass.",
      merged: "The PR was merged.",
      closed: "The PR was closed without merging.",
    },
    flag: {
      "needs-ask-answer": "The PR is stopped on an open ask; answer it so work can resume.",
      "needs-human-pr-review": "The PR touches something sensitive and needs a human review before merging.",
    },
    checks: {
      failing: "Number of failing CI checks; red when above zero.",
      passing: "Number of passing CI checks.",
      pending: "Number of CI checks still running.",
      none: "No CI checks were reported for this PR.",
    },
    taskState: {
      queued: "The task is waiting to be started.",
      active: "The task is being worked on.",
      blocked: "The task cannot move forward; see the reason shown below it.",
      done: "The task is finished.",
    },
    queueState: {
      ready: "Nothing stands in the way of this PR.",
      waiting: "The PR is waiting on checks that are still running.",
      blocked: "Something must be fixed before this PR can merge.",
    },
    queueAction: {
      merge: "Merge this PR by hand; guild never merges.",
      promote: "Mark this draft ready for review with gh pr ready.",
      review: "A human must review this PR, then merge it by hand.",
      fix: "Fix the listed problems; the party named is the one to do it.",
      wait: "Wait for the listed checks to finish.",
    },
    scope: {
      guild: "Delivered to every party.",
      project: "Delivered to every party of that project.",
      raid: "Delivered to the members of that raid.",
    },
    role: {
      solo: "The party is not in any raid.",
      lead: "The party leads the raid listed (RL = raid lead).",
      member: "The party is a member of the raid listed.",
    },
    blockedWait: {
      permission: "The session is blocked on a Claude Code permission prompt; approve or deny it in that session.",
    },
    drift: {
      "merged PR, task not done": "A PR was merged but its task is not marked done.",
      "tracker and SDD disagree": "The tracker card and the SDD task show different states.",
      "SDD task without card": "An SDD task has no tracker card.",
      "card not under its epic": "A card exists that is not under its epic in the tracker.",
      "PR open, card not started": "A PR is open but its card was never started.",
      "PR closed unmerged": "A PR was closed without merging while its task is still open.",
      "party has no running leader": "A party with open work has no running leader session.",
      "epic done with open work": "The epic is marked done but still has open work.",
      "quest task not in SDD": "A quest task has no matching task in the SDD.",
      "task done, SDD not done": "A task is done in guild but not in the SDD.",
    },
    ui: {
      noticeNew: "You have not marked this notice as seen yet.",
      issued: "When the notice was issued, in local time.",
      timeLeft: "How long until the notice expires.",
      askBlocks: "How many references (tasks, PRs) still wait on this ask; 0 may mean the list is stale.",
      mainRed: "The main branch of this repo is failing; fix it before merging anything else.",
      generation: "How many times the party's leader session was replaced.",
      leader: "The leader session of the party.",
      noLeader: "The party has no leader session right now.",
      claims: "Areas this party has reserved so other parties do not edit them.",
      synced: "How fresh the PR data from GitHub is.",
    },
  });

  function explain(node, group, key) {
    if (Object.prototype.hasOwnProperty.call(TOOLTIPS[group], key)) {
      node.title = TOOLTIPS[group][key];
    }
    return node;
  }

  function explainLabel(node, label) {
    explain(node, "lifecycle", label);
    return explain(node, "flag", label);
  }

  function scopeKind(scope) {
    if (scope === "guild") {
      return "guild";
    }
    if (scope.indexOf("project:") === 0) {
      return "project";
    }
    if (scope.indexOf("raid:") === 0) {
      return "raid";
    }
    return "";
  }

  function actionKind(action) {
    return action.split(":")[0];
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

  var askDetails = { open: {}, cache: {} };

  function detailText(tag, value, tooltip) {
    var node = textEl(tag, value);
    node.title = tooltip;
    return node;
  }

  function detailLink(url, label, tooltip) {
    if (typeof url !== "string" || url.indexOf("https://") !== 0) {
      return detailText("span", label, tooltip);
    }
    var anchor = link(url, label);
    anchor.title = tooltip;
    return anchor;
  }

  function detailLine(parts) {
    var line = el("p");
    line.className = "ask-detail-line";
    appendAll(line, parts);
    return line;
  }

  function renderTaskRef(ref) {
    if (ref.missing) {
      return [detailLine([detailText("strong", "task " + ref.quest + "/" + ref.tid, "Quest task the ask points at"), detailText("span", " (not found)", "The task no longer exists in the local database")])];
    }
    var lines = [
      detailLine([
        detailText("strong", "task " + ref.quest + "/" + ref.tid, "Quest task the ask points at"),
        detailText("span", " " + ref.title + " [" + ref.state + "]", "Task title and current state"),
        detailText("span", ref.epic ? " epic: " + ref.epic : "", "SDD epic the task belongs to"),
      ]),
    ];
    if (ref.spec) {
      lines.push(detailLine([detailText("span", "spec: ", "Path of the epic spec"), detailText("code", ref.spec, "Path of the epic spec")]));
    }
    if (ref.tasks) {
      lines.push(detailLine([detailText("span", "tasks: ", "Path of the epic task list"), detailText("code", ref.tasks, "Path of the epic task list")]));
    }
    return lines;
  }

  function renderCardRef(ref) {
    if (ref.missing) {
      return [detailLine([detailText("strong", "card " + ref.key, "Tracker card the ask points at"), detailText("span", " (not found)", "The card is not known locally")])];
    }
    return [
      detailLine([
        detailText("strong", "card " + ref.key, "Tracker card the ask points at"),
        detailText("span", ref.status ? " " + ref.status : "", "Card status at the last tracker sync"),
        ref.url ? detailLink(ref.url, " open card", "Open the card in the tracker") : detailText("span", "", "No tracker link configured"),
      ]),
    ];
  }

  function renderPrRef(ref) {
    var name = ref.ref.slice("pr:".length);
    if (ref.missing) {
      return [detailLine([detailLink(ref.url, "PR " + name, "Open the pull request on GitHub"), detailText("span", " (not found)", "The PR is not tracked locally")])];
    }
    var checks = ref.checks_passing + " passing, " + ref.checks_failing + " failing, " + ref.checks_pending + " pending";
    var parts = [
      detailLink(ref.url, "PR " + name, "Open the pull request on GitHub"),
      detailText("span", " lifecycle: " + ref.lifecycle, "Guild lifecycle of the PR"),
      detailText("span", " checks: " + checks, "CI checks at the last sync"),
    ];
    if (ref.waits) {
      parts.push(detailText("span", " waits: " + ref.waits, "What the PR waits on"));
    }
    return [detailLine(parts)];
  }

  function renderRefDetail(ref) {
    if (ref.kind === "task") {
      return renderTaskRef(ref);
    }
    if (ref.kind === "card") {
      return renderCardRef(ref);
    }
    return renderPrRef(ref);
  }

  function renderOriginDetail(origin) {
    if (origin === null) {
      return [detailLine([detailText("span", "origin: not recorded", "The ask predates origin snapshots")])];
    }
    var session = origin.session_name ? origin.session_id + " (" + origin.session_name + ")" : origin.session_id;
    var tasks = origin.in_progress.map(function (task) {
      return task.quest + "/" + task.tid + " " + task.title;
    });
    var lines = [
      detailLine([detailText("strong", "origin (at creation)", "State of the asking party when the ask was created")]),
      detailLine([detailText("span", "session: " + session, "Session that created the ask")]),
      detailLine([detailText("span", "in progress: " + (tasks.join(", ") || "none"), "Tasks in progress at creation")]),
      detailLine([detailText("span", "epics: " + (origin.epics.join(", ") || "none") + "  cards: " + (origin.cards.join(", ") || "none"), "Epics and cards linked at creation")]),
    ];
    if (origin.handoff_path) {
      lines.push(detailLine([detailText("span", "handoff: ", "Latest handoff file of the party"), detailText("code", origin.handoff_path, "Latest handoff file of the party")]));
    }
    return lines;
  }

  function renderAskDetail(model) {
    var wrapper = el("div");
    wrapper.className = "ask-detail";
    model.refs.forEach(function (ref) {
      appendAll(wrapper, renderRefDetail(ref));
    });
    appendAll(wrapper, renderOriginDetail(model.origin));
    if (model.resume) {
      wrapper.appendChild(detailLine([detailText("span", "resume: ", "Command that reopens the asking session"), detailText("code", model.resume, "Command that reopens the asking session")]));
    }
    if (model.answer !== null) {
      wrapper.appendChild(detailLine([detailText("span", "answer: " + model.answer, "Answer given to the ask")]));
    }
    wrapper.appendChild(detailLine([detailText("strong", "recent events", "Latest events of the asking party")]));
    model.events.forEach(function (event) {
      wrapper.appendChild(detailLine([detailText("code", event.ts + " " + event.kind + " " + event.summary, "Event timestamp, kind and subject")]));
    });
    return wrapper;
  }

  function showAskDetail(container, askId) {
    clear(container);
    var model = askDetails.cache[askId];
    if (model === undefined) {
      container.appendChild(detailText("p", "loading...", "Detail is being fetched"));
      return;
    }
    container.appendChild(renderAskDetail(model));
  }

  function fetchAskDetail(askId, container) {
    fetch("/api/asks/" + askId)
      .then(function (response) {
        return response.json();
      })
      .then(function (model) {
        if (typeof model.error === "string") {
          clear(container);
          container.appendChild(detailText("p", model.error, "Why the detail could not load"));
          return;
        }
        askDetails.cache[askId] = model;
        showAskDetail(container, askId);
      })
      .catch(function () {
        clear(container);
        container.appendChild(detailText("p", "detail request failed", "Why the detail could not load"));
      });
  }

  function renderAskDetailControl(ask) {
    var details = el("details");
    details.className = "ask-detail-control";
    details.open = askDetails.open[ask.id] === true;
    details.appendChild(detailText("summary", "detail", "Task, card, PR, origin session and recent events behind this ask"));
    var container = el("div");
    details.appendChild(container);
    if (details.open) {
      showAskDetail(container, ask.id);
      fetchAskDetail(ask.id, container);
    }
    details.addEventListener("toggle", function () {
      askDetails.open[ask.id] = details.open;
      if (details.open) {
        showAskDetail(container, ask.id);
        fetchAskDetail(ask.id, container);
      }
    });
    return details;
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
    article.appendChild(explain(textEl("p", blocksText(ask)), "ui", "askBlocks"));

    var details = el("details");
    details.open = contextOpen(ask.id);
    details.appendChild(textEl("summary", "context"));
    details.appendChild(textEl("p", ask.context));
    details.addEventListener("toggle", function () {
      state.openContexts[ask.id] = details.open;
    });
    article.appendChild(details);
    article.appendChild(renderAskDetailControl(ask));
    article.appendChild(renderAskControls(ask));

    return article;
  }

  function renderBlocked(entry) {
    var line = el("p");
    line.className = "blocked-session";
    line.appendChild(textEl("strong", entry.party));
    line.appendChild(explain(textEl("span", entry.label), "blockedWait", entry.wait));
    if (entry.detail) {
      line.appendChild(textEl("code", entry.detail));
    }
    return line;
  }

  function renderAsks(asks, blocked) {
    var section = document.getElementById("asks");
    clear(section);
    section.appendChild(textEl("h2", "asks (" + asks.length + ") · blocked (" + blocked.length + ")"));
    if (asks.length === 0 && blocked.length === 0) {
      section.appendChild(textEl("p", "nothing needs you"));
      return;
    }
    appendAll(section, blocked.map(renderBlocked));
    appendAll(section, asks.map(renderAsk));
  }

  function renderStatusBadge(status) {
    var badge = textEl("span", status.label);
    badge.className = "status-badge status-" + status.name;
    return explain(badge, "partyStatus", status.name);
  }

  function renderNotice(notice) {
    var article = el("article");
    article.className = "card notice";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("span", "#" + notice.id));
    head.appendChild(textEl("span", notice.party || "human"));
    head.appendChild(explain(textEl("span", notice.issued), "ui", "issued"));
    head.appendChild(explain(textEl("span", notice.scope), "scope", scopeKind(notice.scope)));
    head.appendChild(explain(textEl("span", notice.time_left), "ui", "timeLeft"));
    if (!notice.seen) {
      var badge = textEl("span", "new");
      badge.className = "badge notice-new";
      head.appendChild(explain(badge, "ui", "noticeNew"));
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
    article.appendChild(explain(textEl("p", entry.scope), "scope", scopeKind(entry.scope)));
    var ruleNames = Object.keys(entry.findings);
    if (ruleNames.length === 0) {
      article.appendChild(textEl("p", "no drift"));
      return article;
    }
    ruleNames.forEach(function (rule) {
      var findings = entry.findings[rule];
      article.appendChild(explain(textEl("h4", rule + " (" + findings.length + ")"), "drift", rule));
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
    entry.labels.forEach(function (label) {
      var pill = textEl("span", label);
      pill.className = "pill lifecycle-" + label;
      head.appendChild(explainLabel(pill, label));
    });
    head.appendChild(renderChecks(entry));
    head.appendChild(textEl("span", entry.party));
    head.appendChild(textEl("span", entry.task || "-"));
    return head;
  }

  function renderQueueSummary(entry) {
    var summary = el("p");
    summary.className = "queue-reason";
    if (entry.next_action) {
      summary.appendChild(document.createTextNode("\u25b6 next action: "));
    }
    summary.appendChild(explain(textEl("span", entry.state), "queueState", entry.state));
    summary.appendChild(document.createTextNode(" \u00b7 unblocks " + entry.unblocks + " \u2014 "));
    summary.appendChild(explain(textEl("span", entry.action), "queueAction", actionKind(entry.action)));
    return summary;
  }

  function renderQueueEntry(entry) {
    var item = el("li");
    item.className = "queue-entry queue-" + entry.state;
    item.value = entry.position;
    item.appendChild(renderQueueEntryHead(entry));
    item.appendChild(renderQueueSummary(entry));
    if (entry.why) {
      item.appendChild(classedText("p", entry.why, "queue-reason"));
    }
    return item;
  }

  function renderMainRow(row) {
    var text = "MAIN RED " + row.repo + " \u2014 " + row.reason + " (" + row.source + ") \u2192 fix before anything";
    return explain(classedText("p", text, "queue-main-red"), "ui", "mainRed");
  }

  function renderMergeQueue(queue) {
    var article = el("article");
    article.className = "card merge-queue";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(explain(textEl("strong", queue.scope), "scope", scopeKind(queue.scope)));
    head.appendChild(explain(textEl("span", queue.synced_label), "ui", "synced"));
    article.appendChild(head);
    appendAll(article, queue.main.map(renderMainRow));
    var list = el("ol");
    list.className = "queue-list";
    appendAll(list, queue.queue.map(renderQueueEntry));
    article.appendChild(list);
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
    if (state.stateFilter === "all") {
      return true;
    }
    if (state.stateFilter === "needs-ask-answer") {
      return pr.needs_ask_answer;
    }
    if (state.stateFilter === "needs-human-pr-review") {
      return pr.needs_human_pr_review;
    }
    return pr.lifecycle === state.stateFilter;
  }

  function renderChecks(pr) {
    var checks = el("span");
    if (pr.checks_failing === 0 && pr.checks_passing === 0 && pr.checks_pending === 0) {
      var none = textEl("span", "no checks");
      none.className = "checks-none";
      checks.appendChild(explain(none, "checks", "none"));
      return checks;
    }
    var failing = textEl("span", "✗" + pr.checks_failing);
    failing.className = pr.checks_failing > 0 ? "checks-failing" : "checks-clear";
    var passing = textEl("span", "✓" + pr.checks_passing);
    passing.className = "checks-passing";
    checks.appendChild(explain(failing, "checks", "failing"));
    checks.appendChild(document.createTextNode(" "));
    checks.appendChild(explain(passing, "checks", "passing"));
    if (pr.checks_pending > 0) {
      var pending = textEl("span", "⏳" + pr.checks_pending);
      pending.className = "checks-pending";
      checks.appendChild(document.createTextNode(" "));
      checks.appendChild(explain(pending, "checks", "pending"));
    }
    return checks;
  }

  function renderPr(pr) {
    var row = el("li");
    row.className = "pr";
    row.appendChild(link(pr.url, pr.repo + "#" + pr.number));
    var lifecycle = textEl("span", pr.lifecycle);
    lifecycle.className = "pill lifecycle-" + pr.lifecycle;
    row.appendChild(explain(lifecycle, "lifecycle", pr.lifecycle));
    if (pr.needs_ask_answer) {
      var ask = textEl("span", "needs-ask-answer");
      ask.className = "pill lifecycle-needs-ask-answer";
      row.appendChild(explain(ask, "flag", "needs-ask-answer"));
    }
    if (pr.needs_human_pr_review) {
      var review = textEl("span", "needs-human-pr-review");
      review.className = "pill lifecycle-needs-human-pr-review";
      row.appendChild(explain(review, "flag", "needs-human-pr-review"));
    }
    row.appendChild(renderChecks(pr));
    if (pr.card_url) {
      row.appendChild(link(pr.card_url, pr.card));
    } else if (pr.card) {
      row.appendChild(textEl("span", pr.card));
    }
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
    head.appendChild(explain(taskState, "taskState", task.state));
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

  function renderRoleBadge(raids) {
    var badge = el("span");
    var isLead = raids.some(function (raid) {
      return raid.lead;
    });
    var modifier = raids.length === 0 ? "role-solo" : isLead ? "role-lead" : "role-member";
    badge.className = "role-badge " + modifier;
    explain(badge, "role", modifier.slice("role-".length));
    badge.textContent =
      raids.length === 0
        ? "solo"
        : raids
            .slice()
            .sort(function (a, b) {
              return a.raid < b.raid ? -1 : a.raid > b.raid ? 1 : 0;
            })
            .map(function (raid) {
              return raid.lead ? "RL " + raid.raid : raid.raid;
            })
            .join(", ");
    return badge;
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
    summary.appendChild(renderRoleBadge(party.raids));
    summary.appendChild(renderStatusBadge(party.status));
    summary.appendChild(explain(textEl("span", party.state), "partyState", party.state));
    summary.appendChild(explain(textEl("span", "gen " + party.generation), "ui", "generation"));
    var leaderKey = party.leader_session_name ? "leader" : "noLeader";
    summary.appendChild(explain(textEl("span", party.leader_session_name || "no leader"), "ui", leaderKey));
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
      details.appendChild(explain(textEl("p", "claims: " + claimsText), "ui", "claims"));
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
      item.appendChild(explain(badge, "role", "lead"));
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
      blocked: data.blocked.filter(function (entry) {
        return entry.party === state.partyFilter;
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
          main: queue.main,
          queue: queue.queue.filter(matches),
        };
      })
      .filter(function (queue) {
        return queue.queue.length > 0;
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
      blocked: data.blocked.filter(function (entry) {
        return members.indexOf(entry.party) !== -1;
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
    renderAsks(filtered.asks, filtered.blocked);
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
