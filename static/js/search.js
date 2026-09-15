/* Search on the Blogs page, backed by the Pagefind index built alongside the
   site. No server: Pagefind downloads only the index fragments a query needs.
   The box stays hidden until the index loads, so the page never offers a
   search that cannot run. While a query is active the timeline steps aside. */
(function () {
  "use strict";

  var base = document.documentElement.getAttribute("data-base") || "";
  var form = document.querySelector("[data-find]");
  var input = document.getElementById("q");
  var list = document.querySelector("[data-results]");
  var meta = document.querySelector("[data-search-meta]");
  var timeline = document.querySelector("[data-timeline]");
  var pagefind = null;
  var seq = 0;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function row(d) {
    var m = d.meta || {};
    return '<li class="row">' +
      '<time class="row__date">' + esc(m.date) + "</time>" +
      '<div class="row__main"><a class="row__title" href="' + esc(d.url) + '">' + esc(m.title) + "</a>" +
      '<p class="result__excerpt">' + d.excerpt + "</p></div></li>";
  }

  function showTimeline(on) {
    timeline.hidden = !on;
    list.hidden = on;
  }

  async function run() {
    var q = input.value.trim();
    var mine = ++seq;
    var url = new URL(window.location.href);
    if (q) url.searchParams.set("q", q); else url.searchParams.delete("q");
    history.replaceState(null, "", url);

    if (!q) { list.innerHTML = ""; meta.textContent = ""; showTimeline(true); return; }

    var res = await pagefind.search(q);
    if (mine !== seq || !res) return;

    var n = res.results.length;
    meta.textContent = n === 0 ? "Nothing matches “" + q + "”." : n + (n === 1 ? " blog" : " blogs");

    var data = await Promise.all(res.results.slice(0, 25).map(function (r) { return r.data(); }));
    if (mine !== seq) return;
    list.innerHTML = data.map(row).join("");
    showTimeline(false);
  }

  (async function init() {
    if (!form || !input) return;
    try {
      pagefind = await import(base + "/pagefind/pagefind.js");
      await pagefind.options({ baseUrl: base + "/", excerptLength: 26 });
      await pagefind.init();
    } catch (e) {
      return;
    }
    form.hidden = false;
    var initial = new URLSearchParams(window.location.search).get("q");
    if (initial) { input.value = initial; run(); }
    var t;
    input.addEventListener("input", function () { clearTimeout(t); t = setTimeout(run, 150); });
  })();
})();
