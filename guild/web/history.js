(function () {
  "use strict";

  var HISTORY_URL = "/api/history";
  var UNKNOWN = "—";

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

  function formatDuration(seconds) {
    if (seconds === null || seconds === undefined) {
      return UNKNOWN;
    }
    var minutes = Math.floor(seconds / 60);
    var hours = Math.floor(minutes / 60);
    var days = Math.floor(hours / 24);
    if (days > 0) {
      return days + "d " + (hours % 24) + "h";
    }
    if (hours > 0) {
      return hours + "h " + (minutes % 60) + "m";
    }
    if (minutes > 0) {
      return minutes + "m";
    }
    return "<1m";
  }

  function formatDate(iso) {
    if (!iso) {
      return UNKNOWN;
    }
    return iso.slice(0, 16).replace("T", " ");
  }

  function orUnknown(value) {
    if (value === null || value === undefined) {
      return UNKNOWN;
    }
    return String(value);
  }

  function listOrUnknown(values) {
    if (values === null || values === undefined) {
      return UNKNOWN;
    }
    if (values.length === 0) {
      return "none";
    }
    return values.join(", ");
  }

  function stat(label, value) {
    var node = el("div");
    node.className = "stat";
    appendAll(node, [classedText("span", value, "stat-value"), classedText("span", label, "stat-label")]);
    return node;
  }

  function renderTotals(totals) {
    var node = document.getElementById("totals");
    clear(node);
    var strip = el("div");
    strip.className = "totals-strip";
    appendAll(strip, [
      stat("quests", String(totals.quests_done)),
      stat("PRs merged", String(totals.prs_merged)),
      stat("tasks", String(totals.tasks_done)),
      stat("asks answered", String(totals.asks_answered)),
      stat("median answer", formatDuration(totals.median_answer_seconds)),
      stat("handoffs", String(totals.handoffs)),
    ]);
    node.appendChild(strip);
  }

  function field(label, value) {
    var node = el("div");
    node.className = "field";
    appendAll(node, [classedText("dt", label, "field-label"), classedText("dd", value, "field-value")]);
    return node;
  }

  function fieldList(fields) {
    var list = el("dl");
    list.className = "fields";
    appendAll(list, fields);
    return list;
  }

  function epicBar(quest) {
    var progress = quest.epic_progress;
    var wrap = el("div");
    wrap.className = "epic-progress";
    var bar = el("progress");
    bar.max = progress.total;
    bar.value = progress.done;
    appendAll(wrap, [
      classedText(
        "span",
        "epic " + quest.epic + " " + progress.percent + "% (" + progress.done + "/" + progress.total + ")",
        "muted"
      ),
      bar,
    ]);
    return wrap;
  }

  function asksText(quest) {
    if (quest.asks_raised === null) {
      return UNKNOWN;
    }
    var text = quest.asks_answered + "/" + quest.asks_raised + " answered";
    if (quest.median_answer_seconds === null) {
      return text;
    }
    return text + ", median " + formatDuration(quest.median_answer_seconds);
  }

  function driftText(quest) {
    if (!quest.snapshot) {
      return UNKNOWN;
    }
    if (quest.drift.length === 0) {
      return "none";
    }
    return quest.drift.length + " accepted";
  }

  function questHead(quest) {
    var head = el("div");
    head.className = "card-head";
    appendAll(head, [textEl("h3", quest.title), classedText("span", quest.party, "muted")]);
    if (quest.project) {
      head.appendChild(classedText("span", quest.project, "muted"));
    }
    if (!quest.snapshot) {
      head.appendChild(classedText("span", "no snapshot", "badge badge-warn"));
    }
    return head;
  }

  function questCard(quest) {
    var card = el("article");
    card.className = "card quest-card";
    card.appendChild(questHead(quest));
    card.appendChild(
      classedText(
        "p",
        formatDate(quest.started_at) + " → " + formatDate(quest.done_at) + " · " + formatDuration(quest.duration_seconds),
        "muted"
      )
    );
    if (quest.epic_progress) {
      card.appendChild(epicBar(quest));
    }
    card.appendChild(
      fieldList([
        field("tasks", quest.tasks_done + " done, " + quest.tasks_blocked_events + " blocked events"),
        field("SDD tasks", listOrUnknown(quest.sdd_tids)),
        field("JIRA cards", quest.snapshot ? listOrUnknown(quest.jira_cards_done) : UNKNOWN),
        field("PRs", listOrUnknown(quest.prs_merged)),
        field("handoffs", orUnknown(quest.handoffs)),
        field("sessions", orUnknown(quest.sessions)),
        field("asks", asksText(quest)),
        field("drift accepted", driftText(quest)),
      ])
    );
    return card;
  }

  function renderQuests(quests) {
    var node = document.getElementById("quests");
    clear(node);
    node.appendChild(textEl("h2", "Completed quests"));
    if (quests.length === 0) {
      node.appendChild(classedText("p", "no completed quests yet", "muted empty"));
      return;
    }
    var grid = el("div");
    grid.className = "card-grid";
    quests.forEach(function (quest) {
      grid.appendChild(questCard(quest));
    });
    node.appendChild(grid);
  }

  function partyLabel(entry) {
    if (entry.lead) {
      return entry.party + " (lead)";
    }
    return entry.party;
  }

  function raidQuestLabel(quest) {
    return quest.title + " (" + quest.party + ")";
  }

  function raidCard(raid) {
    var card = el("article");
    card.className = "card raid-card";
    var head = el("div");
    head.className = "card-head";
    head.appendChild(textEl("h3", raid.name));
    card.appendChild(head);
    card.appendChild(
      classedText(
        "p",
        formatDate(raid.started_at) + " → " + formatDate(raid.ended_at) + " · " + formatDuration(raid.duration_seconds),
        "muted"
      )
    );
    card.appendChild(
      fieldList([
        field("parties", raid.parties.map(partyLabel).join(", ")),
        field("quests", listOrUnknown(raid.quests.map(raidQuestLabel))),
        field("PRs", listOrUnknown(raid.prs_merged)),
        field("pauses", String(raid.pauses)),
      ])
    );
    return card;
  }

  function renderRaids(raids) {
    var node = document.getElementById("raids");
    clear(node);
    node.appendChild(textEl("h2", "Finished raids"));
    if (raids.length === 0) {
      node.appendChild(classedText("p", "no finished raids yet", "muted empty"));
      return;
    }
    var grid = el("div");
    grid.className = "card-grid";
    raids.forEach(function (raid) {
      grid.appendChild(raidCard(raid));
    });
    node.appendChild(grid);
  }

  function render(model) {
    renderTotals(model.totals);
    renderQuests(model.quests);
    renderRaids(model.raids);
  }

  function showError(message) {
    document.getElementById("generated-at").textContent = message;
  }

  function load() {
    fetch(HISTORY_URL, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("history request failed: " + response.status);
        }
        return response.json();
      })
      .then(render)
      .catch(function (error) {
        showError(error.message);
      });
  }

  load();
})();
