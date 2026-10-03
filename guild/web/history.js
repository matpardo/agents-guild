(function () {
  "use strict";

  var HISTORY_URL = "/api/history";
  var MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];
  var DAY_MS = 86400000;
  var PARTIAL_DATA_HINT = "recorded before achievements were captured; some fields unknown";

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

  function plural(count, singular, pluralForm) {
    return count + " " + (count === 1 ? singular : pluralForm);
  }

  function formatDuration(seconds) {
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
    return iso.slice(0, 16).replace("T", " ");
  }

  function dayLabel(date) {
    var label = date.getUTCDate() + " " + MONTHS[date.getUTCMonth()];
    if (date.getUTCFullYear() === new Date().getUTCFullYear()) {
      return label;
    }
    return label + " " + date.getUTCFullYear();
  }

  function weekStart(iso) {
    var date = new Date(iso);
    var midnight = Date.UTC(date.getUTCFullYear(), date.getUTCMonth(), date.getUTCDate());
    return midnight - ((date.getUTCDay() + 6) % 7) * DAY_MS;
  }

  function summaryLine(parts) {
    var present = parts.filter(function (part) {
      return part !== null;
    });
    if (present.length === 0) {
      return null;
    }
    return classedText("p", present.join(" · "), "summary-line");
  }

  function countPart(count, singular, pluralForm) {
    if (!count) {
      return null;
    }
    return plural(count, singular, pluralForm);
  }

  function field(label, value) {
    var node = el("div");
    node.className = "field";
    appendAll(node, [classedText("dt", label, "field-label"), classedText("dd", value, "field-value")]);
    return node;
  }

  function nodeField(label, valueNode) {
    var node = el("div");
    node.className = "field";
    var value = el("dd");
    value.className = "field-value";
    value.appendChild(valueNode);
    appendAll(node, [classedText("dt", label, "field-label"), value]);
    return node;
  }

  function fold(fields) {
    var details = el("details");
    details.className = "more";
    var list = el("dl");
    list.className = "fields";
    appendAll(list, fields);
    appendAll(details, [textEl("summary", "more"), list]);
    return details;
  }

  function tag(text, hint) {
    var node = classedText("span", text, "tag");
    if (hint) {
      node.title = hint;
    }
    return node;
  }

  function prLink(repo, number) {
    var link = el("a");
    link.href = "https://github.com/" + repo + "/pull/" + number;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = "#" + number;
    return link;
  }

  function groupPrs(refs) {
    var byRepo = {};
    refs.forEach(function (ref) {
      var cut = ref.lastIndexOf("#");
      var repo = ref.slice(0, cut);
      byRepo[repo] = (byRepo[repo] || []).concat([Number(ref.slice(cut + 1))]);
    });
    return Object.keys(byRepo)
      .sort()
      .map(function (repo) {
        return {
          repo: repo,
          numbers: byRepo[repo].sort(function (a, b) {
            return a - b;
          }),
        };
      });
  }

  function shortRepo(repo) {
    return repo.slice(repo.indexOf("/") + 1);
  }

  function prLinks(refs) {
    var wrap = el("span");
    wrap.className = "pr-links";
    groupPrs(refs).forEach(function (group, index) {
      if (index > 0) {
        wrap.appendChild(document.createTextNode(" · "));
      }
      wrap.appendChild(document.createTextNode(shortRepo(group.repo) + ": "));
      group.numbers.forEach(function (number, position) {
        if (position > 0) {
          wrap.appendChild(document.createTextNode(" "));
        }
        wrap.appendChild(prLink(group.repo, number));
      });
    });
    return wrap;
  }

  function stat(label, value) {
    var node = el("div");
    node.className = "stat";
    appendAll(node, [classedText("span", value, "stat-value"), classedText("span", label, "stat-label")]);
    return node;
  }

  function totalsRow(label, totals) {
    var row = el("div");
    row.className = "totals-row";
    var median = totals.median_answer_seconds === null ? "" : " (median " + formatDuration(totals.median_answer_seconds) + ")";
    var strip = el("div");
    strip.className = "totals-strip";
    appendAll(strip, [
      stat("quests done", String(totals.quests_done)),
      stat("PRs merged", String(totals.prs_merged)),
      stat("tasks done", String(totals.tasks_done)),
      stat("asks answered" + median, String(totals.asks_answered)),
      stat("handoffs", String(totals.handoffs)),
    ]);
    appendAll(row, [classedText("h3", label, "totals-label"), strip]);
    return row;
  }

  function renderTotals(model) {
    var node = document.getElementById("totals");
    clear(node);
    node.appendChild(textEl("h2", "Hall of achievements"));
    if (model.since) {
      node.appendChild(classedText("p", "since " + dayLabel(new Date(model.since)), "muted"));
    }
    appendAll(node, [totalsRow("this week", model.week_totals), totalsRow("all time", model.totals)]);
  }

  function epicBar(quest) {
    var progress = quest.epic_progress;
    var wrap = el("div");
    wrap.className = "epic-progress";
    var bar = el("progress");
    bar.max = progress.total;
    bar.value = progress.done;
    appendAll(wrap, [classedText("span", "epic " + quest.epic + " " + progress.percent + "%", "muted"), bar]);
    return wrap;
  }

  function driftItem(item) {
    if (typeof item === "string") {
      return item;
    }
    return JSON.stringify(item);
  }

  function questAsks(quest) {
    if (!quest.asks_raised) {
      return null;
    }
    var text = quest.asks_raised + " raised, " + quest.asks_answered + " answered";
    if (quest.median_answer_seconds === null) {
      return text;
    }
    return text + ", median " + formatDuration(quest.median_answer_seconds);
  }

  function nonEmpty(fields) {
    return fields.filter(function (entry) {
      return entry !== null;
    });
  }

  function listField(label, values) {
    if (!values || values.length === 0) {
      return null;
    }
    return field(label, values.join(", "));
  }

  function textField(label, value) {
    if (value === null || value === undefined) {
      return null;
    }
    return field(label, String(value));
  }

  function prField(refs) {
    if (!refs || refs.length === 0) {
      return null;
    }
    return nodeField("PRs", prLinks(refs));
  }

  function questDetails(quest) {
    var blocked = quest.tasks_blocked_events > 0 ? "blocked " + plural(quest.tasks_blocked_events, "time", "times") : null;
    var drift = quest.drift.length > 0 ? quest.drift.map(driftItem) : null;
    var asks = questAsks(quest);
    return nonEmpty([
      listField("SDD tasks", quest.sdd_tids),
      listField("JIRA cards", quest.jira_cards_done),
      prField(quest.prs_merged),
      asks === null ? null : field("asks", asks),
      textField("sessions", quest.sessions),
      blocked === null ? null : field("blocked", blocked),
      drift === null ? null : field("drift accepted at close", drift.join("; ")),
    ]);
  }

  function questTags(quest, showProject) {
    var tags = [tag(quest.party, null)];
    if (quest.duration_seconds !== null) {
      tags.push(tag(formatDuration(quest.duration_seconds), null));
    }
    if (showProject && quest.project) {
      tags.push(tag(quest.project, null));
    }
    if (!quest.snapshot) {
      tags.push(tag("partial data", PARTIAL_DATA_HINT));
    }
    return tags;
  }

  function appendIfPresent(parent, child) {
    if (child !== null) {
      parent.appendChild(child);
    }
  }

  function card(titleText, tags) {
    var node = el("article");
    node.className = "card achievement-card";
    var tagRow = el("div");
    tagRow.className = "tags";
    appendAll(tagRow, tags);
    appendAll(node, [classedText("h3", titleText, "card-title"), tagRow]);
    return node;
  }

  function questCard(quest, showProject) {
    var node = card(quest.title, questTags(quest, showProject));
    appendIfPresent(
      node,
      summaryLine([
        countPart(quest.tasks_done, "task", "tasks"),
        countPart(quest.prs_merged.length, "PR", "PRs"),
        countPart(quest.handoffs, "handoff", "handoffs"),
      ])
    );
    if (quest.epic_progress) {
      node.appendChild(epicBar(quest));
    }
    var fields = questDetails(quest);
    if (fields.length > 0) {
      node.appendChild(fold(fields));
    }
    return node;
  }

  function groupByWeek(quests) {
    var groups = {};
    quests.forEach(function (quest) {
      var key = weekStart(quest.done_at);
      groups[key] = (groups[key] || []).concat([quest]);
    });
    return Object.keys(groups)
      .map(Number)
      .sort(function (a, b) {
        return b - a;
      })
      .map(function (key) {
        return { start: key, quests: groups[key] };
      });
  }

  function projectsIn(lists) {
    var seen = {};
    lists.forEach(function (list) {
      list.forEach(function (quest) {
        if (quest.project) {
          seen[quest.project] = true;
        }
      });
    });
    return Object.keys(seen);
  }

  function cardGrid(cards) {
    var grid = el("div");
    grid.className = "card-grid";
    appendAll(grid, cards);
    return grid;
  }

  function renderQuests(model, showProject) {
    var node = document.getElementById("quests");
    clear(node);
    node.appendChild(textEl("h2", "Completed quests"));
    if (model.quests.length === 0) {
      node.appendChild(classedText("p", "no completed quests yet", "muted empty"));
      return;
    }
    groupByWeek(model.quests).forEach(function (group) {
      var week = el("section");
      week.className = "week";
      week.appendChild(textEl("h3", "week of " + dayLabel(new Date(group.start))));
      week.appendChild(
        cardGrid(
          group.quests.map(function (quest) {
            return questCard(quest, showProject);
          })
        )
      );
      node.appendChild(week);
    });
  }

  function partyLabel(entry) {
    if (entry.lead) {
      return entry.party + " (lead)";
    }
    return entry.party;
  }

  function raidDetails(raid) {
    var quests = raid.quests.map(function (quest) {
      return quest.title + " (" + quest.party + ")";
    });
    return nonEmpty([
      field("when", formatDate(raid.started_at) + " → " + formatDate(raid.ended_at)),
      field("parties", raid.parties.map(partyLabel).join(", ")),
      listField("quests", quests),
      prField(raid.prs_merged),
    ]);
  }

  function raidCard(raid) {
    var tags = [tag(plural(raid.parties.length, "party", "parties"), null)];
    if (raid.duration_seconds !== null) {
      tags.push(tag(formatDuration(raid.duration_seconds), null));
    }
    var node = card(raid.name, tags);
    appendIfPresent(
      node,
      summaryLine([
        countPart(raid.quests.length, "quest", "quests"),
        countPart(raid.prs_merged.length, "PR", "PRs"),
        countPart(raid.pauses, "pause", "pauses"),
      ])
    );
    node.appendChild(fold(raidDetails(raid)));
    return node;
  }

  function renderRaids(raids) {
    var node = document.getElementById("raids");
    clear(node);
    node.appendChild(textEl("h2", "Finished raids"));
    if (raids.length === 0) {
      node.appendChild(classedText("p", "no finished raids yet", "muted empty"));
      return;
    }
    node.appendChild(cardGrid(raids.map(raidCard)));
  }

  function incompleteCard(quest, showProject) {
    var tags = [tag(quest.party, null)];
    if (showProject && quest.project) {
      tags.push(tag(quest.project, null));
    }
    var node = card(quest.title, tags);
    node.appendChild(classedText("p", quest.reason, "reason"));
    appendIfPresent(
      node,
      summaryLine([quest.tasks_not_done + " of " + plural(quest.tasks_total, "task", "tasks") + " not done"])
    );
    return node;
  }

  function renderIncompleteQuests(quests, showProject) {
    var node = document.getElementById("incomplete-quests");
    clear(node);
    var details = el("details");
    details.className = "closed-section";
    details.appendChild(textEl("summary", "Closed without completing (" + quests.length + ")"));
    if (quests.length === 0) {
      details.appendChild(classedText("p", "nothing closed without completing", "muted empty"));
    } else {
      details.appendChild(
        cardGrid(
          quests.map(function (quest) {
            return incompleteCard(quest, showProject);
          })
        )
      );
    }
    node.appendChild(details);
  }

  function render(model) {
    var showProject = projectsIn([model.quests, model.incomplete_quests]).length > 1;
    renderTotals(model);
    renderQuests(model, showProject);
    renderRaids(model.raids);
    renderIncompleteQuests(model.incomplete_quests, showProject);
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
