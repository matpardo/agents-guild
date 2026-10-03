(function () {
  "use strict";

  var HISTORY_URL = "/api/history";
  var HOUR_MS = 3600000;

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

  function appendAll(node, children) {
    children.forEach(function (child) {
      node.appendChild(child);
    });
  }

  function clear(node) {
    while (node.firstChild) {
      node.removeChild(node.firstChild);
    }
  }

  function formatDate(iso) {
    return iso.slice(0, 16).replace("T", " ");
  }

  function formatAge(milliseconds) {
    var minutes = Math.floor(milliseconds / 60000);
    var hours = Math.floor(minutes / 60);
    var days = Math.floor(hours / 24);
    if (days > 0) {
      return days + "d " + (hours % 24) + "h ago";
    }
    if (hours > 0) {
      return hours + "h " + (minutes % 60) + "m ago";
    }
    if (minutes > 0) {
      return minutes + "m ago";
    }
    return "just now";
  }

  function idleMilliseconds(quest, nowMs) {
    return nowMs - new Date(quest.last_activity_at).getTime();
  }

  function isStale(quest, nowMs) {
    return idleMilliseconds(quest, nowMs) > quest.stale_hours * HOUR_MS;
  }

  function cell(child) {
    var node = el("td");
    node.appendChild(child);
    return node;
  }

  function textCell(value, className) {
    return cell(classedText("span", value, className));
  }

  function percentCell(quest) {
    var wrap = el("div");
    wrap.className = "epic-progress";
    var bar = el("progress");
    bar.max = quest.tasks.total;
    bar.value = quest.tasks.done;
    appendAll(wrap, [
      classedText("span", quest.percent_done + "% (" + quest.tasks.done + "/" + quest.tasks.total + ")", "muted"),
      bar,
    ]);
    return cell(wrap);
  }

  function startedCell(quest) {
    if (!quest.started_at) {
      return textCell("unknown", "muted");
    }
    return textCell(formatDate(quest.started_at), "muted");
  }

  function activityCell(quest, nowMs) {
    var wrap = el("span");
    if (!quest.last_activity_at) {
      wrap.appendChild(classedText("span", "no activity recorded", "muted"));
      return cell(wrap);
    }
    wrap.appendChild(classedText("span", formatAge(idleMilliseconds(quest, nowMs)), "muted"));
    if (isStale(quest, nowMs)) {
      var marker = classedText("span", "stale", "badge badge-warn stale-marker");
      marker.title = "no activity for more than " + quest.stale_hours + "h";
      wrap.appendChild(marker);
    }
    return cell(wrap);
  }

  function row(quest, nowMs) {
    var tr = el("tr");
    appendAll(tr, [
      textCell(quest.party, "party-name"),
      textCell(quest.title, "quest-title"),
      percentCell(quest),
      startedCell(quest),
      activityCell(quest, nowMs),
    ]);
    return tr;
  }

  function headRow() {
    var tr = el("tr");
    ["party", "quest", "progress", "started", "last activity"].forEach(function (label) {
      var th = textEl("th", label);
      th.scope = "col";
      tr.appendChild(th);
    });
    return tr;
  }

  function table(quests, nowMs) {
    var scroller = el("div");
    scroller.className = "table-scroll";
    var tbl = el("table");
    tbl.className = "progress-table";
    var head = el("thead");
    head.appendChild(headRow());
    var body = el("tbody");
    quests.forEach(function (quest) {
      body.appendChild(row(quest, nowMs));
    });
    appendAll(tbl, [head, body]);
    scroller.appendChild(tbl);
    return scroller;
  }

  function render(model) {
    var node = document.getElementById("progress-table");
    clear(node);
    node.appendChild(textEl("h2", "In progress (" + model.active_quests.length + ")"));
    if (model.active_quests.length === 0) {
      node.appendChild(classedText("p", "nothing in progress", "muted empty"));
      return;
    }
    node.appendChild(table(model.active_quests, Date.now()));
  }

  function showError(message) {
    document.getElementById("generated-at").textContent = message;
  }

  function load() {
    fetch(HISTORY_URL, { cache: "no-store" })
      .then(function (response) {
        if (!response.ok) {
          throw new Error("progress request failed: " + response.status);
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
