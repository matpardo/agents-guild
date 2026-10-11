(function () {
  "use strict";

  var REFRESH_INTERVAL_MS = 15000;
  var BOARD_URL = "/api/board";
  var SESSION_URL = "/api/session";
  var RESOURCES_URL = "/api/resources";
  var ANSWERED_ASKS_URL = "/api/asks/answered";
  var RESOURCE_ITEMS_PER_CATEGORY = 10;
  var NO_RESOURCES_MESSAGE = "no samples yet; run guild resources collect";
  var EMPTY_REASON_MESSAGE = "write a reason first";
  var EMPTY_ANSWER_MESSAGE = "write an answer first";
  var DEFAULT_BRANCHES = ["main", "master"];
  var BLOCKED_EXTERNAL_TEXT = "blocked: external";
var NO_SESSION_MESSAGE = "session token not loaded, reload the page";
  var sessionToken = null;

  var answered = {
    open: false,
    page: 1,
    model: null,
    error: null,
  };

  var state = {
    partyFilter: "all",
    stateFilter: "all",
    raidFilter: "all",
    openParties: {},
    resourcesOpen: false,
    noticesOpen: true,
    queueDetailOpen: {},
    openResourceProjects: {},
    openContexts: {},
    drafts: {},
    statuses: {},
    busy: {},
    prBlockOpen: {},
    prDrafts: {},
    prStatuses: {},
    prBusy: {},
    focusedPrRef: null,
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
      unknown: "A running leader session never reported its status.",
      idle: "The party has no live session and nothing to do.",
      queued: "The party has no live session but has work waiting; start a fresh session from its brief.",
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
      "fixes-main": "The PR repairs a broken main branch; it goes first so everyone is unblocked.",
      "fixes-flaky": "The PR fixes flaky tests; it goes first so the suite stops lying to everyone.",
      "needs-ask-answer": "The PR is stopped on an open ask; answer it so work can resume.",
      "needs-human-pr-review": "The PR touches something sensitive and needs a human review before merging.",
      "blocked-external": "The PR waits on something outside development; do not try to fix it.",
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
    reason: {
      threads: "Review threads on this PR are still unresolved.",
      "changes requested": "A reviewer asked for changes on this PR.",
      "behind base": "The PR branch is behind its base branch and needs an update.",
      "merge conflict": "The PR conflicts with its base branch and cannot merge until resolved.",
      "checks failing": "Some checks of this PR are failing.",
      "checks pending": "Some checks of this PR are still running.",
      "needs ask answer": "The party is stopped on an ask; answer it first.",
      external: "The PR is blocked by something outside guild.",
      "waits on task": "The PR waits on a task that is not done yet.",
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
      "PR merged, card not done": "A PR was merged but its card is not done in the tracker.",
      "task started, card not started": "A task is in progress but its card was never started.",
      "PR closed unmerged": "A PR was closed without merging while its task is still open.",
      "party has no running leader": "A party with open work has no running leader session.",
      "epic done with open work": "The epic is marked done but still has open work.",
      "quest task not in SDD": "A quest task has no matching task in the SDD.",
      "task done, SDD not done": "A task is done in guild but not in the SDD.",
    },
    resourceCategory: {
      worktree: "Disk used by a git checkout of the project; worktrees nested inside it are counted on their own.",
      docker_container: "Writable layer of a Docker container tied to the project through its compose label.",
      docker_image: "Unique size of a Docker image; layers shared with other images are not included, so the sum is approximate.",
      docker_volume: "Docker volume tied to the project through its compose label.",
      claude_scratch: "Claude Code scratchpad files created while working in the checkout.",
      claude_transcripts: "Claude Code session transcripts stored for the checkout.",
      docker: "Docker could not be read; the detail says why.",
    },
    resourceFlag: {
      merged: "The PR of this branch was merged but the worktree is still on disk.",
      closed: "The PR of this branch was closed but the worktree is still on disk.",
      orphaned: "The compose project of this object no longer has a working directory or a checkout.",
      dangling: "A Docker image with no name and no tag.",
      unused: "A Docker image that no container uses.",
    },
    ui: {
      openPrs: "Open PRs of this party against its cap (max_open_prs_per_party); PRs blocked externally are not counted.",
      projectOpenPrs: "Open PRs of the whole project against its cap (max_open_prs); PRs blocked externally are not counted.",
      capWait: "The cap is reached: merge the PR named before opening another.",
      hotFiles: "Files touched by as many open PRs as max_open_prs_per_file allows; expect merge conflicts.",
      findingClasses: "Review finding classes with the number of distinct PRs; at the threshold the class should become an architecture guard.",
      syncFreshness: "How long ago the SDD and the tracker were last synced successfully.",
      noticeNew: "You have not marked this notice as seen yet.",
      issued: "When the notice was issued, in local time.",
      timeLeft: "How long until the notice expires.",
      askBlocks: "How many references (tasks, PRs) still wait on this ask; 0 may mean the list is stale.",
      mainRed: "The main branch of this repo is failing; fix it before merging anything else.",
      generation: "How many times the party's leader session was replaced.",
      ctxHigh: "The leader session is near its context limit and should run guild handoff soon.",
      remaining: "Tasks not done in the party's active quests plus open PRs outside them; the tooltip lists done/total per quest.",
      allDone: "Every task of the party's active quests is done and no open PR is left outside them.",
      resumeCommand: "Run this to start the next generation of this party; it waits for a new leader.",
      dispatcherRules: "Dispatcher rules this project enabled with their mode, and launches in the last hour against the hourly cap.",
      dispatcherDeferred: "A dispatch waiting on a live session, an open window or a paused raid; retried until it expires after 24 hours.",
      dispatcherPlanned: "The rule is in dry-run: it recorded what it would do and did nothing.",
      leader: "The leader session of the party.",
      noLeader: "The party has no leader session right now.",
      claims: "Areas this party has reserved so other parties do not edit them.",
      synced: "How fresh the PR data from GitHub is.",
      baseBranch: "The PR targets this branch instead of the default one, so it is stacked on another change.",
      nextToMerge: "The first PR in this queue that is ready to merge by hand.",
      noMergeReady: "No PR in this queue is ready to merge right now.",
      queueDetail: "What stands between this PR and a merge: blockers, waits and gates.",
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

  function prUrl(ref, action) {
    var parts = ref.split("#");
    return "/api/prs/" + parts[0] + "/" + parts[1] + "/" + action;
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

  function postPrAction(ref, action, payload) {
    if (sessionToken === null) {
      state.prStatuses[ref] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.prBusy[ref] = true;
    state.prStatuses[ref] = "sending...";
    fetchBoard();
    sendPost(prUrl(ref, action), payload).then(function (result) {
      delete state.prBusy[ref];
      if (result.ok) {
        delete state.prBlockOpen[ref];
        delete state.prDrafts[ref];
        delete state.prStatuses[ref];
      } else {
        state.prStatuses[ref] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function submitBlock(ref) {
    var text = state.prDrafts[ref] || "";
    if (text.trim() === "") {
      state.prStatuses[ref] = EMPTY_REASON_MESSAGE;
      fetchBoard();
      return;
    }
    postPrAction(ref, "block", { reason: text });
  }

  function prButton(ref, label, handler) {
    var button = textEl("button", label);
    button.type = "button";
    button.disabled = state.prBusy[ref] === true;
    button.addEventListener("click", handler);
    return button;
  }

  function renderBlockInput(ref, location) {
    var input = el("input");
    input.type = "text";
    input.className = "block-reason";
    input.placeholder = "reason";
    input.value = state.prDrafts[ref] || "";
    input.disabled = state.prBusy[ref] === true;
    input.dataset.focusKey = location + "|" + ref;
    input.addEventListener("input", function () {
      state.prDrafts[ref] = input.value;
    });
    return input;
  }

  function renderPrBlockControls(ref, blockedExternal, location) {
    var controls = el("span");
    controls.className = "pr-block-controls";
    if (blockedExternal !== null) {
      controls.appendChild(
        prButton(ref, "Unblock", function () {
          postPrAction(ref, "unblock", {});
        })
      );
    } else if (state.prBlockOpen[ref]) {
      controls.appendChild(renderBlockInput(ref, location));
      controls.appendChild(
        prButton(ref, "Confirm block", function () {
          submitBlock(ref);
        })
      );
    } else {
      controls.appendChild(
        prButton(ref, "Block", function () {
          state.prBlockOpen[ref] = true;
          fetchBoard();
        })
      );
    }
    var status = textEl("span", state.prStatuses[ref] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function renderBlockedExternalPill(reason) {
    var pill = textEl("span", BLOCKED_EXTERNAL_TEXT);
    pill.className = "pill lifecycle-blocked-external";
    explain(pill, "flag", "blocked-external");
    if (reason !== null) {
      pill.title = pill.title + " Reason: " + reason;
    }
    return pill;
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
      wrapper.appendChild(detailLine([detailText("code", event.time + " " + event.kind + " " + event.summary, "Event timestamp, kind and subject")]));
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

  function ctxHighCount(parties) {
    return parties.filter(function (party) {
      return party.ctx !== null;
    }).length;
  }

  function renderAsks(asks, blocked, parties) {
    var section = document.getElementById("asks");
    var ctxHigh = ctxHighCount(parties);
    clear(section);
    section.appendChild(
      textEl(
        "h2",
        "asks (" + asks.length + ") · blocked (" + blocked.length + ") · context high (" + ctxHigh + ")"
      )
    );
    if (asks.length === 0 && blocked.length === 0 && ctxHigh === 0) {
      section.appendChild(textEl("p", "nothing needs you"));
      return;
    }
    appendAll(section, blocked.map(renderBlocked));
    appendAll(section, asks.map(renderAsk));
  }

  function renderAnsweredAsk(ask) {
    var article = el("article");
    article.className = "card answered-ask";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("span", "#" + ask.id));
    head.appendChild(textEl("span", ask.party));
    head.appendChild(textEl("strong", ask.question));
    article.appendChild(head);
    article.appendChild(textEl("p", "answer: " + ask.answer));
    if (ask.answered !== null) {
      article.appendChild(textEl("p", "answered: " + ask.answered));
    }
    return article;
  }

  function renderAnsweredPager(model) {
    var pager = el("p");
    pager.className = "answered-pager";
    var previous = textEl("button", "newer");
    previous.type = "button";
    previous.disabled = model.page <= 1;
    previous.addEventListener("click", function () {
      answered.page = model.page - 1;
      fetchAnsweredAsks();
    });
    var next = textEl("button", "older");
    next.type = "button";
    next.disabled = model.page >= model.page_count;
    next.addEventListener("click", function () {
      answered.page = model.page + 1;
      fetchAnsweredAsks();
    });
    pager.appendChild(previous);
    pager.appendChild(textEl("span", "page " + model.page + "/" + model.page_count));
    pager.appendChild(next);
    return pager;
  }

  function renderAnsweredBody(container) {
    clear(container);
    if (answered.error !== null) {
      container.appendChild(textEl("p", answered.error));
      return;
    }
    if (answered.model === null) {
      container.appendChild(textEl("p", "loading"));
      return;
    }
    if (answered.model.total === 0) {
      container.appendChild(textEl("p", "no answered asks"));
      return;
    }
    appendAll(container, answered.model.asks.map(renderAnsweredAsk));
    container.appendChild(renderAnsweredPager(answered.model));
  }

  function fetchAnsweredAsks() {
    var container = document.getElementById("answered-asks-body");
    fetch(ANSWERED_ASKS_URL + "?page=" + answered.page)
      .then(function (response) {
        return response.json();
      })
      .then(function (model) {
        answered.error = typeof model.error === "string" ? model.error : null;
        answered.model = answered.error === null ? model : null;
        renderAnsweredBody(container);
      })
      .catch(function () {
        answered.error = "answered asks request failed";
        renderAnsweredBody(container);
      });
  }

  function renderAnsweredAsks() {
    var section = document.getElementById("answered-asks");
    var details = el("details");
    details.open = answered.open;
    details.appendChild(textEl("summary", "answered asks"));
    var container = el("div");
    container.id = "answered-asks-body";
    details.appendChild(container);
    details.addEventListener("toggle", function () {
      answered.open = details.open;
      if (details.open) {
        renderAnsweredBody(container);
        fetchAnsweredAsks();
      }
    });
    section.appendChild(details);
    if (details.open) {
      renderAnsweredBody(container);
    }
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
    var details = el("details");
    details.className = "notices-section";
    details.open = state.noticesOpen;
    details.addEventListener("toggle", function () {
      state.noticesOpen = details.open;
    });
    var summary = el("summary");
    summary.appendChild(textEl("h2", "notices (" + notices.length + ") · " + newCount + " new"));
    details.appendChild(summary);
    details.appendChild(renderSeenAllControls(newCount));
    appendAll(details, notices.map(renderNotice));
    section.appendChild(details);
  }

  function renderLaunch(launch, label) {
    var text = label + " " + launch.party + " g" + launch.generation + " " + launch.age + " ago (" + launch.rule + ", " + launch.subject + ")";
    if (launch.reason) {
      text += ": " + launch.reason;
    }
    return classedText("p", text, label === "failed" ? "queue-main-red" : "muted");
  }

  function renderDispatchProject(project) {
    var rules = Object.keys(project.rules).map(function (rule) {
      return rule + " " + project.rules[rule];
    }).join(", ");
    return explain(
      classedText("p", project.name + ": " + rules + " | launches last hour " + project.launches_last_hour + "/" + project.max_launches_per_hour, "muted"),
      "ui",
      "dispatcherRules"
    );
  }

  function renderDeferred(launch) {
    var text = "deferred " + launch.party + " " + launch.rule + " " + launch.subject + " " + launch.age + " ago: " + launch.reason;
    return explain(classedText("p", text, "muted"), "ui", "dispatcherDeferred");
  }

  function renderRecent(decision) {
    var text = "recent " + decision.outcome + " " + decision.rule + " " + decision.subject + " " + decision.party + " " + decision.age + " ago";
    var node = classedText("p", text, "muted");
    return decision.outcome === "planned" ? explain(node, "ui", "dispatcherPlanned") : node;
  }

  function renderDispatcher(dispatcher) {
    var section = document.getElementById("dispatcher");
    clear(section);
    var count = dispatcher.projects.length + dispatcher.in_flight.length + dispatcher.failed.length
      + dispatcher.deferred.length + dispatcher.recent.length;
    if (count === 0) {
      return;
    }
    section.appendChild(textEl("h2", "dispatcher"));
    appendAll(section, dispatcher.projects.map(renderDispatchProject));
    appendAll(section, dispatcher.in_flight.map(function (launch) {
      return renderLaunch(launch, "in flight");
    }));
    appendAll(section, dispatcher.failed.map(function (launch) {
      return renderLaunch(launch, "failed");
    }));
    appendAll(section, dispatcher.deferred.map(renderDeferred));
    appendAll(section, dispatcher.recent.map(renderRecent));
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
        list.appendChild(textEl("li", finding.text));
      });
      article.appendChild(list);
    });
    return article;
  }

  function renderPartyDrift(partyDrift) {
    if (partyDrift.findings.length === 0) {
      return null;
    }
    var block = el("div");
    block.className = "party-drift";
    block.appendChild(textEl("h4", "drift"));
    var list = el("ul");
    partyDrift.findings.forEach(function (finding) {
      list.appendChild(textEl("li", finding));
    });
    block.appendChild(list);
    if (partyDrift.more > 0) {
      block.appendChild(textEl("p", partyDrift.more + " more"));
    }
    return block;
  }

  function filterDriftByParties(drift, parties) {
    return drift.map(function (entry) {
      var findings = {};
      Object.keys(entry.findings).forEach(function (rule) {
        var kept = entry.findings[rule].filter(function (finding) {
          return finding.party !== null && parties.indexOf(finding.party) !== -1;
        });
        if (kept.length > 0) {
          findings[rule] = kept;
        }
      });
      return { project: entry.project, scope: entry.scope, findings: findings };
    });
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

  function renderProject(project) {
    var article = el("article");
    article.className = "card project";
    article.appendChild(textEl("h3", project.name));
    if (project.max_open_prs !== null) {
      article.appendChild(explain(
        textEl("p", "open PRs " + project.open_prs + "/" + project.max_open_prs),
        "ui",
        "projectOpenPrs"
      ));
    }
    if (project.wait !== null) {
      article.appendChild(explain(classedText("p", project.wait, "queue-reason"), "ui", "capWait"));
    }
    if (project.hot_files.length > 0) {
      article.appendChild(explain(textEl("h4", "hot files (" + project.hot_files.length + ")"), "ui", "hotFiles"));
      var hot = el("ul");
      appendAll(hot, project.hot_files.map(function (file) {
        return textEl("li", file.repo + " " + file.path + ": " + file.prs.join(", "));
      }));
      article.appendChild(hot);
    }
    if (project.finding_classes.length > 0) {
      article.appendChild(explain(textEl("h4", "finding classes"), "ui", "findingClasses"));
      var classes = el("ul");
      appendAll(classes, project.finding_classes.map(function (entry) {
        var threshold = entry.threshold === null ? "" : "/" + entry.threshold;
        var item = textEl("li", entry.class + ": " + entry.count + threshold + " PR(s)" + (entry.at_threshold ? " \u2014 guard" : ""));
        if (entry.at_threshold) {
          item.className = "finding-guard";
        }
        return item;
      }));
      article.appendChild(classes);
    }
    var fresh = Object.keys(project.freshness).map(function (name) {
      var age = project.freshness[name];
      return name + " synced " + (age === null ? "never" : age + " ago");
    });
    article.appendChild(explain(classedText("p", fresh.join(", "), "muted"), "ui", "syncFreshness"));
    return article;
  }

  function renderProjects(projects) {
    var section = document.getElementById("projects");
    clear(section);
    if (projects.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "projects"));
    appendAll(section, projects.map(renderProject));
  }

  function branchEl(name) {
    var branch = textEl("span", name);
    branch.className = "branch";
    branch.title = name;
    return branch;
  }

  function renderQueueEntryHead(entry) {
    var head = el("div");
    head.className = "queue-entry-head";
    head.appendChild(link(entry.url, entry.ref));
    if (entry.branch) {
      head.appendChild(branchEl(entry.branch));
    }
    entry.labels.forEach(function (label) {
      if (label === "blocked-external") {
        head.appendChild(renderBlockedExternalPill(entry.blocked_external));
        if (entry.blocked_external !== null) {
          head.appendChild(textEl("span", entry.blocked_external));
        }
        return;
      }
      var pill = textEl("span", label);
      pill.className = "pill lifecycle-" + label;
      head.appendChild(explainLabel(pill, label));
    });
    head.appendChild(renderChecks(entry));
    head.appendChild(textEl("span", entry.party));
    head.appendChild(textEl("span", entry.task || "-"));
    return head;
  }

  function reasonKind(reason) {
    if (reason.indexOf("unresolved thread") !== -1) {
      return "threads";
    }
    var base = reason.split(/ \(|: /)[0];
    if (base.indexOf("waits on task") === 0) {
      return "waits on task";
    }
    return base;
  }

  function renderReasonPills(reasons) {
    return reasons.map(function (reason) {
      var pill = textEl("span", reason);
      pill.className = "pill reason-pill";
      return explain(pill, "reason", reasonKind(reason));
    });
  }

  function renderQueueDetail(entry) {
    var lines = entry.blockers.concat(entry.waits.map(function (wait) {
      return "wait: " + wait;
    }), entry.gates.map(function (gate) {
      return "gate: " + gate;
    }));
    if (lines.length === 0) {
      return null;
    }
    var details = el("details");
    details.className = "queue-detail";
    details.open = state.queueDetailOpen[entry.ref] === true;
    details.addEventListener("toggle", function () {
      state.queueDetailOpen[entry.ref] = details.open;
    });
    details.appendChild(explain(textEl("summary", "ready-check (" + lines.length + ")"), "ui", "queueDetail"));
    var list = el("ul");
    appendAll(list, lines.map(function (line) {
      return textEl("li", line);
    }));
    details.appendChild(list);
    return details;
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
    item.appendChild(renderPrBlockControls(entry.ref, entry.blocked_external, "queue"));
    if (entry.why) {
      item.appendChild(classedText("p", entry.why, "queue-reason"));
    }
    appendAll(item, renderReasonPills(entry.reasons));
    var detail = renderQueueDetail(entry);
    if (detail) {
      item.appendChild(detail);
    }
    return item;
  }

  function renderMainRow(row) {
    var text = "MAIN RED " + row.repo + " \u2014 " + row.reason + " (" + row.source + ") \u2192 fix before anything";
    return explain(classedText("p", text, "queue-main-red"), "ui", "mainRed");
  }

  function renderNextToMerge(head) {
    if (head === null) {
      return explain(classedText("p", "no PR ready to merge", "muted"), "ui", "noMergeReady");
    }
    var line = el("p");
    line.className = "queue-next-to-merge";
    line.appendChild(document.createTextNode("next to merge: "));
    line.appendChild(link(head.url, head.ref));
    line.appendChild(document.createTextNode(" (" + head.party + ")"));
    return explain(line, "ui", "nextToMerge");
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
    article.appendChild(renderNextToMerge(queue.head));
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
    if (state.stateFilter === "fixes-main") {
      return pr.fixes_main;
    }
    if (state.stateFilter === "fixes-flaky") {
      return pr.fixes_flaky;
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
    if (pr.branch) {
      row.appendChild(branchEl(pr.branch));
    }
    if (pr.fixes_main) {
      var fixesMain = textEl("span", "fixes-main");
      fixesMain.className = "pill lifecycle-fixes-main";
      row.appendChild(explain(fixesMain, "flag", "fixes-main"));
    }
    if (pr.fixes_flaky) {
      var fixesFlaky = textEl("span", "fixes-flaky");
      fixesFlaky.className = "pill lifecycle-fixes-flaky";
      row.appendChild(explain(fixesFlaky, "flag", "fixes-flaky"));
    }
    if (pr.needs_ask_answer) {
      var ask = textEl("span", "needs-ask-answer");
      ask.className = "pill lifecycle-needs-ask-answer";
      row.appendChild(explain(ask, "flag", "needs-ask-answer"));
      if (pr.ask_id !== null) {
        ask.textContent = "needs-ask-answer (ask #" + pr.ask_id + ")";
        ask.title = "An open ask refs this PR; answering ask #" + pr.ask_id + " unblocks it.";
      }
    }
    if (pr.needs_human_pr_review) {
      var review = textEl("span", "needs-human-pr-review");
      review.className = "pill lifecycle-needs-human-pr-review";
      row.appendChild(explain(review, "flag", "needs-human-pr-review"));
    }
    if (pr.blocked_external !== null) {
      row.appendChild(renderBlockedExternalPill(pr.blocked_external));
      row.appendChild(textEl("span", pr.blocked_external));
    }
    if (pr.base_branch && DEFAULT_BRANCHES.indexOf(pr.base_branch) === -1) {
      var base = textEl("span", "on " + pr.base_branch);
      base.className = "branch";
      row.appendChild(explain(base, "ui", "baseBranch"));
    }
    appendAll(row, renderReasonPills(pr.review_reasons));
    row.appendChild(renderChecks(pr));
    row.appendChild(renderPrBlockControls(pr.repo + "#" + pr.number, pr.blocked_external, "card"));
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

  function renderRemainingBadge(remaining) {
    if (remaining.all_done) {
      return explain(textEl("span", "all done"), "ui", "allDone");
    }
    var left = remaining.pending + remaining.extra_prs;
    var badge = textEl("span", left + " left");
    badge.className = "status-badge badge-warn";
    explain(badge, "ui", "remaining");
    var perQuest = remaining.quests
      .map(function (quest) {
        return quest.slug + " " + quest.done + "/" + quest.total;
      })
      .join(", ");
    badge.title = badge.title + (perQuest === "" ? "" : " " + perQuest);
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
    summary.appendChild(renderRemainingBadge(party.remaining));
    if (party.ctx !== null) {
      var ctxBadge = textEl("span", "context " + party.ctx.pct + "% / " + party.ctx.threshold + "%");
      ctxBadge.className = "status-badge badge-warn";
      summary.appendChild(explain(ctxBadge, "ui", "ctxHigh"));
    }
    summary.appendChild(explain(textEl("span", party.state), "partyState", party.state));
    summary.appendChild(explain(textEl("span", "gen " + party.generation), "ui", "generation"));
    var leaderKey = party.leader_session_name ? "leader" : "noLeader";
    summary.appendChild(explain(textEl("span", party.leader_session_name || "no leader"), "ui", leaderKey));
    details.appendChild(summary);

    if (party.resume_command !== null) {
      var resumeLine = el("p");
      resumeLine.className = "resume-command";
      resumeLine.appendChild(textEl("span", "resume: "));
      resumeLine.appendChild(textEl("code", party.resume_command));
      details.appendChild(explain(resumeLine, "ui", "resumeCommand"));
    }

    if (party.caps !== null && party.caps.cap !== null) {
      details.appendChild(explain(textEl("p", "open PRs " + party.caps.open + "/" + party.caps.cap), "ui", "openPrs"));
    }
    if (party.caps !== null && party.caps.wait !== null) {
      details.appendChild(explain(classedText("p", party.caps.wait, "queue-reason"), "ui", "capWait"));
    }
    var partyDrift = renderPartyDrift(party.drift);
    if (partyDrift) {
      details.appendChild(partyDrift);
    }

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
      drift: filterDriftByParties(data.drift, [state.partyFilter]),
      projects: data.projects,
      raids: data.raids,
      merge_queues: filterMergeQueuesByParty(data.merge_queues, state.partyFilter),
      dispatcher: filterDispatcher(data.dispatcher, function (launch) {
        return launch.party === state.partyFilter;
      }),
    };
  }

  function filterDispatcher(dispatcher, keep) {
    return Object.assign({}, dispatcher, {
      in_flight: dispatcher.in_flight.filter(keep),
      failed: dispatcher.failed.filter(keep),
      deferred: dispatcher.deferred.filter(keep),
      recent: dispatcher.recent.filter(keep),
    });
  }

  function filterMergeQueuesByParty(queues, partyName) {
    var matches = function (entry) {
      return entry.party === partyName;
    };
    return queues
      .map(function (queue) {
        return Object.assign({}, queue, { queue: queue.queue.filter(matches) });
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
      drift: filterDriftByParties(data.drift, members),
      projects: data.projects,
      raids: data.raids,
      merge_queues: data.merge_queues.filter(function (queue) {
        return queue.scope === "raid:" + state.raidFilter;
      }),
      dispatcher: filterDispatcher(data.dispatcher, function (launch) {
        return members.indexOf(launch.party) !== -1;
      }),
    };
  }

  function rememberFocus() {
    var active = document.activeElement;
    state.focusedAskId = null;
    state.focusedPrRef = null;
    if (active && active.dataset && active.dataset.focusKey) {
      state.focusedPrRef = active.dataset.focusKey;
      state.focusStart = active.selectionStart;
      state.focusEnd = active.selectionEnd;
    }
    if (active && active.dataset && active.dataset.askId) {
      state.focusedAskId = active.dataset.askId;
      state.focusStart = active.selectionStart;
      state.focusEnd = active.selectionEnd;
    }
  }

  function restorePrFocus() {
    var inputs = document.querySelectorAll("input.block-reason");
    Array.prototype.forEach.call(inputs, function (input) {
      if (input.dataset.focusKey === state.focusedPrRef && !input.disabled) {
        input.focus();
        input.setSelectionRange(state.focusStart, state.focusEnd);
      }
    });
  }

  function restoreFocus() {
    if (state.focusedPrRef !== null) {
      restorePrFocus();
    }
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

  var RESOURCE_FLAG_LABELS = {
    merged: "merged, still on disk",
    closed: "closed, still on disk",
    orphaned: "orphaned",
    dangling: "dangling",
    unused: "unused",
  };
  var BYTE_UNITS = [[1e12, "TB", 1], [1e9, "GB", 1], [1e6, "MB", 0], [1e3, "kB", 0]];

  function formatBytes(value) {
    if (value === null) {
      return "?";
    }
    for (var index = 0; index < BYTE_UNITS.length; index += 1) {
      var unit = BYTE_UNITS[index];
      if (value >= unit[0]) {
        return (value / unit[0]).toFixed(unit[2]) + " " + unit[1];
      }
    }
    return value + " B";
  }

  function signedBytes(value) {
    if (value === null) {
      return "?";
    }
    return (value < 0 ? "-" : "+") + formatBytes(Math.abs(value));
  }

  function resourceDelta(entry, hasBaseline) {
    if (!hasBaseline) {
      return "";
    }
    if (entry.new) {
      return "new";
    }
    return signedBytes(entry.delta_bytes);
  }

  function renderResourceItem(entry, hasBaseline) {
    var row = el("li");
    row.appendChild(textEl("code", entry.item));
    row.appendChild(textEl("span", " " + formatBytes(entry.bytes)));
    var delta = resourceDelta(entry, hasBaseline);
    if (delta) {
      row.appendChild(textEl("span", " " + delta));
    }
    if (entry.flag) {
      row.appendChild(explain(textEl("span", " " + (RESOURCE_FLAG_LABELS[entry.flag] || entry.flag)), "resourceFlag", entry.flag));
    }
    return row;
  }

  function resourceCategoryText(category, hasBaseline) {
    if (category.category === "docker") {
      return category.category + " " + category.state + " (" + category.detail + ")";
    }
    var text = category.category + " " + formatBytes(category.bytes);
    if (hasBaseline && category.delta_bytes !== null) {
      text += " (" + signedBytes(category.delta_bytes) + ")";
    }
    return text;
  }

  function renderResourceCategory(project, category, hasBaseline) {
    var wrapper = el("div");
    wrapper.appendChild(explain(textEl("h4", resourceCategoryText(category, hasBaseline)), "resourceCategory", category.category));
    var items = project.items.filter(function (entry) {
      return entry.category === category.category;
    });
    items.sort(function (left, right) {
      return (right.bytes === null ? -1 : right.bytes) - (left.bytes === null ? -1 : left.bytes);
    });
    var list = el("ul");
    items.slice(0, RESOURCE_ITEMS_PER_CATEGORY).forEach(function (entry) {
      list.appendChild(renderResourceItem(entry, hasBaseline));
    });
    if (items.length > RESOURCE_ITEMS_PER_CATEGORY) {
      list.appendChild(textEl("li", "(+" + (items.length - RESOURCE_ITEMS_PER_CATEGORY) + " more)"));
    }
    wrapper.appendChild(list);
    return wrapper;
  }

  function resourceHeadline(label, project) {
    var hasBaseline = project.baseline_at !== null;
    var text = label + " total " + formatBytes(project.total_bytes);
    if (hasBaseline && project.delta_bytes !== null) {
      text += " (" + signedBytes(project.delta_bytes) + ")";
    }
    if (!hasBaseline) {
      text += " no earlier sample";
    }
    return text;
  }

  function renderResourceProject(label, project) {
    var details = el("details");
    details.className = "party";
    details.open = state.openResourceProjects[label] === true;
    details.addEventListener("toggle", function () {
      state.openResourceProjects[label] = details.open;
    });
    details.appendChild(textEl("summary", resourceHeadline(label, project)));
    var hasBaseline = project.baseline_at !== null;
    project.categories.forEach(function (category) {
      details.appendChild(renderResourceCategory(project, category, hasBaseline));
    });
    if (project.growers.length > 0) {
      var growers = project.growers.map(function (grower) {
        return grower.item + " " + signedBytes(grower.delta_bytes);
      });
      details.appendChild(textEl("p", "top growers: " + growers.join(", ")));
    }
    return details;
  }

  function resourceMachineLines(machine, since) {
    var lines = [];
    var disk = "disk n/a";
    if (machine.disk_percent !== null) {
      disk = "disk " + machine.disk_percent + "% used (" + formatBytes(machine.disk_used) + " of " + formatBytes(machine.disk_total);
      if (machine.disk_delta !== null) {
        disk += ", " + signedBytes(machine.disk_delta) + " in " + since;
      }
      disk += ")";
    }
    var ram = "ram n/a";
    if (machine.mem_available !== null) {
      ram = "ram " + formatBytes(machine.mem_available) + " available of " + formatBytes(machine.mem_total);
    }
    var docker = "docker n/a";
    if (machine.docker !== null) {
      docker = "docker " + formatBytes(machine.docker.total) + " (reclaimable " + formatBytes(machine.docker.images_reclaimable) + ")";
    }
    lines.push(disk + " \u00b7 " + ram);
    lines.push(docker + " \u00b7 guild.db " + formatBytes(machine.guild_db_bytes));
    if (machine.untracked_growth !== null) {
      lines.push("untracked growth: " + signedBytes(machine.untracked_growth));
    }
    return lines;
  }

  function renderResourceProjects(model) {
    var details = el("details");
    details.open = state.resourcesOpen;
    details.addEventListener("toggle", function () {
      state.resourcesOpen = details.open;
    });
    details.appendChild(textEl("summary", "projects"));
    model.projects.forEach(function (project) {
      details.appendChild(renderResourceProject(project.name, project));
    });
    if (model.unattributed !== null) {
      details.appendChild(renderResourceProject("unattributed", model.unattributed));
    }
    return details;
  }

  function renderResources(model) {
    var section = document.getElementById("resources");
    clear(section);
    section.appendChild(textEl("h2", "resources"));
    if (model.machine === null) {
      section.appendChild(textEl("p", NO_RESOURCES_MESSAGE));
      return;
    }
    resourceMachineLines(model.machine, model.since).forEach(function (line) {
      section.appendChild(textEl("p", line));
    });
    section.appendChild(classedText("p", "sampled at " + model.machine.sampled_at, "muted"));
    section.appendChild(renderResourceProjects(model));
  }

  function fetchResources() {
    fetch(RESOURCES_URL)
      .then(function (response) {
        return response.ok ? response.json() : null;
      })
      .then(function (model) {
        if (model !== null) {
          renderResources(model);
        }
      })
      .catch(function (error) {
        console.error(error);
      });
  }

  function render(data) {
    rememberFocus();
    document.getElementById("generated-at").textContent = "generated at " + data.generated_at;
    refreshPartyFilterOptions(data.parties);
    refreshRaidFilterOptions(data.raids);
    var filtered = applyRaidFilter(applyPartyFilter(data));
    renderAsks(filtered.asks, filtered.blocked, filtered.parties);
    renderNotices(filtered.notices);
    renderDispatcher(filtered.dispatcher);
    renderMergeQueues(filtered.merge_queues);
    renderDrift(filtered.drift);
    renderProjects(filtered.projects);
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
      .catch(function (error) {
        console.error(error);
      });
  }

  function fetchBoard() {
    fetch(BOARD_URL)
      .then(function (response) {
        return response.json();
      })
      .then(render)
      .catch(function (error) {
        console.error(error);
      });
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
    renderAnsweredAsks();
    fetchSession();
    fetchBoard();
    fetchResources();
    setInterval(fetchBoard, REFRESH_INTERVAL_MS);
    setInterval(fetchResources, REFRESH_INTERVAL_MS);
  });
})();
