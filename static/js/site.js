/* CCLGFL Blog — reading settings, menu, progress, note highlighting, copy.
   Everything here is enhancement: without it the site still reads, notes still
   fold open (CSS checkbox), and search falls back to the index page. */
(function () {
  "use strict";

  var root = document.documentElement;
  var KEY = "cclgfl-reader";

  function load() { try { return JSON.parse(localStorage.getItem(KEY) || "{}"); } catch (e) { return {}; } }
  function save(s) { try { localStorage.setItem(KEY, JSON.stringify(s)); } catch (e) { /* private mode */ } }

  var state = load();

  /* ── reading settings ─────────────────────────────────────────────── */

  function apply() {
    var theme = state.theme || "auto";
    if (theme === "auto") root.removeAttribute("data-theme"); else root.setAttribute("data-theme", theme);
    root.style.setProperty("--read-scale", state.size || "1");
    if (state.notes === "text") root.setAttribute("data-notes", "text"); else root.removeAttribute("data-notes");

    var current = { theme: theme, size: state.size || "1", notes: state.notes || "margin" };
    document.querySelectorAll("[data-set]").forEach(function (b) {
      b.setAttribute("aria-pressed", String(b.getAttribute("data-value") === current[b.getAttribute("data-set")]));
    });
  }
  apply();

  var panel = document.getElementById("settings");
  var lastTrigger = null;

  function openPanel(trigger) {
    var r = trigger.getBoundingClientRect();
    panel.style.top = Math.round(r.bottom + 8) + "px";
    panel.style.right = Math.max(12, Math.round(window.innerWidth - r.right)) + "px";
    panel.hidden = false;
    trigger.setAttribute("aria-expanded", "true");
    lastTrigger = trigger;
    var pressed = panel.querySelector('[aria-pressed="true"]');
    (pressed || panel.querySelector("button")).focus();
  }
  function closePanel(refocus) {
    if (!panel || panel.hidden) return;
    panel.hidden = true;
    document.querySelectorAll("[data-settings-toggle]").forEach(function (t) { t.setAttribute("aria-expanded", "false"); });
    if (refocus && lastTrigger) lastTrigger.focus();
  }

  document.querySelectorAll("[data-settings-toggle]").forEach(function (t) {
    t.addEventListener("click", function (e) {
      e.stopPropagation();
      if (panel.hidden) openPanel(t); else closePanel(false);
    });
  });
  if (panel) {
    panel.addEventListener("click", function (e) {
      e.stopPropagation();
      var b = e.target.closest("[data-set]");
      if (!b) return;
      state[b.getAttribute("data-set")] = b.getAttribute("data-value");
      save(state);
      apply();
    });
  }

  /* ── mobile menu ──────────────────────────────────────────────────── */

  var nav = document.getElementById("site-nav");
  var menuBtns = document.querySelectorAll("[data-menu-toggle]");
  function closeMenu() {
    if (!nav) return;
    nav.classList.remove("is-open");
    menuBtns.forEach(function (b) { b.setAttribute("aria-expanded", "false"); });
  }
  menuBtns.forEach(function (b) {
    b.addEventListener("click", function (e) {
      e.stopPropagation();
      var open = !nav.classList.contains("is-open");
      if (open) {
        nav.style.setProperty("--nav-top", Math.round(b.getBoundingClientRect().bottom + 10) + "px");
        nav.classList.add("is-open");
      } else {
        nav.classList.remove("is-open");
      }
      b.setAttribute("aria-expanded", String(open));
    });
  });

  document.addEventListener("click", function (e) {
    closePanel(false);
    if (nav && nav.classList.contains("is-open") && !nav.contains(e.target)) closeMenu();
    document.querySelectorAll(".subjects-menu[open]").forEach(function (d) {
      if (!d.contains(e.target)) d.removeAttribute("open");
    });
  });
  document.addEventListener("keydown", function (e) {
    if (e.key !== "Escape") return;
    closePanel(true);
    closeMenu();
    document.querySelectorAll(".subjects-menu[open]").forEach(function (d) { d.removeAttribute("open"); });
  });

  /* ── reading progress and current section ─────────────────────────── */

  var prose = document.querySelector("[data-prose]");
  var bar = document.querySelector("[data-progress]");
  var sectionLabel = document.querySelector("[data-section]");

  if (prose && bar) {
    var heads = [].slice.call(prose.querySelectorAll("h2"));
    var ticking = false;

    var update = function () {
      ticking = false;
      var r = prose.getBoundingClientRect();
      var span = Math.max(r.height - window.innerHeight * 0.5, 1);
      var done = Math.min(Math.max(window.innerHeight * 0.35 - r.top, 0), span);
      bar.style.transform = "scaleX(" + (done / span).toFixed(4) + ")";

      if (sectionLabel) {
        var label = "";
        for (var i = 0; i < heads.length; i++) {
          if (heads[i].getBoundingClientRect().top > 140) break;
          var no = heads[i].querySelector(".h-no");
          var t = heads[i].querySelector(".h-t");
          label = (no ? no.textContent + ". " : "") + (t ? t.textContent : heads[i].textContent);
        }
        if (sectionLabel.textContent !== label) sectionLabel.textContent = label;
      }
    };
    var onScroll = function () { if (!ticking) { ticking = true; requestAnimationFrame(update); } };
    window.addEventListener("scroll", onScroll, { passive: true });
    window.addEventListener("resize", onScroll);
    update();
  }

  /* ── note highlighting: the marker and its note light together ────── */

  document.querySelectorAll(".sn-ref").forEach(function (ref) {
    var note = document.getElementById("note-" + ref.getAttribute("data-note"));
    if (!note) return;
    var on = function () { ref.classList.add("is-lit"); note.classList.add("is-lit"); };
    var off = function () { ref.classList.remove("is-lit"); note.classList.remove("is-lit"); };
    ref.addEventListener("mouseenter", on);
    ref.addEventListener("mouseleave", off);
    note.addEventListener("mouseenter", on);
    note.addEventListener("mouseleave", off);
  });

  /* ── copy buttons ─────────────────────────────────────────────────── */

  var toast = document.querySelector("[data-toast]");
  var toastTimer;
  function say(msg) {
    if (!toast) return;
    toast.textContent = msg;
    toast.classList.add("is-on");
    clearTimeout(toastTimer);
    toastTimer = setTimeout(function () { toast.classList.remove("is-on"); }, 2200);
  }

  function copyText(text) {
    if (navigator.clipboard && window.isSecureContext) return navigator.clipboard.writeText(text);
    return new Promise(function (resolve, reject) {
      var ta = document.createElement("textarea");
      ta.value = text;
      ta.setAttribute("readonly", "");
      ta.style.position = "fixed";
      ta.style.opacity = "0";
      document.body.appendChild(ta);
      ta.select();
      try { document.execCommand("copy") ? resolve() : reject(); } catch (e) { reject(e); }
      document.body.removeChild(ta);
    });
  }

  document.querySelectorAll("[data-copy]").forEach(function (b) {
    b.addEventListener("click", function () {
      copyText(b.getAttribute("data-copy")).then(
        function () { say(b.getAttribute("data-copied") || "Copied"); },
        function () { say("Couldn't copy — select the text instead"); }
      );
    });
  });
})();
