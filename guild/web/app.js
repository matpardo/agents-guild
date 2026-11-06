(function () {
  "use strict";

  function readToken() {
    var match = /^#t=([A-Za-z0-9_-]+)$/.exec(window.location.hash);
    if (match === null) {
      try {
        return window.sessionStorage.getItem("guild-token");
      } catch (error) {
        return null;
      }
    }
    try {
      window.sessionStorage.setItem("guild-token", match[1]);
    } catch (error) {
      console.error(error);
    }
    window.history.replaceState(null, "", window.location.pathname + window.location.search);
    return match[1];
  }

  var REFRESH_INTERVAL_MS = 10000;
  var BOARD_URL = "/api/board";
  var RESOURCES_URL = "/api/resources";
  var COMPACT_URL = "/api/compact";
  var COLLECT_URL = "/api/resources/collect";
  var REALM_REFRESH_URL = "/api/realm/refresh";
var REALM_DOCTOR_URL = "/api/realm/doctor";
var REALM_INBOX_REFRESH_URL = "/api/realm/inbox/refresh";
var REALM_FLAG_TEXT = "[flagged: looks like an instruction or a command] read it yourself before giving it to an agent";
  var ANSWERED_ASKS_URL = "/api/asks/answered";
  var RESOURCE_ITEMS_PER_CATEGORY = 10;
  var NO_RESOURCES_MESSAGE = "no samples yet; run guild resources collect";
  var EMPTY_REASON_MESSAGE = "write a reason first";
  var NOTICE_FORM_FOCUS_KEY = "notice-form";
  var NOTICE_TTLS = ["1h", "8h", "1d", "3d"];
  var RAID_PAUSE_CONFIRM_TEXT = "Pausing tells members to hand off.";
  var EMPTY_ANSWER_MESSAGE = "write an answer first";
  var DEFAULT_BRANCHES = ["main", "master"];
  var BLOCKED_EXTERNAL_TEXT = "blocked: manual";
  var STOPPED_WITHOUT_REPORT_TEXT = "stopped without report";
  var NO_SESSION_MESSAGE = "session token missing, reopen the URL printed by guild web";
  var sessionToken = readToken();

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
    soloMenuOpen: false,
    renderedHash: "",
    resourcesModel: null,
    realmModel: null,
    realmBusy: false,
    realmStatus: "",
realmFetchNote: "",
realmDoctorLines: [],
    noticesOpen: true,
    queueDetailOpen: {},
    openResourceProjects: {},
    openContexts: {},
    drafts: {},
    statuses: {},
    busy: {},
    prBlockOpen: {},
    prRelinkOpen: {},
    prRelinkDrafts: {},
    prDrafts: {},
    prStatuses: {},
    prBusy: {},
    focusedKey: null,
    sectionKeys: {},
    noticeStatuses: {},
    noticeBusy: {},
    memoryStatuses: {},
    memoryBusy: {},
    noticeAllStatus: "",
    noticeForm: { text: "", to: "", ttl: "1d" },
    noticeFormStatus: "",
    noticeFormBusy: false,
    ideasOpen: true,
    ideaForm: { title: "", description: "", requester: "", deadline: "", project: "" },
    ideaDrafts: {},
    ideaStatuses: {},
    ideaBusy: {},
    ideaLinkChoices: {},
    questForms: {},
    questStatuses: {},
    questBusy: {},
    questTakeChoices: {},
    adventurerStatuses: {},
    adventurerBusy: {},
    raidPauseOpen: {},
    raidStatuses: {},
    raidBusy: {},
    baseStatuses: {},
    partyHandoffStatuses: {},
    partyHandoffBusy: {},
    partyParkOpen: {},
    partyParkDrafts: {},
    partyParkStatuses: {},
    partyParkBusy: {},
    compactStatus: "",
    compactBusy: false,
    collectStatus: "",
    collectBusy: false,
    taskMoveStatuses: {},
    taskDiscardStatuses: {},
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

  function appendBold(parent, line) {
    var pattern = /\*\*(.+?)\*\*/g;
    var last = 0;
    var match = pattern.exec(line);
    while (match !== null) {
      parent.appendChild(document.createTextNode(line.slice(last, match.index)));
      parent.appendChild(textEl("strong", match[1]));
      last = match.index + match[0].length;
      match = pattern.exec(line);
    }
    parent.appendChild(document.createTextNode(line.slice(last)));
  }

  function renderAskText(text) {
    var container = el("div");
    container.className = "ask-text";
    text.split("\n\n").forEach(function (paragraph) {
      var node = el("p");
      paragraph.split("\n").forEach(function (line, index) {
        if (index > 0) {
          node.appendChild(el("br"));
        }
        appendBold(node, line);
      });
      container.appendChild(node);
    });
    return container;
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
      "waiting-permission": "The leader session is blocked on a Claude Code permission prompt or dialog; respond to it in that session.",
      "waiting-ask": "The party has an open ask and its leader is not working; answer the ask below.",
      "waiting-input": "The leader session is idle and waiting for you to type something in it.",
      "waiting-sub-agents": "The leader is waiting on its own subagents; nothing for you to do.",
      "waiting-background": "The leader is waiting on its own PR wait; nothing for you to do.",
      "stopped-with-work": "The leader session stopped but the party still has unfinished work; resume it.",
      working: "The leader session is running.",
      done: "The leader session stopped and the party has no work left.",
      unknown: "A running leader session never reported its status.",
      idle: "The party has no live session and nothing to do.",
      queued: "The party has no live session but has work waiting; start a fresh session from its brief.",
      parked: "The party handed off to wait on something outside development; resume it once that is resolved.",
      blocked: "The party has no live session and all its work left is blocked tasks.",
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
      "review first": "A human must review this PR before it is merged.",
      "blocked-external": "A person marked this PR as blocked manually; it waits on something outside development, do not try to fix it.",
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
      "ready (CI pending)": "Ready for you, but CI has not run on the head (billing or the CI label); check CI before merging.",
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
      "manual block": "A person blocked this PR manually; it waits on something outside development.",
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
      member: "The party is a member of the raid listed.",
    },
    partyWait: {
      "checks-pending": "A PR of this party is waiting for its checks to finish.",
      "checks-failing": "Checks fail on a PR of this party; the leader must fix them.",
      conflict: "A PR of this party has a merge conflict.",
      behind: "A PR of this party is behind its base branch.",
      "changes-requested": "A reviewer requested changes on a PR of this party.",
      threads: "A PR of this party has unresolved review threads.",
      "human-review": "A PR of this party needs a human review before merging.",
      "human-merge": "A PR of this party is ready to merge; merge it by hand.",
      "draft-green": "A draft PR of this party has green checks; mark it ready for review.",
      "ask-open": "The party has an open ask waiting for your answer.",
      "ask-answered-unseen": "An ask of this party was answered and its leader has not read the answer yet.",
      "notices-unread": "A notice for this party was issued and its leader has not read it yet.",
      "limit-reset": "The leader hit its usage limit; resume it by hand once the limit resets.",
    },
    blockedWait: {
      permission: "The session is blocked on a Claude Code permission prompt or dialog; respond to it in that session.",
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
      "session leads several parties": "One session leads more than one active party.",
      "epic done with open work": "The epic is marked done but still has open work.",
      "quest task not in SDD": "A quest task has no matching task in the SDD.",
      "task done, SDD not done": "A task is done in guild but not in the SDD.",
      "discarded task in SDD": "A task was discarded in guild but the SDD still lists it.",
      "adventurer task not in SDD": "An adventurer's PR merged but its task id never appeared in the epic's SDD tasks.",
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
      closeBlocked: "Every task is done but the epic drift gate blocks quest done; drift of other parties must be fixed by them, or pass --accept-drift.",
      openPrs: "Open PRs of this party against its cap (max_open_prs_per_party); PRs blocked externally are not counted.",
      projectOpenPrs: "Open PRs of the whole project against its cap (max_open_prs); PRs blocked externally are not counted.",
      capWait: "The cap is reached: merge the PR named before opening another.",
      hotFiles: "Files touched by as many open PRs as max_open_prs_per_file allows; expect merge conflicts.",
      findingClasses: "Review finding classes with the number of distinct PRs; at the threshold the class should become an architecture guard.",
      syncFreshness: "How long ago the SDD and the tracker were last synced successfully.",
      ideaLinkedForGood: "Linked for good: the holder tracks a PR.",
      noticeNew: "You have not marked this notice as seen yet.",
      noticeFlagged: "Non-human text matching an instruction or command pattern; shown as a caution, never blocked.",
      issued: "When the notice was issued, in local time.",
      timeLeft: "How long until the notice expires.",
      askBlocks: "How many references (tasks, PRs) still wait on this ask; 0 may mean the list is stale.",
      mainRed: "The main branch of this repo is failing; fix it before merging anything else.",
      mainBlocked: "CI cannot run on main because of an external cause; re-run main once it is fixed.",
      bindingReason: "Why the session chose this role when it started; recorded by the session itself.",
      generation: "How many times the party's leader session was replaced.",
      ctxHigh: "The leader session is near its context limit and should run guild handoff soon.",
      ctx: "Context used by the leader session / the percentage at which it is nudged to run guild handoff.",
      remaining: "Tasks not done in the party's active quests plus open PRs outside them; the tooltip lists done/total per quest.",
      allDone: "Every task of the party's active quests is done and no open PR is left outside them.",
      resumeCommand: "Run this to start the next generation of this party; it waits for a new leader.",
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

  function memoryUrl(party, seq) {
    return "/api/memory/" + party + "/" + seq + "/rm";
  }

  function adventurerDismissUrl(adventurerId) {
    return "/api/adventurers/" + adventurerId + "/dismiss";
  }

  function partyHandoffUrl(party) {
    return "/api/parties/" + party + "/hand-off";
  }

  function errorMessage(body) {
    if (body && typeof body.error === "string") {
      return body.error;
    }
    return "request failed";
  }

  function apiGet(url) {
    return fetch(url, { headers: { "X-Guild-Token": sessionToken } });
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

  function postMemoryAction(party, seq) {
    var itemId = party + "/" + seq;
    if (sessionToken === null) {
      state.memoryStatuses[itemId] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.memoryBusy[itemId] = true;
    state.memoryStatuses[itemId] = "sending...";
    fetchBoard();
    sendPost(memoryUrl(party, seq), {}).then(function (result) {
      delete state.memoryBusy[itemId];
      if (result.ok) {
        delete state.memoryStatuses[itemId];
      } else {
        state.memoryStatuses[itemId] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function postPartyHandoffAction(partyName) {
    if (sessionToken === null) {
      state.partyHandoffStatuses[partyName] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.partyHandoffBusy[partyName] = true;
    state.partyHandoffStatuses[partyName] = "sending...";
    fetchBoard();
    sendPost(partyHandoffUrl(partyName), {}).then(function (result) {
      delete state.partyHandoffBusy[partyName];
      if (result.ok) {
        delete state.partyHandoffStatuses[partyName];
      } else {
        state.partyHandoffStatuses[partyName] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function postPartyParkAction(partyName, action, payload) {
    if (sessionToken === null) {
      state.partyParkStatuses[partyName] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.partyParkBusy[partyName] = true;
    state.partyParkStatuses[partyName] = "sending...";
    fetchBoard();
    sendPost("/api/parties/" + partyName + "/" + action, payload).then(function (result) {
      delete state.partyParkBusy[partyName];
      if (result.ok) {
        delete state.partyParkOpen[partyName];
        delete state.partyParkDrafts[partyName];
        delete state.partyParkStatuses[partyName];
      } else {
        state.partyParkStatuses[partyName] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function submitPartyPark(partyName) {
    var text = state.partyParkDrafts[partyName] || "";
    if (text.trim() === "") {
      state.partyParkStatuses[partyName] = EMPTY_REASON_MESSAGE;
      fetchBoard();
      return;
    }
    postPartyParkAction(partyName, "park", { reason: text });
  }

  function postAdventurerDismiss(adventurerId) {
    if (sessionToken === null) {
      state.adventurerStatuses[adventurerId] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.adventurerBusy[adventurerId] = true;
    state.adventurerStatuses[adventurerId] = "sending...";
    fetchBoard();
    sendPost(adventurerDismissUrl(adventurerId), {}).then(function (result) {
      delete state.adventurerBusy[adventurerId];
      if (result.ok) {
        delete state.adventurerStatuses[adventurerId];
      } else {
        state.adventurerStatuses[adventurerId] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function compactResultText(body) {
    return body.message.split("\n").join("; ");
  }

  function postCompact() {
    if (sessionToken === null) {
      state.compactStatus = NO_SESSION_MESSAGE;
      showResources();
      return;
    }
    state.compactBusy = true;
    state.compactStatus = "compacting...";
    showResources();
    sendPost(COMPACT_URL, {}).then(function (result) {
      state.compactBusy = false;
      state.compactStatus = result.ok ? compactResultText(result.body) : errorMessage(result.body);
      showResources();
      fetchResources();
    });
  }

  function postCollect() {
    if (sessionToken === null) {
      state.collectStatus = NO_SESSION_MESSAGE;
      showResources();
      return;
    }
    state.collectBusy = true;
    state.collectStatus = "sampling...";
    showResources();
    sendPost(COLLECT_URL, {}).then(function (result) {
      state.collectBusy = false;
      state.collectStatus = result.ok ? result.body.message : errorMessage(result.body);
      showResources();
      fetchResources();
    });
  }

  function taskMoveUrl(quest, tid) {
    return "/api/quests/" + quest + "/tasks/" + tid + "/move";
  }

  function postTaskMove(quest, tid, target) {
    var key = quest + "/" + tid;
    if (sessionToken === null) {
      state.taskMoveStatuses[key] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.taskMoveStatuses[key] = "sending...";
    fetchBoard();
    sendPost(taskMoveUrl(quest, tid), { to: target }).then(function (result) {
      if (result.ok) {
        delete state.taskMoveStatuses[key];
      } else {
        state.taskMoveStatuses[key] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function postTaskDiscard(quest, tid, action, payload) {
    var key = quest + "/" + tid;
    if (sessionToken === null) {
      state.taskDiscardStatuses[key] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.taskDiscardStatuses[key] = "sending...";
    fetchBoard();
    sendPost("/api/quests/" + quest + "/tasks/" + tid + "/" + action, payload).then(function (result) {
      if (result.ok) {
        delete state.taskDiscardStatuses[key];
      } else {
        state.taskDiscardStatuses[key] = errorMessage(result.body);
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

  function postNoticeCreate() {
    if (sessionToken === null) {
      state.noticeFormStatus = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.noticeFormBusy = true;
    state.noticeFormStatus = "sending...";
    fetchBoard();
    sendPost("/api/notices/create", state.noticeForm).then(function (result) {
      state.noticeFormBusy = false;
      state.noticeFormStatus = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        state.noticeForm = { text: "", to: state.noticeForm.to, ttl: state.noticeForm.ttl };
      }
      fetchBoard();
    });
  }

  function postRaidAction(raidName, action) {
    if (sessionToken === null) {
      state.raidStatuses[raidName] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.raidBusy[raidName] = true;
    state.raidStatuses[raidName] = "sending...";
    fetchBoard();
    sendPost("/api/raids/" + raidName + "/" + action, {}).then(function (result) {
      delete state.raidBusy[raidName];
      if (result.ok) {
        delete state.raidPauseOpen[raidName];
        delete state.raidStatuses[raidName];
      } else {
        state.raidStatuses[raidName] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function postBaseAction(repo, action) {
    if (sessionToken === null) {
      state.baseStatuses[repo] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.baseStatuses[repo] = "sending...";
    fetchBoard();
    sendPost("/api/bases/" + repo + "/" + action, {}).then(function (result) {
      if (result.ok) {
        delete state.baseStatuses[repo];
      } else {
        state.baseStatuses[repo] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function postPrAction(location, ref, action, payload) {
    var key = location + "|" + ref;
    if (sessionToken === null) {
      state.prStatuses[key] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.prBusy[key] = true;
    state.prStatuses[key] = "sending...";
    fetchBoard();
    sendPost(prUrl(ref, action), payload).then(function (result) {
      delete state.prBusy[key];
      if (result.ok) {
        delete state.prBlockOpen[key];
        delete state.prRelinkOpen[key];
        delete state.prRelinkDrafts[key];
        delete state.prDrafts[key];
        delete state.prStatuses[key];
      } else {
        state.prStatuses[key] = errorMessage(result.body);
      }
      fetchBoard();
    });
  }

  function submitBlock(location, ref) {
    var key = location + "|" + ref;
    var text = state.prDrafts[key] || "";
    if (text.trim() === "") {
      state.prStatuses[key] = EMPTY_REASON_MESSAGE;
      fetchBoard();
      return;
    }
    postPrAction(location, ref, "block", { reason: text });
  }

  function prButton(location, ref, label, handler) {
    var button = textEl("button", label);
    button.type = "button";
    button.disabled = state.prBusy[location + "|" + ref] === true;
    button.addEventListener("click", handler);
    return button;
  }

  function renderBlockInput(ref, location) {
    var key = location + "|" + ref;
    var input = el("input");
    input.type = "text";
    input.className = "block-reason";
    input.placeholder = "reason";
    input.value = state.prDrafts[key] || "";
    input.disabled = state.prBusy[key] === true;
    input.dataset.focusKey = key;
    input.addEventListener("input", function () {
      state.prDrafts[key] = input.value;
    });
    return input;
  }

  function relinkPayload(key) {
    var draft = state.prRelinkDrafts[key] || {};
    var payload = {};
    if ((draft.task || "").trim() !== "") {
      payload.task = draft.task.trim();
    }
    if ((draft.card || "").trim() !== "") {
      payload.card = draft.card.trim();
    }
    return payload;
  }

  function submitRelink(location, ref) {
    var key = location + "|" + ref;
    var payload = relinkPayload(key);
    if (payload.task === undefined && payload.card === undefined) {
      state.prStatuses[key] = "enter a task or a card";
      fetchBoard();
      return;
    }
    postPrAction(location, ref, "relink", payload);
  }

  function renderRelinkInput(location, ref, field, placeholder) {
    var key = location + "|" + ref;
    var input = el("input");
    input.type = "text";
    input.className = "block-reason";
    input.placeholder = placeholder;
    input.value = (state.prRelinkDrafts[key] || {})[field] || "";
    input.disabled = state.prBusy[key] === true;
    input.dataset.focusKey = key + "|" + field;
    input.addEventListener("input", function () {
      var draft = state.prRelinkDrafts[key] || {};
      draft[field] = input.value;
      state.prRelinkDrafts[key] = draft;
    });
    return input;
  }

  function renderPrLinkControls(ref, location) {
    var key = location + "|" + ref;
    var controls = el("span");
    controls.className = "pr-block-controls";
    if (state.prRelinkOpen[key]) {
      controls.appendChild(renderRelinkInput(location, ref, "task", "quest/tid"));
      controls.appendChild(renderRelinkInput(location, ref, "card", "card key"));
      controls.appendChild(
        prButton(location, ref, "Confirm relink", function () {
          submitRelink(location, ref);
        })
      );
    } else {
      controls.appendChild(
        prButton(location, ref, "Relink", function () {
          state.prRelinkOpen[key] = true;
          fetchBoard();
        })
      );
    }
    controls.appendChild(
      prButton(location, ref, "Untrack", function () {
        if (window.confirm("Stop tracking " + ref + "?")) {
          postPrAction(location, ref, "untrack", {});
        }
      })
    );
    return controls;
  }

  function renderPrBlockControls(ref, blockedExternal, location) {
    var key = location + "|" + ref;
    var controls = el("span");
    controls.className = "pr-block-controls";
    if (isManuallyBlocked(blockedExternal)) {
      controls.appendChild(
        prButton(location, ref, "Unblock", function () {
          postPrAction(location, ref, "unblock", {});
        })
      );
    } else if (state.prBlockOpen[key]) {
      controls.appendChild(renderBlockInput(ref, location));
      controls.appendChild(
        prButton(location, ref, "Confirm block", function () {
          submitBlock(location, ref);
        })
      );
    } else {
      controls.appendChild(
        prButton(location, ref, "Block manually", function () {
          state.prBlockOpen[key] = true;
          fetchBoard();
        })
      );
    }
    controls.appendChild(renderPrLinkControls(ref, location));
    var status = textEl("span", state.prStatuses[key] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function isManuallyBlocked(reason) {
    return typeof reason === "string" && reason !== "";
  }

  function renderBlockedExternalPill(reason) {
    var pill = textEl("span", BLOCKED_EXTERNAL_TEXT);
    pill.className = "pill lifecycle-blocked-external";
    explain(pill, "flag", "blocked-external");
    if (isManuallyBlocked(reason)) {
      pill.title = pill.title + " Set by a person. Reason: " + reason;
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
    return lines;
  }

  function renderTaskPaths(ref) {
    var lines = [];
    if (ref.missing || ref.kind !== "task") {
      return lines;
    }
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
    ];
    if (origin.handoff_path) {
      lines.push(detailLine([detailText("span", "handoff: ", "Latest handoff file of the party"), detailText("code", origin.handoff_path, "Latest handoff file of the party")]));
    }
    return lines;
  }

  function renderDigIn(model) {
    var dig = el("details");
    dig.className = "ask-dig-in";
    dig.appendChild(detailText("summary", "dig in", "Spec paths, origin session and resume command"));
    model.refs.forEach(function (ref) {
      appendAll(dig, renderTaskPaths(ref));
    });
    appendAll(dig, renderOriginDetail(model.origin));
    if (model.resume) {
      dig.appendChild(detailLine([detailText("span", "resume: ", "Command that reopens the asking session"), detailText("code", model.resume, "Command that reopens the asking session")]));
    }
    return dig;
  }

  function renderAskDetail(model) {
    var wrapper = el("div");
    wrapper.className = "ask-detail";
    model.refs.forEach(function (ref) {
      appendAll(wrapper, renderRefDetail(ref));
    });
    if (model.answer !== null) {
      wrapper.appendChild(detailLine([detailText("span", "answer:", "Answer given to the ask")]));
      wrapper.appendChild(renderAskText(model.answer));
    }
    wrapper.appendChild(renderDigIn(model));
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
    apiGet("/api/asks/" + askId)
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
    details.appendChild(detailText("summary", "detail", "Task, card and PR behind this ask, and a dig in section with the origin session"));
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
    if (ask.recommend !== null) {
      var recommend = el("div");
      recommend.className = "ask-recommend";
      recommend.appendChild(textEl("strong", "recommend:"));
      recommend.appendChild(renderAskText(ask.recommend));
      article.appendChild(recommend);
    }
    article.appendChild(textEl("p", "refs: " + ask.refs.join(", ")));
    if (ask.dates !== null) {
      article.appendChild(classedText("p", ask.dates, "muted"));
    }
    article.appendChild(explain(textEl("p", blocksText(ask)), "ui", "askBlocks"));

    var details = el("details");
    details.open = contextOpen(ask.id);
    details.appendChild(textEl("summary", "context"));
    details.appendChild(renderAskText(ask.context));
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
    line.appendChild(document.createTextNode(" · "));
    line.appendChild(explain(textEl("span", entry.label), "blockedWait", entry.wait));
    if (entry.detail) {
      line.appendChild(document.createTextNode(" · "));
      line.appendChild(textEl("code", entry.detail));
    }
    return line;
  }

  function ctxHighCount(parties) {
    return parties.filter(function (party) {
      return party.ctx !== null && party.ctx.high;
    }).length;
  }

  function renderSoloPending(entry) {
    var line = el("p");
    line.className = "blocked-session";
    line.appendChild(textEl("strong", entry.name));
    line.appendChild(document.createTextNode(" [" + entry.class + "] " + entry.repo + " · "));
    line.appendChild(textEl("code", entry.pending));
    return line;
  }

  function renderAsks(asks, blocked, parties, soloPending) {
    var section = document.getElementById("asks");
    var ctxHigh = ctxHighCount(parties);
    clear(section);
    section.appendChild(
      textEl(
        "h2",
        "asks (" +
          asks.length +
          ") · blocked (" +
          blocked.length +
          ") · context high (" +
          ctxHigh +
          ") · solo (" +
          soloPending.length +
          ")"
      )
    );
    if (asks.length === 0 && blocked.length === 0 && ctxHigh === 0 && soloPending.length === 0) {
      section.appendChild(textEl("p", "nothing needs you"));
      return;
    }
    appendAll(section, blocked.map(renderBlocked));
    appendAll(section, soloPending.map(renderSoloPending));
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
    if (ask.answer !== null) {
      article.appendChild(textEl("strong", "answer:"));
      article.appendChild(renderAskText(ask.answer));
    }
    if (ask.dates !== null) {
      article.appendChild(classedText("p", ask.dates, "muted"));
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
    apiGet(ANSWERED_ASKS_URL + "?page=" + answered.page)
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

  function renderStatusDetail(status) {
    if ((status.name !== "parked" && status.name !== "blocked") || status.detail === null) {
      return null;
    }
    var detail = textEl("span", status.detail);
    detail.className = "status-detail";
    detail.title = status.detail;
    return detail;
  }

  function renderNotice(notice) {
    var article = el("article");
    article.className = "card notice";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("span", "#" + notice.id));
    head.appendChild(textEl("span", notice.author));
    head.appendChild(explain(textEl("span", notice.issued), "ui", "issued"));
    head.appendChild(explain(textEl("span", notice.scope), "scope", scopeKind(notice.scope)));
    head.appendChild(explain(textEl("span", notice.time_left), "ui", "timeLeft"));
    if (!notice.seen) {
      var badge = textEl("span", "new");
      badge.className = "badge notice-new";
      head.appendChild(explain(badge, "ui", "noticeNew"));
    }
    if (notice.flagged) {
      var flagBadge = textEl("span", "flagged");
      flagBadge.className = "badge notice-flagged";
      head.appendChild(explain(flagBadge, "ui", "noticeFlagged"));
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

  function noticeTargets(projects, raids) {
    return projects
      .map(function (project) {
        return "project:" + project.name;
      })
      .concat(
        raids.map(function (raid) {
          return "raid:" + raid.name;
        })
      );
  }

  function noticeSelect(values, current, onChange) {
    var select = el("select");
    values.forEach(function (value) {
      select.appendChild(option(value));
    });
    select.value = current;
    select.disabled = state.noticeFormBusy;
    select.addEventListener("change", function () {
      onChange(select.value);
    });
    return select;
  }

  function renderNoticeForm(projects, raids) {
    var targets = noticeTargets(projects, raids);
    if (targets.indexOf(state.noticeForm.to) === -1) {
      state.noticeForm.to = targets.length > 0 ? targets[0] : "";
    }
    var form = el("div");
    form.className = "notice-actions notice-form";
    var input = el("input");
    input.type = "text";
    input.className = "block-reason notice-text";
    input.placeholder = "new notice";
    input.value = state.noticeForm.text;
    input.disabled = state.noticeFormBusy;
    input.dataset.focusKey = NOTICE_FORM_FOCUS_KEY;
    input.addEventListener("input", function () {
      state.noticeForm.text = input.value;
    });
    form.appendChild(input);
    form.appendChild(
      noticeSelect(targets, state.noticeForm.to, function (value) {
        state.noticeForm.to = value;
      })
    );
    form.appendChild(
      noticeSelect(NOTICE_TTLS, state.noticeForm.ttl, function (value) {
        state.noticeForm.ttl = value;
      })
    );
    var button = textEl("button", "Create notice");
    button.type = "button";
    button.disabled = state.noticeFormBusy;
    button.addEventListener("click", postNoticeCreate);
    form.appendChild(button);
    var status = textEl("span", state.noticeFormStatus);
    status.className = "ask-status";
    form.appendChild(status);
    return form;
  }

  function renderRaidControls(raid) {
    var controls = el("span");
    controls.className = "pr-block-controls";
    var busy = state.raidBusy[raid.name] === true;
    var addButton = function (label, handler) {
      var button = textEl("button", label);
      button.type = "button";
      button.disabled = busy;
      button.addEventListener("click", handler);
      controls.appendChild(button);
    };
    if (raid.paused) {
      addButton("Resume raid", function () {
        postRaidAction(raid.name, "resume");
      });
    } else if (state.raidPauseOpen[raid.name]) {
      controls.appendChild(textEl("span", RAID_PAUSE_CONFIRM_TEXT));
      addButton("Confirm pause", function () {
        postRaidAction(raid.name, "pause");
      });
    } else {
      addButton("Pause raid", function () {
        state.raidPauseOpen[raid.name] = true;
        fetchBoard();
      });
    }
    var status = textEl("span", state.raidStatuses[raid.name] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function renderRaid(raid) {
    var article = el("article");
    article.className = "card raid-card";
    article.appendChild(textEl("h3", raid.name));
    if (raid.paused) {
      article.appendChild(classedText("span", "paused", "pill lifecycle-blocked-external"));
    }
    article.appendChild(renderRaidControls(raid));
    return article;
  }

  function renderRaids(raids) {
    var section = document.getElementById("raids");
    clear(section);
    if (raids.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "raids"));
    appendAll(section, raids.map(renderRaid));
  }

  function renderNotices(notices, projects, raids) {
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
    details.appendChild(renderNoticeForm(projects, raids));
    details.appendChild(renderSeenAllControls(newCount));
    appendAll(details, notices.map(renderNotice));
    section.appendChild(details);
  }

  function ideaPayload(draft) {
    return {
      title: draft.title,
      description: draft.description,
      requester: draft.requester === "" ? null : draft.requester,
      deadline: draft.deadline === "" ? null : draft.deadline,
      project: draft.project === "" ? null : draft.project,
    };
  }

  function postIdea(url, payload, key, onSuccess) {
    if (sessionToken === null) {
      state.ideaStatuses[key] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.ideaBusy[key] = true;
    state.ideaStatuses[key] = "sending...";
    fetchBoard();
    sendPost(url, payload).then(function (result) {
      delete state.ideaBusy[key];
      state.ideaStatuses[key] = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        onSuccess();
      }
      fetchBoard();
    });
  }

  function ideaInput(draft, key, field, type, placeholder, disabled) {
    var input = el("input");
    input.dataset.focusKey = "idea-" + key + "-" + field;
    input.type = type;
    input.className = "block-reason idea-" + field;
    input.placeholder = placeholder;
    input.value = draft[field];
    input.disabled = disabled;
    input.addEventListener("input", function () {
      draft[field] = input.value;
    });
    return input;
  }

  function ideaDescriptionArea(draft, key, disabled) {
    var area = el("textarea");
    area.dataset.focusKey = "idea-" + key + "-description";
    area.rows = 3;
    area.className = "answer-field idea-description";
    area.placeholder = "description";
    area.value = draft.description;
    area.disabled = disabled;
    area.addEventListener("input", function () {
      draft.description = area.value;
    });
    return area;
  }

  function ideaProjectSelect(draft, projectNames, disabled) {
    var select = el("select");
    [""].concat(projectNames).forEach(function (name) {
      var node = option(name);
      if (name === "") {
        node.textContent = "no project";
      }
      select.appendChild(node);
    });
    select.value = draft.project;
    select.disabled = disabled;
    select.addEventListener("change", function () {
      draft.project = select.value;
    });
    return select;
  }

  function renderIdeaFields(draft, key, projectNames, busy) {
    var fields = el("div");
    fields.className = "notice-actions idea-fields";
    fields.appendChild(ideaInput(draft, key, "title", "text", "title", busy));
    fields.appendChild(ideaDescriptionArea(draft, key, busy));
    fields.appendChild(ideaInput(draft, key, "requester", "text", "requester (optional)", busy));
    fields.appendChild(ideaInput(draft, key, "deadline", "text", "deadline YYYY-MM-DD", busy));
    fields.appendChild(ideaProjectSelect(draft, projectNames, busy));
    return fields;
  }

  function ideaActionButton(label, busy, handler) {
    var button = textEl("button", label);
    button.type = "button";
    button.disabled = busy;
    button.addEventListener("click", handler);
    return button;
  }

  function renderIdeaForm(projectNames) {
    var busy = state.ideaBusy.new === true;
    var form = el("div");
    form.className = "idea-form";
    form.appendChild(renderIdeaFields(state.ideaForm, "new", projectNames, busy));
    var actions = el("div");
    actions.className = "notice-actions";
    actions.appendChild(
      ideaActionButton("Add idea", busy, function () {
        postIdea("/api/ideas/create", ideaPayload(state.ideaForm), "new", function () {
          state.ideaForm = { title: "", description: "", requester: "", deadline: "", project: "" };
        });
      })
    );
    actions.appendChild(classedText("span", state.ideaStatuses.new || "", "ask-status"));
    form.appendChild(actions);
    return form;
  }

  function ideaMeta(idea) {
    var parts = [];
    if (idea.project !== null) {
      parts.push(idea.project);
    }
    if (idea.requester !== null) {
      parts.push("from " + idea.requester);
    }
    if (idea.deadline !== null) {
      parts.push("due " + idea.deadline + (idea.overdue ? " (overdue)" : ""));
    }
    if (idea.dates) {
      parts.push(idea.dates);
    }
    return parts.join(" · ");
  }

  function ideaSummary(idea) {
    return "#" + idea.id + " " + idea.title;
  }

  function ideaPartyLabel(party) {
    return party.state === "closed" ? party.name + " (closed)" : party.name;
  }

  function ideaAdventurerLabel(adventurer) {
    var label = "adventurer " + adventurer.id;
    return adventurer.state === "active" ? label : label + " (" + adventurer.state + ")";
  }

  function renderIdeaHolder(idea, label, unlinkPayload, hasPrs, busy) {
    var item = el("span");
    item.className = "idea-party";
    var text = textEl("span", label);
    item.appendChild(text);
    if (hasPrs) {
      explain(text, "ui", "ideaLinkedForGood");
      return item;
    }
    item.appendChild(
      ideaActionButton("Unlink", busy, function () {
        postIdea("/api/ideas/" + idea.id + "/unlink", unlinkPayload, idea.id, function () {});
      })
    );
    return item;
  }

  function ideaHolderChoices(idea, partyNames, adventurerIds) {
    var linkedParties = idea.parties.map(function (party) {
      return party.name;
    });
    var linkedAdventurers = idea.adventurers.map(function (adventurer) {
      return adventurer.id;
    });
    var parties = partyNames
      .filter(function (name) {
        return linkedParties.indexOf(name) === -1;
      })
      .map(function (name) {
        return { value: "party:" + name, label: name };
      });
    var adventurers = adventurerIds
      .filter(function (id) {
        return linkedAdventurers.indexOf(id) === -1;
      })
      .map(function (id) {
        return { value: "adventurer:" + id, label: "adventurer " + id };
      });
    return parties.concat(adventurers);
  }

  function renderIdeaLinkSelect(idea, choices, busy) {
    var select = el("select");
    select.dataset.focusKey = "idea-" + idea.id + "-link";
    choices.forEach(function (choice) {
      var opt = option(choice.value);
      opt.textContent = choice.label;
      select.appendChild(opt);
    });
    var values = choices.map(function (choice) {
      return choice.value;
    });
    if (values.indexOf(state.ideaLinkChoices[idea.id]) !== -1) {
      select.value = state.ideaLinkChoices[idea.id];
    }
    select.disabled = busy || choices.length === 0;
    select.addEventListener("change", function () {
      state.ideaLinkChoices[idea.id] = select.value;
    });
    return select;
  }

  function ideaLinkPayload(choice) {
    var separator = choice.indexOf(":");
    var kind = choice.slice(0, separator);
    var holder = choice.slice(separator + 1);
    return kind === "adventurer" ? { adventurer: Number(holder) } : { party: holder };
  }

  function renderIdeaLinks(idea, partyNames, adventurerIds) {
    var busy = state.ideaBusy[idea.id] === true;
    var links = el("div");
    links.className = "notice-actions idea-links";
    var linked = idea.parties.length + idea.adventurers.length;
    if (linked > 0) {
      links.appendChild(textEl("span", "worked by:"));
    }
    if (linked === 0) {
      links.appendChild(classedText("span", "not linked yet", "muted"));
    }
    appendAll(
      links,
      idea.parties.map(function (party) {
        return renderIdeaHolder(idea, ideaPartyLabel(party), { party: party.name }, party.has_prs, busy);
      })
    );
    appendAll(
      links,
      idea.adventurers.map(function (adventurer) {
        return renderIdeaHolder(
          idea,
          ideaAdventurerLabel(adventurer),
          { adventurer: adventurer.id },
          adventurer.has_prs,
          busy
        );
      })
    );
    var select = renderIdeaLinkSelect(idea, ideaHolderChoices(idea, partyNames, adventurerIds), busy);
    links.appendChild(select);
    links.appendChild(
      ideaActionButton("Link", select.disabled, function () {
        var choice = state.ideaLinkChoices[idea.id] || select.value;
        postIdea("/api/ideas/" + idea.id + "/link", ideaLinkPayload(choice), idea.id, function () {
          delete state.ideaLinkChoices[idea.id];
        });
      })
    );
    return links;
  }

  function renderIdeaView(article, idea, partyNames, adventurerIds) {
    var busy = state.ideaBusy[idea.id] === true;
    article.appendChild(textEl("h3", "#" + idea.id + " " + idea.title));
    article.appendChild(classedText("p", ideaMeta(idea), "muted"));
    article.appendChild(classedText("p", idea.description, "idea-description"));
    article.appendChild(renderIdeaLinks(idea, partyNames, adventurerIds));
    var actions = el("div");
    actions.className = "notice-actions";
    actions.appendChild(
      ideaActionButton("Edit", busy, function () {
        state.ideaDrafts[idea.id] = {
          title: idea.title,
          description: idea.description,
          requester: idea.requester === null ? "" : idea.requester,
          deadline: idea.deadline === null ? "" : idea.deadline,
          project: idea.project === null ? "" : idea.project,
        };
        fetchBoard();
      })
    );
    actions.appendChild(
      ideaActionButton("Delete", busy, function () {
        postIdea("/api/ideas/" + idea.id + "/delete", {}, idea.id, function () {});
      })
    );
    actions.appendChild(classedText("span", state.ideaStatuses[idea.id] || "", "ask-status"));
    article.appendChild(actions);
  }

  function renderIdeaEdit(article, idea, projectNames) {
    var draft = state.ideaDrafts[idea.id];
    var busy = state.ideaBusy[idea.id] === true;
    article.appendChild(renderIdeaFields(draft, idea.id, projectNames, busy));
    var actions = el("div");
    actions.className = "notice-actions";
    actions.appendChild(
      ideaActionButton("Save", busy, function () {
        postIdea("/api/ideas/" + idea.id + "/edit", ideaPayload(draft), idea.id, function () {
          delete state.ideaDrafts[idea.id];
        });
      })
    );
    actions.appendChild(
      ideaActionButton("Cancel", busy, function () {
        delete state.ideaDrafts[idea.id];
        fetchBoard();
      })
    );
    actions.appendChild(classedText("span", state.ideaStatuses[idea.id] || "", "ask-status"));
    article.appendChild(actions);
  }

  function renderIdea(idea, projectNames, partyNames, adventurerIds) {
    var article = el("article");
    article.className = idea.overdue ? "card idea idea-overdue" : "card idea";
    if (state.ideaDrafts[idea.id] === undefined) {
      renderIdeaView(article, idea, partyNames, adventurerIds);
      return article;
    }
    renderIdeaEdit(article, idea, projectNames);
    return article;
  }

  function renderIdeas(ideas, projectNames, partyNames, adventurerIds) {
    var section = document.getElementById("ideas");
    clear(section);
    var details = el("details");
    details.className = "ideas-section";
    details.open = state.ideasOpen;
    details.addEventListener("toggle", function () {
      state.ideasOpen = details.open;
    });
    var summary = el("summary");
    summary.appendChild(textEl("h2", "ideas (" + ideas.length + ")"));
    details.appendChild(summary);
    details.appendChild(renderIdeaForm(projectNames));
    appendAll(
      details,
      ideas.map(function (idea) {
        return renderIdea(idea, projectNames, partyNames, adventurerIds);
      })
    );
    section.appendChild(details);
  }

  function adventurerMeta(adventurer) {
    var parts = [adventurer.project, adventurer.state];
    if (adventurer.task !== null) {
      parts.push("task " + adventurer.task);
    }
    parts.push(adventurer.live ? "live" : "stopped");
    parts.push(adventurer.dates);
    return parts.join(" · ");
  }

  function renderAdventurerDismiss(adventurer) {
    var actions = el("div");
    actions.className = "notice-actions";
    var button = textEl("button", "Dismiss");
    button.type = "button";
    button.disabled = state.adventurerBusy[adventurer.id] === true;
    button.addEventListener("click", function () {
      postAdventurerDismiss(adventurer.id);
    });
    actions.appendChild(button);
    actions.appendChild(classedText("span", state.adventurerStatuses[adventurer.id] || "", "ask-status"));
    return actions;
  }

  function renderAdventurer(adventurer) {
    var article = el("article");
    article.className = "card adventurer";
    article.appendChild(textEl("h3", "adventurer " + adventurer.id + " " + adventurer.job));
    article.appendChild(classedText("p", adventurerMeta(adventurer), "muted"));
    if (adventurer.reason !== null) {
      article.appendChild(explain(textEl("p", "reason: " + adventurer.reason), "ui", "bindingReason"));
    }
    if (adventurer.stopped_without_report) {
      article.appendChild(classedText("span", STOPPED_WITHOUT_REPORT_TEXT, "pill stopped-without-report"));
    }
    if (adventurer.ideas.length > 0) {
      article.appendChild(textEl("p", "ideas: " + adventurer.ideas.map(ideaSummary).join(", ")));
    }
    if (adventurer.state === "done") {
      article.appendChild(textEl("p", "pending: " + adventurer.pending));
      article.appendChild(renderAdventurerDismiss(adventurer));
    }
    var prs = renderPrList(adventurer.prs);
    if (prs) {
      article.appendChild(prs);
    }
    return article;
  }

  function renderAdventurers(adventurers) {
    var section = document.getElementById("adventurers");
    clear(section);
    if (adventurers.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "adventurers (" + adventurers.length + ")"));
    appendAll(section, adventurers.map(renderAdventurer));
  }

  function healthJobMeta(job) {
    var parts = [job.project, job.state, "every " + job.every];
    parts.push("last done " + (job.last_done === null ? "never" : job.last_done));
    return parts.join(" \u00b7 ");
  }

  function renderHealthJob(job) {
    var article = el("article");
    article.className = "card health-job";
    article.appendChild(textEl("h3", job.name));
    article.appendChild(classedText("p", healthJobMeta(job), "muted"));
    if (job.state === "due") {
      article.appendChild(classedText("code", job.launch, "launch-command"));
    }
    return article;
  }

  function renderHealthJobs(jobs) {
    var section = document.getElementById("health-jobs");
    clear(section);
    var pending = jobs.filter(function (job) {
      return job.state !== "ok";
    });
    if (pending.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "health jobs (" + pending.length + ")"));
    appendAll(section, pending.map(renderHealthJob));
  }

  function shortLocalDate(iso) {
    var date = new Date(iso);
    if (isNaN(date.getTime())) {
      return iso;
    }
    function pad(value) {
      return String(value).padStart(2, "0");
    }
    return (
      date.getFullYear() + "-" + pad(date.getMonth() + 1) + "-" + pad(date.getDate()) +
      " " + pad(date.getHours()) + ":" + pad(date.getMinutes())
    );
  }

  function soloPlayerMeta(player) {
    var state = player.state;
    if (player.stalled_adventurer !== null) {
      state += ": session gone, run guild adventurer dismiss " + player.stalled_adventurer;
    } else if (player.retry_at !== null) {
      state += ": same trigger, retry after " + shortLocalDate(player.retry_at);
    } else if (player.waits_on.length > 0) {
      state += ": waits on " + player.waits_on.join(", ");
    }
    var parts = [player.class, player.repo, state, "on " + player.schedule, player.trigger === null ? "no trigger" : player.trigger];
    parts.push("last done " + (player.last_done === null ? "never" : shortLocalDate(player.last_done)));
    parts.push("last pending " + (player.last_pending === null ? "none" : player.last_pending));
    return parts.join(" \u00b7 ");
  }

  function renderSoloToMerge(entries) {
    var list = el("div");
    list.className = "solo-to-merge";
    list.appendChild(classedText("p", "to merge", "muted"));
    appendAll(
      list,
      entries.map(function (entry) {
        var row = el("p");
        row.appendChild(link(entry.url, entry.ref));
        row.appendChild(textEl("span", " " + entry.title));
        return row;
      })
    );
    return list;
  }

  function renderSoloPlayer(player) {
    var article = el("article");
    article.className = "card solo-player";
    article.appendChild(textEl("h3", player.name));
    article.appendChild(classedText("p", soloPlayerMeta(player), "muted"));
    if (player.state === "due" || player.state === "idle" || player.state === "paused") {
      article.appendChild(classedText("code", player.launch, "launch-command"));
    }
    if (player.to_merge.length > 0) {
      article.appendChild(renderSoloToMerge(player.to_merge));
    }
    if (player.runs.length > 0) {
      article.appendChild(renderSoloRuns(player.runs));
    }
    return article;
  }

  function soloRunLine(run) {
    var parts = [shortLocalDate(run.started_at), run.state];
    if (run.duration !== null) {
      parts.push(Math.round(run.duration / 60) + "m");
    }
    if (run.pending !== null) {
      parts.push(run.pending);
    }
    if (run.prs.length > 0) {
      parts.push(
        "PRs: " +
          run.prs
            .map(function (pr) {
              return pr.ref + " " + pr.lifecycle;
            })
            .join(", ")
      );
    }
    return parts.join(" \u00b7 ");
  }

  function renderSoloRuns(runs) {
    var details = el("details");
    details.appendChild(textEl("summary", "runs (" + runs.length + ")"));
    appendAll(
      details,
      runs.map(function (run) {
        return classedText("p", soloRunLine(run), "muted");
      })
    );
    return details;
  }

  function soloChannelLine(message) {
    var who = message.class === "" ? message.name : message.name + " [" + message.class + "]";
    return classedText("p", shortLocalDate(message.ts) + " \u00b7 " + who + " \u00b7 " + message.text, "solo-message");
  }

  function soloProjectNames(players) {
    var names = [];
    players.forEach(function (player) {
      if (names.indexOf(player.project) === -1) {
        names.push(player.project);
      }
    });
    return names.sort();
  }

  function renderSoloPanel(project, players, channel) {
    var panel = el("div");
    panel.className = "solo-project";
    panel.role = "tabpanel";
    appendAll(
      panel,
      players
        .filter(function (player) {
          return player.project === project;
        })
        .map(renderSoloPlayer)
    );
    panel.appendChild(textEl("h3", "channel"));
    var messages = channel.filter(function (message) {
      return message.project === project;
    });
    if (messages.length === 0) {
      panel.appendChild(classedText("p", "no messages yet", "muted"));
    }
    appendAll(panel, messages.map(soloChannelLine));
    return panel;
  }

  function renderSoloTabs(names, selected) {
    var bar = el("div");
    bar.className = "solo-tabs";
    bar.role = "tablist";
    appendAll(
      bar,
      names.map(function (name) {
        var tab = textEl("button", name);
        tab.type = "button";
        tab.role = "tab";
        tab.ariaSelected = name === selected ? "true" : "false";
        tab.addEventListener("click", function () {
          window.location.hash = "#solo-players/" + name;
        });
        return tab;
      })
    );
    return bar;
  }

  function renderSoloPlayers(players, channel, project) {
    var section = document.getElementById("solo-players");
    clear(section);
    if (players.length === 0) {
      return;
    }
    var names = soloProjectNames(players);
    var selected = names.indexOf(project) === -1 ? names[0] : project;
    section.appendChild(textEl("h2", "solo players (" + players.length + ")"));
    section.appendChild(renderSoloTabs(names, selected));
    section.appendChild(renderSoloPanel(selected, players, channel));
  }

  function renderMemoryItem(item) {
    var article = el("article");
    article.className = "card memory";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("span", item.id));
    if (item.flagged) {
      var flagBadge = textEl("span", "flagged");
      flagBadge.className = "badge memory-flagged";
      head.appendChild(flagBadge);
    }
    article.appendChild(head);
    article.appendChild(textEl("p", item.text));
    var actions = el("div");
    actions.className = "notice-actions";
    var button = textEl("button", "Remove");
    button.type = "button";
    button.disabled = state.memoryBusy[item.id] === true;
    button.addEventListener("click", function () {
      postMemoryAction(item.party, item.id.split("/")[1]);
    });
    actions.appendChild(button);
    var status = textEl("span", state.memoryStatuses[item.id] || "");
    status.className = "ask-status";
    actions.appendChild(status);
    article.appendChild(actions);
    return article;
  }

  function renderMemory(items) {
    var section = document.getElementById("memory");
    clear(section);
    if (items.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "memory (" + items.length + ")"));
    appendAll(section, items.map(renderMemoryItem));
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

  function postQuest(url, payload, key, onSuccess) {
    if (sessionToken === null) {
      state.questStatuses[key] = NO_SESSION_MESSAGE;
      fetchBoard();
      return;
    }
    state.questBusy[key] = true;
    state.questStatuses[key] = "sending...";
    fetchBoard();
    sendPost(url, payload).then(function (result) {
      delete state.questBusy[key];
      state.questStatuses[key] = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        onSuccess();
      }
      fetchBoard();
    });
  }

  function questTaskText(task) {
    var text = task.tid + " " + task.title;
    return task.adventurer === null ? text : text + " (held by adventurer " + task.adventurer + ")";
  }

  function renderQuestAssign(quest, parties) {
    var busy = state.questBusy[quest.slug] === true;
    var actions = el("div");
    actions.className = "notice-actions";
    var select = el("select");
    select.dataset.focusKey = "quest-" + quest.slug + "-party";
    parties.forEach(function (name) {
      select.appendChild(option(name));
    });
    if (parties.indexOf(state.questTakeChoices[quest.slug]) !== -1) {
      select.value = state.questTakeChoices[quest.slug];
    }
    select.disabled = busy || parties.length === 0;
    select.addEventListener("change", function () {
      state.questTakeChoices[quest.slug] = select.value;
    });
    actions.appendChild(select);
    actions.appendChild(
      ideaActionButton("Assign", select.disabled, function () {
        var party = state.questTakeChoices[quest.slug] || select.value;
        postQuest("/api/quests/" + quest.slug + "/take", { party: party }, quest.slug, function () {
          delete state.questTakeChoices[quest.slug];
        });
      })
    );
    actions.appendChild(classedText("span", state.questStatuses[quest.slug] || "", "ask-status"));
    return actions;
  }

  function renderOpenQuest(quest, parties) {
    var article = el("article");
    article.className = "card open-quest";
    article.appendChild(textEl("h4", quest.slug + " \u2014 " + quest.title));
    article.appendChild(classedText("p", quest.epic === null ? "no epic" : "epic " + quest.epic, "muted"));
    if (quest.dates) {
      article.appendChild(classedText("p", quest.dates, "muted"));
    }
    var list = el("ul");
    list.className = "task-list";
    appendAll(
      list,
      quest.tasks.map(function (task) {
        return textEl("li", questTaskText(task));
      })
    );
    article.appendChild(list);
    article.appendChild(renderQuestAssign(quest, parties));
    return article;
  }

  function questForm(formKey) {
    if (state.questForms[formKey] === undefined) {
      state.questForms[formKey] = { slug: "", title: "", tids: {} };
    }
    return state.questForms[formKey];
  }

  function questFormInput(form, formKey, field, placeholder, disabled) {
    var input = el("input");
    input.dataset.focusKey = "quest-" + formKey + "-" + field;
    input.type = "text";
    input.className = "block-reason quest-" + field;
    input.placeholder = placeholder;
    input.value = form[field];
    input.disabled = disabled;
    input.addEventListener("input", function () {
      form[field] = input.value;
    });
    return input;
  }

  function renderFreeTask(form, formKey, task, disabled) {
    var label = el("label");
    label.className = "free-task";
    var box = el("input");
    box.type = "checkbox";
    box.dataset.focusKey = "quest-" + formKey + "-" + task.tid;
    box.checked = form.tids[task.tid] === true;
    box.disabled = disabled;
    box.addEventListener("change", function () {
      form.tids[task.tid] = box.checked;
    });
    label.appendChild(box);
    label.appendChild(textEl("span", task.tid + " " + task.title));
    return label;
  }

  function renderFreeEpic(project, entry) {
    var formKey = project.name + "/" + entry.epic;
    var form = questForm(formKey);
    var busy = state.questBusy[formKey] === true;
    var block = el("div");
    block.className = "free-epic";
    block.appendChild(textEl("h4", "free tasks \u2014 " + entry.epic));
    appendAll(
      block,
      entry.tasks.map(function (task) {
        return renderFreeTask(form, formKey, task, busy);
      })
    );
    var actions = el("div");
    actions.className = "notice-actions";
    actions.appendChild(questFormInput(form, formKey, "slug", "quest slug", busy));
    actions.appendChild(questFormInput(form, formKey, "title", "title", busy));
    actions.appendChild(
      ideaActionButton("Create open quest", busy, function () {
        var tids = entry.tasks
          .map(function (task) {
            return task.tid;
          })
          .filter(function (tid) {
            return form.tids[tid] === true;
          });
        var payload = { project: project.name, slug: form.slug, title: form.title, epic: entry.epic, tasks: tids };
        postQuest("/api/quests/create-open", payload, formKey, function () {
          delete state.questForms[formKey];
        });
      })
    );
    actions.appendChild(classedText("span", state.questStatuses[formKey] || "", "ask-status"));
    block.appendChild(actions);
    return block;
  }

  function renderProjectQuestBoard(project) {
    var article = el("article");
    article.className = "card quest-board";
    article.appendChild(textEl("h3", project.name));
    appendAll(
      article,
      project.open_quests.map(function (quest) {
        return renderOpenQuest(quest, project.parties);
      })
    );
    appendAll(
      article,
      project.free_tasks.map(function (entry) {
        return renderFreeEpic(project, entry);
      })
    );
    return article;
  }

  function renderQuestBoard(projects) {
    var section = document.getElementById("quest-board");
    clear(section);
    if (projects.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "quest board"));
    appendAll(section, projects.map(renderProjectQuestBoard));
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

  function isReadyToMerge(entry) {
    return entry.human_state === "ready" || entry.human_state === "ready (CI pending)";
  }

  function renderReadyPill(entry) {
    var pill = textEl("span", entry.human_state);
    pill.className = "pill lifecycle-ready";
    return explain(pill, "queueState", entry.human_state);
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
        if (isManuallyBlocked(entry.blocked_external)) {
          head.appendChild(textEl("span", entry.blocked_external));
        }
        return;
      }
      var pill = textEl("span", label);
      pill.className = "pill lifecycle-" + label;
      head.appendChild(explainLabel(pill, label));
    });
    if (isReadyToMerge(entry)) {
      head.appendChild(renderReadyPill(entry));
    }
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
    var lines = entry.blockers.concat(entry.human_missing, entry.waits.map(function (wait) {
      return "wait: " + wait;
    }), entry.gates.map(function (gate) {
      return "gate: " + gate;
    }), entry.notes.map(function (note) {
      return "note: " + note;
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

  function renderAckButton(entry) {
    return prButton("queue", entry.ref, "Mark " + entry.unseen_comments + (entry.unseen_comments === 1 ? " comment" : " comments") + " read", function () {
      postPrAction("queue", entry.ref, "ack", {});
    });
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
    if (entry.unseen_comments > 0) {
      item.appendChild(renderAckButton(entry));
    }
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
    if (row.external !== null) {
      var blocked = "MAIN BLOCKED (" + row.external + ") " + row.repo + " \u2192 re-run main once " + row.external + " is fixed";
      return explain(classedText("p", blocked, "queue-main-red"), "ui", "mainBlocked");
    }
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

  function renderReadyItem(item) {
    var row = el("li");
    row.className = "ready-item";
    row.appendChild(link(item.url, item.ref));
    row.appendChild(textEl("span", item.title));
    row.appendChild(textEl("span", item.party === null ? "from " + item.from : item.party));
    if (item.review_first) {
      var pill = textEl("span", "review first");
      pill.className = "pill lifecycle-ready";
      row.appendChild(explain(pill, "flag", "review first"));
    }
    var notes = el("div");
    notes.className = "ready-notes";
    item.notes.forEach(function (note) {
      notes.appendChild(classedText("p", "note: " + note, "muted"));
    });
    row.appendChild(notes);
    return row;
  }

  function renderReadyForYou(items) {
    var section = document.getElementById("ready-for-you");
    clear(section);
    section.appendChild(textEl("h2", "ready for you"));
    if (items.length === 0) {
      section.appendChild(textEl("p", "nothing is ready for you"));
      return;
    }
    var list = el("ol");
    appendAll(list, items.map(renderReadyItem));
    section.appendChild(list);
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

  function percentOf(done, total) {
    return total === 0 ? 0 : Math.round((done * 100) / total);
  }

  function progressBar(done, total) {
    var bar = el("progress");
    bar.max = total;
    bar.value = done;
    return bar;
  }

  function progressRow(label, done, total) {
    var row = el("div");
    row.className = "epic-progress";
    row.appendChild(textEl("span", label + " " + done + "/" + total));
    row.appendChild(progressBar(done, total));
    return row;
  }

  function mergedBlockedGroups(parties) {
    var byReason = {};
    parties.forEach(function (party) {
      party.blocked_groups.forEach(function (group) {
        byReason[group.reason] = (byReason[group.reason] || []).concat(group.tids);
      });
    });
    return Object.keys(byReason)
      .map(function (reason) {
        return { reason: reason, tids: byReason[reason] };
      })
      .sort(function (a, b) {
        return b.tids.length - a.tids.length || (a.reason < b.reason ? -1 : 1);
      });
  }

  function renderProgress(parties) {
    var section = document.getElementById("progress");
    clear(section);
    section.appendChild(textEl("h2", "progress"));
    if (parties.length === 0) {
      section.appendChild(textEl("p", "no party in view"));
      return;
    }
    var quests = [];
    var counts = { active: 0, blocked: 0, queued: 0 };
    parties.forEach(function (party) {
      quests = quests.concat(party.remaining.quests);
      Object.keys(counts).forEach(function (key) {
        counts[key] += party.remaining[key];
      });
    });
    if (quests.length === 0) {
      section.appendChild(textEl("p", "no active quest"));
      return;
    }
    var done = quests.reduce(function (sum, quest) { return sum + quest.done; }, 0);
    var total = quests.reduce(function (sum, quest) { return sum + quest.total; }, 0);
    section.appendChild(textEl("p", done + "/" + total + " tasks done (" + percentOf(done, total) + "%)"));
    section.appendChild(progressBar(done, total));
    quests.forEach(function (quest) {
      section.appendChild(progressRow(quest.slug, quest.done, quest.total));
    });
    section.appendChild(
      textEl("p", "active " + counts.active + " · blocked " + counts.blocked + " · queued " + counts.queued)
    );
    mergedBlockedGroups(parties).forEach(function (group) {
      var line = textEl("p", group.tids.length + " blocked — " + group.reason);
      line.title = group.tids.join(", ");
      section.appendChild(line);
    });
  }

  function summedDailyTasks(parties) {
    if (parties.length === 0) {
      return [];
    }
    return parties[0].daily_tasks.map(function (entry, index) {
      return parties.reduce(
        function (total, party) {
          var day = party.daily_tasks[index];
          return {
            day: entry.day,
            created: total.created + day.created,
            done: total.done + day.done,
            active: total.active || day.active,
            existed: total.existed || day.existed,
          };
        },
        { day: entry.day, created: 0, done: 0, active: false, existed: false }
      );
    });
  }

  var DAILY_DASH_HINT =
    "no session event this day; a session that sat idle across midnight leaves no event and also shows -";

  var DAILY_X_HINT = "party did not exist yet";

  function dailyTaskRow(label, days, key) {
    var row = el("tr");
    row.appendChild(textEl("th", label));
    days.forEach(function (day) {
      if (!day.existed) {
        var missing = classedText("td", "x", "muted");
        missing.title = DAILY_X_HINT;
        row.appendChild(missing);
        return;
      }
      if (!day.active && day[key] === 0) {
        var cell = classedText("td", "-", "muted");
        cell.title = DAILY_DASH_HINT;
        row.appendChild(cell);
        return;
      }
      row.appendChild(textEl("td", String(day[key])));
    });
    return row;
  }

  function renderDailyTasks(parties) {
    var section = document.getElementById("daily-tasks");
    clear(section);
    section.appendChild(textEl("h2", "tasks per day"));
    var days = summedDailyTasks(parties);
    if (days.length === 0) {
      section.appendChild(textEl("p", "no party in view"));
      return;
    }
    var head = el("tr");
    head.appendChild(textEl("th", "day"));
    days.forEach(function (day, index) {
      head.appendChild(classedText("th", day.day.slice(5), index === days.length - 1 ? "today" : ""));
    });
    var table = el("table");
    table.className = "progress-table daily-tasks";
    table.appendChild(head);
    table.appendChild(dailyTaskRow("created", days, "created"));
    table.appendChild(dailyTaskRow("done", days, "done"));
    var scroller = el("div");
    scroller.className = "table-scroll";
    scroller.appendChild(table);
    section.appendChild(scroller);
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
    if (isManuallyBlocked(pr.blocked_external)) {
      row.appendChild(renderBlockedExternalPill(pr.blocked_external));
      row.appendChild(textEl("span", pr.blocked_external));
    }
    if (pr.base_branch && DEFAULT_BRANCHES.indexOf(pr.base_branch) === -1) {
      var base = textEl("span", "on " + pr.base_branch);
      base.className = "branch";
      row.appendChild(explain(base, "ui", "baseBranch"));
    }
    appendAll(row, renderReasonPills(pr.review_reasons));
    if (pr.behind) {
      var behind = textEl("span", pr.behind);
      behind.className = "pill behind-pill";
      behind.title = "The PR branch is " + pr.behind.split(" ")[0] + " commits behind its base branch, as of its last local push.";
      row.appendChild(behind);
    }
    row.appendChild(renderChecks(pr));
    row.appendChild(renderPrBlockControls(pr.repo + "#" + pr.number, pr.blocked_external, "card"));
    if (pr.card_url) {
      row.appendChild(link(pr.card_url, pr.card));
    } else if (pr.card) {
      row.appendChild(textEl("span", pr.card));
    }
    row.appendChild(textEl("span", pr.what));
    if (pr.dates) {
      row.appendChild(classedText("span", pr.dates, "muted"));
    }
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

  function renderTaskMoveControls(quest, task) {
    var controls = el("span");
    controls.className = "task-move-controls";
    var select = el("select");
    var placeholder = textEl("option", "move to...");
    placeholder.value = "";
    select.appendChild(placeholder);
    quest.move_targets.forEach(function (target) {
      var option = textEl("option", target.open ? target.slug + " (open)" : target.slug);
      option.value = target.slug;
      select.appendChild(option);
    });
    select.addEventListener("change", function () {
      if (select.value === "") {
        return;
      }
      postTaskMove(quest.slug, task.tid, select.value);
    });
    controls.appendChild(select);
    var status = textEl("span", state.taskMoveStatuses[quest.slug + "/" + task.tid] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function renderTaskDiscardControls(quest, task) {
    var controls = el("span");
    controls.className = "task-discard-controls";
    var force = el("input");
    force.type = "checkbox";
    var forceLabel = el("label");
    appendAll(forceLabel, [force, textEl("span", "force")]);
    controls.appendChild(forceLabel);
    controls.appendChild(
      ideaActionButton("Discard", false, function () {
        var reason = window.prompt("Why is " + task.tid + " discarded?");
        if (reason === null || reason.trim() === "") {
          return;
        }
        postTaskDiscard(quest.slug, task.tid, "discard", { reason: reason, force: force.checked });
      })
    );
    var status = textEl("span", state.taskDiscardStatuses[quest.slug + "/" + task.tid] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function renderDiscardedTask(quest, task) {
    var item = el("li");
    item.className = "task task-discarded";
    var head = el("div");
    head.className = "task-head";
    head.appendChild(textEl("span", task.tid));
    head.appendChild(textEl("span", task.title));
    item.appendChild(head);
    item.appendChild(classedText("p", "discarded by " + task.by + " on " + shortLocalDate(task.at) + ": " + task.reason, "muted"));
    item.appendChild(
      ideaActionButton("Restore", false, function () {
        postTaskDiscard(quest.slug, task.tid, "restore", {});
      })
    );
    item.appendChild(classedText("span", state.taskDiscardStatuses[quest.slug + "/" + task.tid] || "", "ask-status"));
    return item;
  }

  function renderDiscardedTasks(quest) {
    var details = el("details");
    details.className = "discarded-tasks";
    details.appendChild(textEl("summary", "Discarded (" + quest.discarded.length + ")"));
    var list = el("ul");
    list.className = "task-list";
    appendAll(
      list,
      quest.discarded.map(function (task) {
        return renderDiscardedTask(quest, task);
      })
    );
    details.appendChild(list);
    return details;
  }

  function renderTask(quest, task) {
    var item = el("li");
    item.className = "task task-" + task.state;
    var head = el("div");
    head.className = "task-head";
    head.appendChild(textEl("span", task.tid));
    head.appendChild(textEl("span", task.title));
    if (task.no_sdd) {
      head.appendChild(classedText("span", "no sdd", "muted"));
    }
    var taskState = textEl("span", task.state);
    taskState.className = "state state-" + task.state;
    head.appendChild(explain(taskState, "taskState", task.state));
    if (task.card_url) {
      head.appendChild(link(task.card_url, task.tid + " card"));
    }
    item.appendChild(head);
    if (task.dates) {
      item.appendChild(classedText("p", task.dates, "muted"));
    }
    var movable = task.state === "queued" || task.state === "blocked";
    if (movable && quest.move_targets.length > 0) {
      item.appendChild(renderTaskMoveControls(quest, task));
    }
    if (task.state !== "done") {
      item.appendChild(renderTaskDiscardControls(quest, task));
    }
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

  function renderCloseBlockerList(label, items) {
    if (items.length === 0) {
      return null;
    }
    var block = el("div");
    block.className = "party-drift";
    block.appendChild(textEl("h4", label));
    var list = el("ul");
    items.forEach(function (item) {
      list.appendChild(textEl("li", item));
    });
    block.appendChild(list);
    return block;
  }

  function renderCloseBlockers(blockers) {
    var wrapper = el("div");
    var badge = textEl("span", "can't close: drift");
    badge.className = "status-badge badge-warn";
    wrapper.appendChild(explain(badge, "ui", "closeBlocked"));
    var sections = [
      renderCloseBlockerList("yours", blockers.own),
      renderCloseBlockerList(
        "other parties",
        blockers.foreign.map(function (item) {
          return item.text + " (party " + item.party + ")";
        })
      ),
    ];
    sections.forEach(function (section) {
      if (section) {
        wrapper.appendChild(section);
      }
    });
    return wrapper;
  }

  function renderQuestRelease(quest) {
    var actions = el("div");
    actions.className = "notice-actions";
    actions.appendChild(
      ideaActionButton("Release", state.questBusy[quest.slug] === true, function () {
        postQuest("/api/quests/" + quest.slug + "/release", {}, quest.slug, function () {});
      })
    );
    actions.appendChild(classedText("span", state.questStatuses[quest.slug] || "", "ask-status"));
    return actions;
  }

  function renderQuest(quest) {
    var article = el("div");
    article.className = "quest";
    article.appendChild(textEl("h4", quest.slug + " — " + quest.title));
    if (quest.dates) {
      article.appendChild(classedText("p", quest.dates, "muted"));
    }
    if (quest.close_blockers) {
      article.appendChild(renderCloseBlockers(quest.close_blockers));
    }
    var list = el("ul");
    list.className = "task-list";
    appendAll(
      list,
      quest.tasks.map(function (task) {
        return renderTask(quest, task);
      })
    );
    article.appendChild(list);
    if (quest.discarded.length > 0) {
      article.appendChild(renderDiscardedTasks(quest));
    }
    if (quest.releasable) {
      article.appendChild(renderQuestRelease(quest));
    }
    return article;
  }

  function renderRoleBadge(raids) {
    var badge = el("span");
    var modifier = raids.length === 0 ? "role-solo" : "role-member";
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
              return raid.raid;
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

  function renderPartyHandoffControls(party) {
    var controls = el("span");
    controls.className = "pr-block-controls";
    var button = textEl("button", "Hand off");
    button.type = "button";
    button.disabled = state.partyHandoffBusy[party.name] === true;
    button.addEventListener("click", function () {
      postPartyHandoffAction(party.name);
    });
    controls.appendChild(button);
    var status = textEl("span", state.partyHandoffStatuses[party.name] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function partyParkButton(party, label, handler) {
    var button = textEl("button", label);
    button.type = "button";
    button.disabled = state.partyParkBusy[party.name] === true;
    button.addEventListener("click", handler);
    return button;
  }

  function renderPartyParkInput(party) {
    var input = el("input");
    input.type = "text";
    input.className = "block-reason";
    input.placeholder = "what it waits on";
    input.value = state.partyParkDrafts[party.name] || "";
    input.disabled = state.partyParkBusy[party.name] === true;
    input.dataset.focusKey = "park|" + party.name;
    input.addEventListener("input", function () {
      state.partyParkDrafts[party.name] = input.value;
    });
    return input;
  }

  function renderPartyParkControls(party) {
    var controls = el("span");
    controls.className = "pr-block-controls";
    if (party.parked !== null) {
      controls.appendChild(
        partyParkButton(party, "Unpark", function () {
          postPartyParkAction(party.name, "unpark", {});
        })
      );
    } else if (state.partyParkOpen[party.name]) {
      controls.appendChild(renderPartyParkInput(party));
      controls.appendChild(
        partyParkButton(party, "Confirm park", function () {
          submitPartyPark(party.name);
        })
      );
    } else {
      controls.appendChild(
        partyParkButton(party, "Park", function () {
          state.partyParkOpen[party.name] = true;
          fetchBoard();
        })
      );
    }
    var status = textEl("span", state.partyParkStatuses[party.name] || "");
    status.className = "ask-status";
    controls.appendChild(status);
    return controls;
  }

  function renderPartyWaits(waits) {
    if (waits.length === 0) {
      return null;
    }
    var line = el("p");
    line.className = "party-waits";
    line.appendChild(textEl("span", "waits on: "));
    waits.forEach(function (wait) {
      var pill = textEl("span", wait.label);
      pill.className = "pill lifecycle-converging";
      pill.dataset.waitKind = wait.kind;
      line.appendChild(explain(pill, "partyWait", wait.kind));
    });
    return line;
  }

  function partyOrigin(party) {
    var parts = [];
    if (party.dates !== null) {
      parts.push(party.dates);
    }
    if (party.from_adventurer !== null) {
      parts.push("from adventurer " + party.from_adventurer);
    }
    if (party.reason !== null) {
      parts.push("reason: " + party.reason);
    }
    if (parts.length === 0) {
      return null;
    }
    return parts.join(" · ");
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
    if (party.stopped_without_report) {
      summary.appendChild(classedText("span", STOPPED_WITHOUT_REPORT_TEXT, "pill stopped-without-report"));
    }
    if (party.ctx !== null) {
      var ctxSource = party.ctx.source === "configured" ? "" : " (" + party.ctx.source + ")";
      var ctxBadge = textEl("span", "context " + party.ctx.pct + "% / " + party.ctx.threshold + "%" + ctxSource);
      ctxBadge.className = party.ctx.high ? "status-badge badge-warn" : "status-badge";
      summary.appendChild(explain(ctxBadge, "ui", party.ctx.high ? "ctxHigh" : "ctx"));
    }
    summary.appendChild(explain(textEl("span", party.state), "partyState", party.state));
    summary.appendChild(explain(textEl("span", "gen " + party.generation), "ui", "generation"));
    var leaderKey = party.leader_session_name ? "leader" : "noLeader";
    summary.appendChild(explain(textEl("span", party.leader_session_name || "no leader"), "ui", leaderKey));
    details.appendChild(summary);

    var statusDetail = renderStatusDetail(party.status);
    if (statusDetail !== null) {
      details.appendChild(statusDetail);
    }

    var origin = partyOrigin(party);
    if (origin !== null) {
      details.appendChild(explain(textEl("p", origin), "ui", "bindingReason"));
    }

    var partyWaits = renderPartyWaits(party.waits);
    if (partyWaits) {
      details.appendChild(partyWaits);
    }

    if (party.resume_command !== null) {
      var resumeLine = el("p");
      resumeLine.className = "resume-command";
      resumeLine.appendChild(textEl("span", "resume: "));
      resumeLine.appendChild(textEl("code", party.resume_command));
      details.appendChild(explain(resumeLine, "ui", "resumeCommand"));
    }

    if (party.state === "active" && !party.has_live_leader) {
      details.appendChild(renderPartyHandoffControls(party));
    }
    if (party.state !== "closed") {
      details.appendChild(renderPartyParkControls(party));
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

    if (party.ideas.length > 0) {
      details.appendChild(textEl("p", "ideas: " + party.ideas.map(ideaSummary).join(", ")));
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
          return claim.dates ? claim.area + " (" + claim.dates + ")" : claim.area;
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

  function applyPartyFilter(data) {
    if (state.partyFilter === "all") {
      return data;
    }
    return {
      generated_at: data.generated_at,
      ideas: data.ideas,
      adventurers: data.adventurers,
      health_jobs: data.health_jobs,
      solo_players: data.solo_players,
      solo_channel: data.solo_channel,
      solo_pending: [],
      asks: data.asks.filter(function (ask) {
        return ask.party === state.partyFilter;
      }),
      notices: data.notices.filter(function (notice) {
        return notice.party === state.partyFilter;
      }),
      memory: data.memory.filter(function (item) {
        return item.party === state.partyFilter;
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
      ready_for_you: data.ready_for_you.filter(function (item) {
        return item.party === state.partyFilter;
      }),
    };
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
      ideas: data.ideas,
      adventurers: data.adventurers,
      health_jobs: data.health_jobs,
      solo_players: data.solo_players,
      solo_channel: data.solo_channel,
      solo_pending: [],
      asks: data.asks.filter(function (ask) {
        return members.indexOf(ask.party) !== -1;
      }),
      notices: data.notices.filter(function (notice) {
        return notice.scope === scope;
      }),
      memory: data.memory.filter(function (item) {
        return members.indexOf(item.party) !== -1;
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
      ready_for_you: data.ready_for_you.filter(function (item) {
        return item.scopes.indexOf(scope) !== -1;
      }),
    };
  }

  function rememberFocus() {
    var active = document.activeElement;
    state.focusedAskId = null;
    state.focusedKey = null;
    if (active && active.dataset && active.dataset.focusKey) {
      state.focusedKey = active.dataset.focusKey;
      state.focusStart = active.selectionStart;
      state.focusEnd = active.selectionEnd;
    }
    if (active && active.dataset && active.dataset.askId) {
      state.focusedAskId = active.dataset.askId;
      state.focusStart = active.selectionStart;
      state.focusEnd = active.selectionEnd;
    }
  }

  function restoreKeyedFocus() {
    var inputs = document.querySelectorAll("[data-focus-key]");
    Array.prototype.forEach.call(inputs, function (input) {
      if (input.dataset.focusKey === state.focusedKey && !input.disabled) {
        input.focus();
        input.setSelectionRange(state.focusStart, state.focusEnd);
      }
    });
  }

  function restoreFocus() {
    if (state.focusedKey !== null) {
      restoreKeyedFocus();
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

  var DISK_WARN_PERCENT = 70;
  var DISK_BAD_PERCENT = 85;
  var RAM_BAD_RATIO = 0.1;
  var RAM_WARN_RATIO = 0.25;
  var CPU_BAD_PER_CORE = 1.5;
  var CPU_WARN_PER_CORE = 0.8;

  function pill(text, tone) {
    return classedText("span", text, "pill res-" + tone);
  }

  function deltaPill(text, value) {
    if (value === null) {
      return pill(text, "dim");
    }
    return pill(text, value > 0 ? "warn" : "ok");
  }

  function diskTone(percent) {
    if (percent >= DISK_BAD_PERCENT) {
      return "bad";
    }
    return percent >= DISK_WARN_PERCENT ? "warn" : "ok";
  }

  function ramTone(machine) {
    if (machine.mem_available < machine.mem_total * RAM_BAD_RATIO) {
      return "bad";
    }
    return machine.mem_available < machine.mem_total * RAM_WARN_RATIO ? "warn" : "ok";
  }

  function cpuTone(loadPerCore) {
    if (loadPerCore >= CPU_BAD_PER_CORE) {
      return "bad";
    }
    return loadPerCore >= CPU_WARN_PER_CORE ? "warn" : "ok";
  }

  function diskText(machine) {
    return "disk " + machine.disk_percent + "% used (" + formatBytes(machine.disk_used) + " of " + formatBytes(machine.disk_total) + ")";
  }

  function resourceDeltaPill(entry, hasBaseline) {
    if (!hasBaseline) {
      return null;
    }
    if (entry.new) {
      return pill("new", "warn");
    }
    return deltaPill(signedBytes(entry.delta_bytes), entry.delta_bytes);
  }

  function renderResourceItem(entry, hasBaseline) {
    var row = el("li");
    row.appendChild(textEl("code", entry.item));
    row.appendChild(textEl("span", " " + formatBytes(entry.bytes) + " "));
    var delta = resourceDeltaPill(entry, hasBaseline);
    if (delta) {
      row.appendChild(delta);
    }
    if (entry.state !== "ok") {
      row.appendChild(pill(entry.state, "dim"));
    }
    if (entry.flag) {
      row.appendChild(explain(pill(RESOURCE_FLAG_LABELS[entry.flag] || entry.flag, "warn"), "resourceFlag", entry.flag));
    }
    return row;
  }

  function renderResourceCategoryHeading(category, hasBaseline) {
    var heading = el("h4");
    if (category.category === "docker") {
      heading.appendChild(textEl("span", "docker "));
      heading.appendChild(pill(category.state, "dim"));
      heading.appendChild(textEl("span", " (" + category.detail + ")"));
      return heading;
    }
    heading.appendChild(textEl("span", category.category + " " + formatBytes(category.bytes) + " "));
    if (hasBaseline && category.delta_bytes !== null) {
      heading.appendChild(deltaPill(signedBytes(category.delta_bytes), category.delta_bytes));
    }
    if (category.state !== "ok") {
      heading.appendChild(pill(category.state, "dim"));
    }
    return heading;
  }

  function renderResourceCategory(project, category, hasBaseline) {
    var wrapper = el("div");
    wrapper.appendChild(explain(renderResourceCategoryHeading(category, hasBaseline), "resourceCategory", category.category));
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

  function renderResourceHeadline(label, project) {
    var hasBaseline = project.baseline_at !== null;
    var summary = el("summary");
    summary.appendChild(textEl("span", label + " total " + formatBytes(project.total_bytes) + " "));
    if (hasBaseline && project.delta_bytes !== null) {
      summary.appendChild(deltaPill(signedBytes(project.delta_bytes), project.delta_bytes));
    }
    if (!hasBaseline) {
      summary.appendChild(textEl("span", "no earlier sample"));
    }
    return summary;
  }

  function renderResourceProject(label, project) {
    var details = el("details");
    details.className = "party";
    details.open = state.openResourceProjects[label] === true;
    details.addEventListener("toggle", function () {
      state.openResourceProjects[label] = details.open;
    });
    details.appendChild(renderResourceHeadline(label, project));
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

  function diskPill(machine) {
    if (machine.disk_percent === null) {
      return pill("disk n/a", "dim");
    }
    return pill(diskText(machine), diskTone(machine.disk_percent));
  }

  function ramPill(machine) {
    if (machine.mem_available === null) {
      return pill("ram n/a", "dim");
    }
    return pill("ram " + formatBytes(machine.mem_available) + " available of " + formatBytes(machine.mem_total), ramTone(machine));
  }

  function cpuPill(machine) {
    if (machine.load_per_core === null) {
      return pill("cpu n/a", "dim");
    }
    var text = "cpu " + machine.load_per_core.toFixed(1) + "/core (load " + machine.load1.toFixed(1) + " on " + machine.cpu_count + " cores, 15m " + machine.load15.toFixed(1) + ")";
    return pill(text, cpuTone(machine.load_per_core));
  }

  function dockerPill(machine) {
    if (machine.docker === null) {
      return pill("docker n/a", "dim");
    }
    var text = "docker " + formatBytes(machine.docker.total) + " (reclaimable " + formatBytes(machine.docker.images_reclaimable) + ")";
    return pill(text, machine.docker.images_reclaimable > 0 ? "warn" : "ok");
  }

  function resourceMachinePills(machine, since) {
    var pills = [diskPill(machine)];
    if (machine.disk_delta !== null) {
      pills.push(deltaPill(signedBytes(machine.disk_delta) + " in " + since, machine.disk_delta));
    }
    pills.push(ramPill(machine));
    pills.push(cpuPill(machine));
    pills.push(dockerPill(machine));
    pills.push(pill("guild.db " + formatBytes(machine.guild_db_bytes), "dim"));
    if (machine.untracked_growth !== null) {
      pills.push(deltaPill("untracked growth: " + signedBytes(machine.untracked_growth), machine.untracked_growth));
    }
    return pills;
  }

  function renderSidebarResources(model) {
    var target = document.getElementById("sidebar-resources");
    clear(target);
    if (model.machine === null || model.machine.disk_percent === null) {
      return;
    }
    target.appendChild(pill("disk " + model.machine.disk_percent + "%", diskTone(model.machine.disk_percent)));
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

  function renderCompactControls() {
    var controls = el("p");
    var button = textEl("button", "Compact db");
    button.type = "button";
    button.disabled = state.compactBusy;
    button.addEventListener("click", postCompact);
    controls.appendChild(button);
    controls.appendChild(classedText("span", state.compactStatus, "ask-status"));
    var collect = textEl("button", "Collect now");
    collect.type = "button";
    collect.disabled = state.collectBusy;
    collect.addEventListener("click", postCollect);
    controls.appendChild(collect);
    controls.appendChild(classedText("span", state.collectStatus, "ask-status"));
    return controls;
  }

  function showResources() {
    if (state.resourcesModel !== null) {
      renderResources(state.resourcesModel);
    }
  }

  function renderResources(model) {
    state.resourcesModel = model;
    var section = document.getElementById("resources");
    clear(section);
    renderSidebarResources(model);
    section.appendChild(textEl("h2", "resources"));
    if (model.machine === null) {
      section.appendChild(textEl("p", NO_RESOURCES_MESSAGE));
      return;
    }
    var pills = classedText("div", "", "res-pills");
    resourceMachinePills(model.machine, model.since).forEach(function (machinePill) {
      pills.appendChild(machinePill);
    });
    section.appendChild(pills);
    section.appendChild(classedText("p", "sampled at " + model.machine.sampled_at, "muted"));
    section.appendChild(renderCompactControls());
    section.appendChild(renderResourceProjects(model));
  }

  function fetchResources() {
    apiGet(RESOURCES_URL)
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

  function ageSince(iso) {
    var seconds = Math.max(0, Math.floor((Date.now() - Date.parse(iso)) / 1000));
    if (isNaN(seconds)) {
      return iso;
    }
    if (seconds < 60) {
      return seconds + "s";
    }
    if (seconds < 3600) {
      return Math.floor(seconds / 60) + "m";
    }
    if (seconds < 86400) {
      return Math.floor(seconds / 3600) + "h";
    }
    return Math.floor(seconds / 86400) + "d";
  }

  function realmProjectLine(project) {
    var line = el("p");
    line.appendChild(
      textEl(
        "span",
        project.name + ": parties " + project.parties + ", quests " + project.open_quests +
          ", PRs " + project.open_prs + " (" + project.ready_prs + " ready), asks " + project.open_asks + " "
      )
    );
    if (project.main_red) {
      line.appendChild(pill("main red", "bad"));
    }
    return line;
  }

  function renderRealmGuild(entry) {
    var article = el("article");
    article.className = "card realm-guild";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("strong", entry.guild));
    head.appendChild(classedText("span", "last seen " + ageSince(entry.received_at) + " ago", "muted"));
    article.appendChild(head);
    appendAll(article, entry.projects.map(realmProjectLine));
    return article;
  }

  function realmInboxActionUrl(fileId, action) {
    return "/api/realm/inbox/" + fileId + "/" + action;
  }

  function postRealmInboxRefresh() {
    if (sessionToken === null) {
      state.realmStatus = NO_SESSION_MESSAGE;
      showRealm();
      return;
    }
    state.realmBusy = true;
    state.realmStatus = "refreshing inbox...";
    showRealm();
    sendPost(REALM_INBOX_REFRESH_URL, {}).then(function (result) {
      state.realmBusy = false;
      state.realmStatus = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        state.realmModel.inbox = result.body.files;
      }
      showRealm();
    });
  }

  function postRealmRefresh() {
    if (sessionToken === null) {
      state.realmStatus = NO_SESSION_MESSAGE;
      showRealm();
      return;
    }
    state.realmBusy = true;
    state.realmStatus = "refreshing...";
    showRealm();
    sendPost(REALM_REFRESH_URL, {}).then(function (result) {
      state.realmBusy = false;
      state.realmStatus = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        state.realmModel = Object.assign({}, result.body, { inbox: state.realmModel.inbox });
      }
      showRealm();
      if (result.ok) {
        postRealmInboxRefresh();
      }
    });
  }

  function postRealmDoctor() {
    if (sessionToken === null) {
      state.realmStatus = NO_SESSION_MESSAGE;
      showRealm();
      return;
    }
    state.realmBusy = true;
    state.realmStatus = "checking...";
    showRealm();
    sendPost(REALM_DOCTOR_URL, {}).then(function (result) {
      state.realmBusy = false;
      state.realmStatus = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        state.realmDoctorLines = result.body.lines;
      }
      showRealm();
    });
  }

  function renderRealmDoctorLine(entry) {
    var line = el("p");
    if (!entry.passed) {
      line.appendChild(pill(entry.text, "bad"));
      return line;
    }
    line.appendChild(classedText("span", entry.text, entry.text.indexOf("warn") === 0 ? "muted" : ""));
    return line;
  }

  function postRealmInboxFetch(fileId) {
    if (sessionToken === null) {
      state.realmStatus = NO_SESSION_MESSAGE;
      showRealm();
      return;
    }
    state.realmBusy = true;
    state.realmStatus = "fetching...";
    state.realmFetchNote = "";
    showRealm();
    sendPost(realmInboxActionUrl(fileId, "fetch"), {}).then(function (result) {
      state.realmBusy = false;
      state.realmStatus = result.ok ? "" : errorMessage(result.body);
      if (result.ok) {
        state.realmFetchNote =
          "saved " + result.body.path + " from " + result.body.from + (result.body.flagged ? " " + REALM_FLAG_TEXT : "");
      }
      showRealm();
    });
  }

  function postRealmInboxDrop(fileId) {
    if (!window.confirm("Drop realm file " + fileId + " from the hub?")) {
      return;
    }
    if (sessionToken === null) {
      state.realmStatus = NO_SESSION_MESSAGE;
      showRealm();
      return;
    }
    state.realmBusy = true;
    state.realmStatus = "dropping...";
    showRealm();
    sendPost(realmInboxActionUrl(fileId, "drop"), {}).then(function (result) {
      state.realmBusy = false;
      state.realmStatus = result.ok ? "" : errorMessage(result.body);
      showRealm();
      if (result.ok) {
        postRealmInboxRefresh();
      }
    });
  }

  function realmInboxButton(label, handler, fileId) {
    var button = textEl("button", label);
    button.type = "button";
    button.disabled = state.realmBusy;
    button.addEventListener("click", function () {
      handler(fileId);
    });
    return button;
  }

  function renderRealmInboxRow(entry) {
    var row = el("p");
    row.appendChild(
      textEl("span", entry.from + " " + entry.name + " " + entry.size + " bytes " + ageSince(entry.sent_at) + " ago ")
    );
    row.appendChild(realmInboxButton("Fetch", postRealmInboxFetch, entry.id));
    row.appendChild(realmInboxButton("Drop", postRealmInboxDrop, entry.id));
    return row;
  }

  function renderRealmInbox(realm) {
    var box = el("div");
    box.className = "realm-inbox";
    box.appendChild(textEl("h3", "Inbox"));
    var controls = el("p");
    var refresh = textEl("button", "Refresh inbox");
    refresh.type = "button";
    refresh.disabled = state.realmBusy;
    refresh.addEventListener("click", postRealmInboxRefresh);
    controls.appendChild(refresh);
    box.appendChild(controls);
    if (realm.inbox.length === 0) {
      box.appendChild(textEl("p", "inbox empty"));
    }
    appendAll(box, realm.inbox.map(renderRealmInboxRow));
    if (state.realmFetchNote !== "") {
      box.appendChild(classedText("p", state.realmFetchNote, "muted"));
    }
    return box;
  }

  function renderRealmControls(realm) {
    var controls = el("p");
    var fetched = realm.fetched_at === null ? "never fetched" : "fetched " + ageSince(realm.fetched_at) + " ago";
    controls.appendChild(classedText("span", fetched + " ", "muted"));
    var button = textEl("button", "Refresh");
    button.type = "button";
    button.disabled = state.realmBusy;
    button.addEventListener("click", postRealmRefresh);
    controls.appendChild(button);
    var check = textEl("button", "Check");
    check.type = "button";
    check.disabled = state.realmBusy;
    check.addEventListener("click", postRealmDoctor);
    controls.appendChild(check);
    controls.appendChild(classedText("span", state.realmStatus, "ask-status"));
    return controls;
  }

  function showRealm() {
    renderRealm(state.realmModel);
  }

  function renderRealm(realm) {
    state.realmModel = realm;
    var section = document.getElementById("realm");
    clear(section);
    if (realm === null) {
      return;
    }
    section.appendChild(textEl("h2", realm.realm ? "realm " + realm.realm : "realm"));
    section.appendChild(renderRealmControls(realm));
    appendAll(section, state.realmDoctorLines.map(renderRealmDoctorLine));
    if (realm.guilds.length === 0) {
      section.appendChild(textEl("p", "no guilds reported yet"));
    }
    appendAll(section, realm.guilds.map(renderRealmGuild));
    section.appendChild(renderRealmInbox(realm));
  }

  function renderSection(id, args, renderFn, onlyIfChanged) {
    var key = JSON.stringify(args);
    if (onlyIfChanged && state.sectionKeys[id] === key) {
      return;
    }
    state.sectionKeys[id] = key;
    renderFn.apply(null, args);
  }

  function activeAdventurerIds(adventurers) {
    return adventurers
      .filter(function (adventurer) {
        return adventurer.state === "active";
      })
      .map(function (adventurer) {
        return adventurer.id;
      });
  }

  function activePartyNames(parties) {
    return parties
      .filter(function (party) {
        return party.state === "active";
      })
      .map(function (party) {
        return party.name;
      });
  }

  var VIEW_SECTIONS = {
    "needs-you": ["asks", "ready-for-you", "answered-asks"],
    party: ["asks", "merge-queues", "progress", "daily-tasks", "parties", "memory"],
    raid: ["asks", "merge-queues", "progress", "daily-tasks", "parties", "memory"],
    adventurers: ["adventurers", "health-jobs"],
    "solo-players": ["solo-players"],
    ideas: ["ideas"],
    quests: ["quest-board"],
    overview: ["notices", "raids", "drift", "projects", "realm"],
  };
  var ALL_SECTION_IDS = [
    "asks", "ready-for-you", "answered-asks", "notices", "ideas", "adventurers", "health-jobs", "solo-players",
    "memory", "raids", "drift", "projects", "quest-board", "merge-queues", "progress", "daily-tasks", "parties", "realm",
  ];
  var DEFAULT_VIEW = { kind: "needs-you", name: "", hash: "needs-you" };

  function currentView() {
    var hash = window.location.hash.replace(/^#/, "");
    var slash = hash.indexOf("/");
    var kind = slash === -1 ? hash : hash.slice(0, slash);
    var name = slash === -1 ? "" : hash.slice(slash + 1);
    if (!VIEW_SECTIONS.hasOwnProperty(kind)) {
      return DEFAULT_VIEW;
    }
    var named = kind === "party" || kind === "raid";
    if (kind !== "solo-players" && named !== (name !== "")) {
      return DEFAULT_VIEW;
    }
    return { kind: kind, name: name, hash: hash };
  }

  function applyView(view) {
    var shown = VIEW_SECTIONS[view.kind];
    ALL_SECTION_IDS.forEach(function (id) {
      document.getElementById(id).hidden = shown.indexOf(id) === -1;
    });
  }

  function partyViewQueues(data, partyName) {
    var party = data.parties.filter(function (candidate) {
      return candidate.name === partyName;
    });
    if (party.length === 0) {
      return [];
    }
    var scopes = party[0].raids.length > 0
      ? party[0].raids.map(function (membership) {
          return "raid:" + membership.raid;
        })
      : ["party:" + partyName];
    return data.merge_queues.filter(function (queue) {
      return scopes.indexOf(queue.scope) !== -1;
    });
  }

  var ATTENTION_ORDER = ["waiting-permission", "waiting-ask", "ctx-high", "waiting-input", "stopped-with-work", "working", "waiting-sub-agents", "waiting-background", "queued", "parked", "blocked"];

  function attentionRank(row) {
    var key = row.ctxHigh && row.status.name !== "waiting-permission" && row.status.name !== "waiting-ask" ? "ctx-high" : row.status.name;
    var index = ATTENTION_ORDER.indexOf(key);
    return index === -1 ? ATTENTION_ORDER.length : index;
  }

  function byAttention(left, right) {
    var diff = attentionRank(left) - attentionRank(right);
    if (diff !== 0) {
      return diff;
    }
    return left.name < right.name ? -1 : left.name > right.name ? 1 : 0;
  }

  function sidebarRow(party, asks) {
    return {
      name: party.name,
      status: party.status,
      remaining: party.remaining,
      asks: asks.filter(function (ask) {
        return ask.party === party.name;
      }).length,
      ctxHigh: Boolean(party.ctx && party.ctx.high),
      stoppedWithoutReport: Boolean(party.stopped_without_report),
    };
  }

  function sidebarModel(data) {
    var rows = {};
    data.parties.forEach(function (party) {
      rows[party.name] = sidebarRow(party, data.asks);
    });
    return {
      asks: data.asks.length,
      ready: data.ready_for_you.length,
      blocked: data.blocked.length,
      ctxHigh: ctxHighCount(data.parties),
      raids: data.raids.map(function (raid) {
        return {
          name: raid.name,
          paused: raid.paused,
          members: raid.members
            .filter(function (name) {
              return Object.prototype.hasOwnProperty.call(rows, name);
            })
            .map(function (name) {
              return rows[name];
            })
            .sort(byAttention),
        };
      }),
      parties: data.parties
        .filter(function (party) {
          return party.raids.length === 0;
        })
        .map(function (party) {
          return rows[party.name];
        })
        .sort(byAttention),
      adventurers: data.adventurers.filter(function (adventurer) {
        return adventurer.state === "active";
      }).length,
      soloPlayers: data.solo_players.length,
      soloProjects: soloProjectNames(data.solo_players).map(function (name) {
        return {
          name: name,
          count: data.solo_players.filter(function (player) {
            return player.project === name;
          }).length,
        };
      }),
      ideas: data.ideas.length,
      openQuests: data.quest_boards.reduce(function (total, project) {
        return total + project.open_quests.length;
      }, 0),
      newNotices: data.new_notice_count,
    };
  }

  function sidebarLink(hash, label, currentHash) {
    var anchor = textEl("a", label);
    anchor.href = "#" + hash;
    if (hash === currentHash) {
      anchor.ariaCurrent = "page";
    }
    return anchor;
  }

  function sidebarItem(child) {
    var item = el("li");
    item.appendChild(child);
    return item;
  }

  function sidebarPartyItem(row, currentHash) {
    var item = sidebarItem(sidebarLink("party/" + row.name, row.name, currentHash));
    var badges = el("div");
    badges.className = "sidebar-badges";
    badges.appendChild(renderStatusBadge(row.status));
    if (row.asks > 0) {
      badges.appendChild(classedText("span", row.asks + " asks", "pill ask-count"));
    }
    badges.appendChild(renderRemainingBadge(row.remaining));
    if (row.stoppedWithoutReport) {
      badges.appendChild(classedText("span", STOPPED_WITHOUT_REPORT_TEXT, "pill stopped-without-report"));
    }
    item.appendChild(badges);
    var statusDetail = renderStatusDetail(row.status);
    if (statusDetail !== null) {
      item.appendChild(statusDetail);
    }
    return item;
  }

  function sidebarPartyList(rows, currentHash) {
    var list = el("ul");
    appendAll(
      list,
      rows.map(function (row) {
        return sidebarPartyItem(row, currentHash);
      })
    );
    return list;
  }

  function sidebarRaidGroup(raid, currentHash) {
    var group = el("li");
    group.className = "sidebar-group";
    var head = el("h3");
    head.appendChild(sidebarLink("raid/" + raid.name, "raid " + raid.name, currentHash));
    if (raid.paused) {
      head.appendChild(classedText("span", " paused", "muted"));
    }
    if (raid.members.length > 0) {
      head.appendChild(renderStatusBadge(raid.members[0].status));
    }
    group.appendChild(head);
    group.appendChild(sidebarPartyList(raid.members, currentHash));
    return group;
  }

  function needsCount(count, label, type) {
    var text = count + " " + label;
    return count > 0 ? classedText("span", text, "pill needs-" + type) : classedText("span", text, "muted");
  }

  function sidebarNeedsCounts(model) {
    var counts = el("div");
    counts.className = "sidebar-badges";
    appendAll(counts, [
      needsCount(model.asks, "asks", "asks"),
      needsCount(model.ready, "ready", "ready"),
      needsCount(model.blocked, "blocked", "blocked"),
      needsCount(model.ctxHigh, "context high", "ctx-high"),
    ]);
    return counts;
  }

  function sidebarSoloMenu(model, currentHash) {
    var details = el("details");
    details.open = state.soloMenuOpen;
    details.addEventListener("toggle", function () {
      state.soloMenuOpen = details.open;
    });
    var summary = el("summary");
    summary.appendChild(sidebarLink("solo-players", "solo players (" + model.soloPlayers + ")", currentHash));
    details.appendChild(summary);
    var list = el("ul");
    appendAll(
      list,
      model.soloProjects.map(function (project) {
        return sidebarItem(
          sidebarLink("solo-players/" + project.name, project.name + " (" + project.count + ")", currentHash)
        );
      })
    );
    details.appendChild(list);
    return sidebarItem(details);
  }

  function renderSidebar(model, currentHash) {
    var nav = document.getElementById("sidebar");
    clear(nav);
    var top = el("ul");
    var needs = sidebarItem(sidebarLink("needs-you", "needs you", currentHash));
    needs.appendChild(sidebarNeedsCounts(model));
    top.appendChild(needs);
    top.appendChild(sidebarItem(sidebarLink("adventurers", "adventurers (" + model.adventurers + ")", currentHash)));
    top.appendChild(sidebarSoloMenu(model, currentHash));
    top.appendChild(sidebarItem(sidebarLink("ideas", "ideas (" + model.ideas + ")", currentHash)));
    top.appendChild(sidebarItem(sidebarLink("quests", "quest board (" + model.openQuests + ")", currentHash)));
    top.appendChild(sidebarItem(sidebarLink("overview", "overview (" + model.newNotices + " new)", currentHash)));
    appendAll(
      top,
      model.raids.map(function (raid) {
        return sidebarRaidGroup(raid, currentHash);
      })
    );
    if (model.parties.length > 0) {
      var parties = el("li");
      parties.className = "sidebar-group";
      parties.appendChild(textEl("h3", "parties"));
      parties.appendChild(sidebarPartyList(model.parties, currentHash));
      top.appendChild(parties);
    }
    nav.appendChild(top);
  }

  function renderBases(bases) {
    var section = document.getElementById("bases");
    clear(section);
    if (bases.length === 0) {
      return;
    }
    section.appendChild(textEl("h2", "bases"));
    bases.forEach(function (entry) {
      var line = el("p");
      var pillClass = entry.paused ? "pill lifecycle-blocked-external" : "pill res-" + (entry.warn ? "warn" : "ok");
      line.appendChild(classedText("span", entry.text, pillClass));
      var action = entry.paused ? "resume" : "pause";
      var button = textEl("button", action);
      button.type = "button";
      button.addEventListener("click", function () {
        postBaseAction(entry.repo, action);
      });
      line.appendChild(button);
      if (state.baseStatuses[entry.repo]) {
        line.appendChild(classedText("span", state.baseStatuses[entry.repo], "ask-status"));
      }
      section.appendChild(line);
    });
  }

  function render(data, onlyIfChanged) {
    rememberFocus();
    document.getElementById("generated-at").textContent = "generated at " + data.generated_at;
    document.getElementById("board-title").textContent = data.guild_name ? "guild board · " + data.guild_name : "guild board";
    var view = currentView();
    applyView(view);
    if (view.hash !== state.renderedHash && view.kind === "solo-players" && view.name !== "") {
      state.soloMenuOpen = true;
    }
    state.renderedHash = view.hash;
    state.partyFilter = view.kind === "party" ? view.name : "all";
    state.raidFilter = view.kind === "raid" ? view.name : "all";
    var filtered = applyRaidFilter(applyPartyFilter(data));
    if (view.kind === "party") {
      filtered.merge_queues = partyViewQueues(data, view.name);
    }
    renderSection("bases", [data.bases], renderBases, onlyIfChanged);
    renderSection("sidebar", [sidebarModel(data), view.hash], renderSidebar, onlyIfChanged);
    renderSection(
      "asks",
      [filtered.asks, filtered.blocked, filtered.parties, filtered.solo_pending],
      renderAsks,
      onlyIfChanged
    );
    renderSection("ready", [filtered.ready_for_you], renderReadyForYou, onlyIfChanged);
    renderSection("notices", [filtered.notices, filtered.projects, filtered.raids], renderNotices, onlyIfChanged);
    renderSection(
      "ideas",
      [filtered.ideas, data.project_names, activePartyNames(data.parties), activeAdventurerIds(data.adventurers)],
      renderIdeas,
      onlyIfChanged
    );
    renderSection("adventurers", [filtered.adventurers], renderAdventurers, onlyIfChanged);
    renderSection("health-jobs", [filtered.health_jobs], renderHealthJobs, onlyIfChanged);
    renderSection(
      "solo-players",
      [filtered.solo_players, filtered.solo_channel, view.kind === "solo-players" ? view.name : ""],
      renderSoloPlayers,
      onlyIfChanged
    );
    renderSection("memory", [filtered.memory], renderMemory, onlyIfChanged);
    renderSection("raids", [filtered.raids], renderRaids, onlyIfChanged);
    renderSection("merge-queues", [filtered.merge_queues], renderMergeQueues, onlyIfChanged);
    renderSection("progress", [filtered.parties], renderProgress, onlyIfChanged);
    renderSection("daily-tasks", [filtered.parties], renderDailyTasks, onlyIfChanged);
    renderSection("drift", [filtered.drift], renderDrift, onlyIfChanged);
    renderSection("projects", [filtered.projects], renderProjects, onlyIfChanged);
    renderSection("quest-board", [data.quest_boards], renderQuestBoard, onlyIfChanged);
    renderSection("parties", [filtered.parties], renderParties, onlyIfChanged);
    renderSection("realm", [data.realm], renderRealm, onlyIfChanged);
    restoreFocus();
  }

  function loadBoard(onlyIfChanged) {
    apiGet(BOARD_URL)
      .then(function (response) {
        return response.json();
      })
      .then(function (data) {
        render(data, onlyIfChanged);
      })
      .catch(function (error) {
        console.error(error);
      });
  }

  function fetchBoard() {
    loadBoard(false);
  }

  function pollBoard() {
    loadBoard(true);
  }

  document.addEventListener("DOMContentLoaded", function () {
    window.addEventListener("hashchange", fetchBoard);
    document.getElementById("state-filter").addEventListener("change", function (event) {
      state.stateFilter = event.target.value;
      fetchBoard();
    });
    renderAnsweredAsks();
    fetchBoard();
    fetchResources();
    setInterval(pollBoard, REFRESH_INTERVAL_MS);
    setInterval(fetchResources, REFRESH_INTERVAL_MS);
  });
})();
