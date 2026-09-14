/* Search, backed by the Pagefind index built alongside the site. No server:
   Pagefind downloads only the index fragments a query needs. */
(function () {
  "use strict";

  var base = document.documentElement.getAttribute("data-base") || "";
  var input = document.getElementById("q");
  var list = document.querySelector("[data-results]");
  var meta = document.querySelector("[data-search-meta]");
  var filterBox = document.querySelector("[data-filters]");
  var pagefind = null;
  var activeCategory = "";
  var seq = 0;

  function esc(s) {
    return String(s == null ? "" : s).replace(/[&<>"']/g, function (c) {
      return { "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c];
    });
  }

  function row(d) {
    var m = d.meta || {};
    return '<li class="row">' +
      '<span class="row__cat">' + esc(m.category) + "</span>" +
      '<div class="row__main"><a class="row__title" href="' + esc(d.url) + '">' + esc(m.title) + "</a>" +
      '<p class="result__excerpt">' + d.excerpt + "</p></div>" +
      '<time class="row__date">' + esc(m.date) + "</time></li>";
  }

  async function run() {
    var q = input.value.trim();
    var mine = ++seq;
    var url = new URL(window.location.href);
    if (q) url.searchParams.set("q", q); else url.searchParams.delete("q");
    history.replaceState(null, "", url);

    if (!q) { list.innerHTML = ""; meta.textContent = ""; return; }

    var options = activeCategory ? { filters: { category: activeCategory } } : {};
    var res = await pagefind.search(q, options);
    if (mine !== seq || !res) return;

    var n = res.results.length;
    meta.textContent = n === 0
      ? "Nothing matches “" + q + "”" + (activeCategory ? " in " + activeCategory : "") + "."
      : n + (n === 1 ? " post" : " posts") + (activeCategory ? " in " + activeCategory : "");

    var data = await Promise.all(res.results.slice(0, 25).map(function (r) { return r.data(); }));
    if (mine !== seq) return;
    list.innerHTML = data.map(row).join("");
  }

  async function buildFilters() {
    var filters = await pagefind.filters();
    var cats = filters && filters.category ? Object.keys(filters.category).sort() : [];
    if (cats.length < 2) return;
    filterBox.innerHTML = ['<button type="button" class="chip" data-cat="" aria-pressed="true">All subjects</button>']
      .concat(cats.map(function (c) {
        return '<button type="button" class="chip" data-cat="' + esc(c) + '" aria-pressed="false">' + esc(c) + "</button>";
      })).join("");
    filterBox.hidden = false;
    filterBox.addEventListener("click", function (e) {
      var b = e.target.closest("[data-cat]");
      if (!b) return;
      activeCategory = b.getAttribute("data-cat");
      filterBox.querySelectorAll("[data-cat]").forEach(function (x) { x.setAttribute("aria-pressed", String(x === b)); });
      run();
    });
  }

  (async function init() {
    try {
      pagefind = await import(base + "/pagefind/pagefind.js");
      await pagefind.options({ baseUrl: base + "/", excerptLength: 26 });
      await pagefind.init();
    } catch (e) {
      meta.textContent = "Search isn’t available in this build. Every post is listed under All posts.";
      input.disabled = true;
      return;
    }
    buildFilters();
    var initial = new URLSearchParams(window.location.search).get("q");
    if (initial) { input.value = initial; run(); }
    var t;
    input.addEventListener("input", function () { clearTimeout(t); t = setTimeout(run, 150); });
  })();
})();
