(function () {
  "use strict";

  var REFRESH_INTERVAL_MS = 15000;
  var ARCHIVED_URL = "/api/archived-notices";
  var SESSION_URL = "/api/session";
  var NO_SESSION_MESSAGE = "session token not loaded, reload the page";
  var sessionToken = null;

  var state = {
    statuses: {},
    busy: {},
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

  function errorMessage(body) {
    if (body && typeof body.error === "string") {
      return body.error;
    }
    return "request failed";
  }

  function sendUnarchive(noticeId) {
    return fetch("/api/notices/" + noticeId + "/unarchive", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-Guild-Token": sessionToken,
      },
      body: "{}",
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

  function unarchive(noticeId) {
    if (sessionToken === null) {
      state.statuses[noticeId] = NO_SESSION_MESSAGE;
      fetchArchived();
      return;
    }
    state.busy[noticeId] = true;
    state.statuses[noticeId] = "sending...";
    fetchArchived();
    sendUnarchive(noticeId).then(function (result) {
      delete state.busy[noticeId];
      if (result.ok) {
        delete state.statuses[noticeId];
      } else {
        state.statuses[noticeId] = errorMessage(result.body);
      }
      fetchArchived();
    });
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
    article.appendChild(head);
    article.appendChild(textEl("p", notice.text));
    var actions = el("div");
    actions.className = "notice-actions";
    var button = textEl("button", "Unarchive");
    button.type = "button";
    button.disabled = state.busy[notice.id] === true;
    button.addEventListener("click", function () {
      unarchive(notice.id);
    });
    actions.appendChild(button);
    var status = textEl("span", state.statuses[notice.id] || "");
    status.className = "ask-status";
    actions.appendChild(status);
    article.appendChild(actions);
    return article;
  }

  function render(data) {
    document.getElementById("generated-at").textContent = "generated at " + data.generated_at;
    var section = document.getElementById("archived");
    clear(section);
    section.appendChild(textEl("h2", "archived (" + data.notices.length + ")"));
    data.notices.forEach(function (notice) {
      section.appendChild(renderNotice(notice));
    });
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

  function fetchArchived() {
    fetch(ARCHIVED_URL)
      .then(function (response) {
        return response.json();
      })
      .then(render)
      .catch(function () {});
  }

  document.addEventListener("DOMContentLoaded", function () {
    fetchSession();
    fetchArchived();
    setInterval(fetchArchived, REFRESH_INTERVAL_MS);
  });
})();
