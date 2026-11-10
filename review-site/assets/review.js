(function () {
  "use strict";
  var body = document.body;
  var repo = body.dataset.repo || "";
  function key(k) { return "rv:" + repo + ":" + k; }
  function get(k) {
    try { return JSON.parse(localStorage.getItem(key(k)) || "null") || {}; } catch (err) { return {}; }
  }
  function set(k, v) {
    try { localStorage.setItem(key(k), JSON.stringify(v)); } catch (err) { /* private window: keep going */ }
  }

  if (body.dataset.page === "index") {
    document.querySelectorAll(".rcard").forEach(function (c) {
      var keys = (c.dataset.keys || "").split(",").filter(Boolean);
      var done = keys.filter(function (k) { return get(k).d; }).length;
      c.querySelector(".done").textContent = done;
      if (keys.length && done === keys.length) c.classList.add("alldone");
      else if (done) c.classList.add("started");
    });
    return;
  }

  // ---- decisions
  var cards = Array.prototype.slice.call(document.querySelectorAll(".card"));
  function grow(ta) { ta.style.height = "auto"; ta.style.height = Math.max(36, ta.scrollHeight + 2) + "px"; }
  function paint(card) {
    var s = get(card.dataset.key);
    card.dataset.d = s.d || "";
    card.querySelectorAll(".decide button").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.dataset.d === s.d));
    });
    var ta = card.querySelector("textarea");
    if (document.activeElement !== ta) { ta.value = s.note || ""; if (ta.value) grow(ta); }
    card.querySelector(".state").textContent = s.d === "ok" ? "Accepted" : s.d === "work" ? "Needs work" : "";
  }
  function progress() {
    var done = cards.filter(function (c) { return get(c.dataset.key).d; }).length;
    document.querySelector(".bar .done").textContent = done;
    document.querySelector(".bar .all").textContent = cards.length;
  }
  function decide(card, d) {
    var s = get(card.dataset.key);
    s.d = s.d === d ? "" : d;
    set(card.dataset.key, s);
    card.classList.remove("peek");
    paint(card);
    progress();
    if (s.d === "work") card.querySelector("textarea").focus();
  }
  cards.forEach(function (card) {
    paint(card);
    card.querySelectorAll(".decide button").forEach(function (b) {
      b.addEventListener("click", function () { decide(card, b.dataset.d); });
    });
    var ta = card.querySelector("textarea");
    ta.addEventListener("input", function () {
      var s = get(card.dataset.key);
      s.note = ta.value;
      set(card.dataset.key, s);
      grow(ta);
    });
    card.querySelector(".chead").addEventListener("click", function () {
      if (card.dataset.d === "ok") card.classList.toggle("peek");
    });
  });
  progress();
  function reveal() {
    var t = location.hash && document.getElementById(location.hash.slice(1));
    if (t && t.classList.contains("card")) t.classList.add("peek");
  }
  window.addEventListener("hashchange", reveal);
  reveal();
  // a link to a decision opens it even when it is folded and already the target
  document.addEventListener("click", function (ev) {
    var a = ev.target.closest && ev.target.closest('a[href^="#d-"]');
    var t = a && document.getElementById(a.getAttribute("href").slice(1));
    if (t) t.classList.add("peek");
  });

  // ---- the review as text for GitHub
  function reviewText() {
    var out = [];
    var papers = document.querySelectorAll(".paper");
    papers.forEach(function (p) {
      var name = p.dataset.paper || body.dataset.label;
      out.push("### Review of " + name + " at " + body.dataset.sha + " (" + body.dataset.label + ")", "");
      var groups = { work: [], ok: [], "": [] };
      p.querySelectorAll(".card").forEach(function (c) {
        var s = get(c.dataset.key);
        groups[s.d || ""].push({ title: c.dataset.title, note: (s.note || "").trim() });
      });
      function list(title, rows) {
        if (!rows.length) return;
        out.push("**" + title + " (" + rows.length + ")**");
        rows.forEach(function (r) { out.push("- **" + r.title + "**" + (r.note ? ": " + r.note.replace(/\s*\n\s*/g, " ") : "")); });
        out.push("");
      }
      list("Needs work", groups.work);
      list("Accepted", groups.ok);
      list("Not decided", groups[""]);
    });
    out.push("_From the review page: " + location.href.split("#")[0] + "_");
    return out.join("\n");
  }
  var copy = document.querySelector(".copy");
  copy.addEventListener("click", function () {
    var text = reviewText();
    function done() {
      copy.textContent = "Copied";
      copy.classList.add("flash");
      setTimeout(function () { copy.textContent = "Copy review"; copy.classList.remove("flash"); }, 1600);
    }
    function fallback() {
      var d = document.createElement("dialog");
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.readOnly = true;
      var close = document.createElement("button");
      close.textContent = "Close";
      close.className = "btn";
      close.addEventListener("click", function () { d.close(); d.remove(); });
      d.appendChild(ta);
      d.appendChild(close);
      document.body.appendChild(d);
      d.showModal();
      ta.select();
    }
    if (navigator.clipboard && navigator.clipboard.writeText) navigator.clipboard.writeText(text).then(done, fallback);
    else fallback();
  });

  // ---- figure viewers
  var still = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  document.querySelectorAll(".viewer").forEach(function (v) {
    var timer = null;
    function mode(m) {
      v.dataset.mode = m;
      v.querySelectorAll(".modes button").forEach(function (b) { b.setAttribute("aria-pressed", String(b.dataset.m === m)); });
      clearInterval(timer);
      v.classList.remove("b");
      if (m === "blink" && !still) timer = setInterval(function () { v.classList.toggle("b"); }, 800);
    }
    v.querySelectorAll(".modes button").forEach(function (b) {
      b.addEventListener("click", function () { mode(b.dataset.m); });
    });
    var stage = v.querySelector(".stage");
    var range = v.querySelector(".swipe");
    if (range) range.addEventListener("input", function () { stage.style.setProperty("--cut", range.value + "%"); });
    if (stage) stage.addEventListener("click", function (ev) {
      if (v.dataset.mode === "blink" && ev.target !== range) v.classList.toggle("b");
    });
  });

  // ---- keys: j and k move between decisions, a accepts, w marks needs work
  document.addEventListener("keydown", function (ev) {
    if (ev.metaKey || ev.ctrlKey || ev.altKey || /^(TEXTAREA|INPUT|SELECT)$/.test(ev.target.tagName)) return;
    var at = cards.indexOf(document.activeElement.closest ? document.activeElement.closest(".card") : null);
    if (ev.key === "j" || ev.key === "k") {
      var next = cards[Math.max(0, Math.min(cards.length - 1, at + (ev.key === "j" ? 1 : -1)))];
      if (at === -1) next = cards[0];
      if (next) { next.focus({ preventScroll: true }); next.scrollIntoView({ block: "center" }); }
      ev.preventDefault();
    } else if ((ev.key === "a" || ev.key === "w") && at !== -1) {
      decide(cards[at], ev.key === "a" ? "ok" : "work");
      ev.preventDefault();
    }
  });
})();
