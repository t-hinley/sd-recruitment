/* Admin page behaviour shared by all admin pages. */

/* Live search: lists filter by themselves once you stop typing (no need to press Enter). The page reloads
   with the results and the cursor goes back to the end of the search box, so typing can carry on. */
(function () {
  var DELAY = 500, KEY = "sd_live_search";
  try {  // after a live-search reload: put the cursor back in the box
    var back = JSON.parse(sessionStorage.getItem(KEY) || "null");
    sessionStorage.removeItem(KEY);
    if (back && back.path === location.pathname) {
      var box = document.querySelector('form[data-live-search] input[name="q"]');
      if (box) { box.focus(); var n = box.value.length; box.setSelectionRange(n, n); }
    }
  } catch (e) {}
  document.querySelectorAll("form[data-live-search]").forEach(function (form) {
    var input = form.querySelector('input[name="q"]');
    if (!input) return;
    var timer = null, sent = input.value.trim();
    input.addEventListener("input", function () {
      clearTimeout(timer);
      form.classList.add("is-typing");
      timer = setTimeout(function () {
        var v = input.value.trim();
        form.classList.remove("is-typing");
        if (v === sent || v.length === 1) return;  // unchanged, or wait for at least two letters
        sent = v;
        try { sessionStorage.setItem(KEY, JSON.stringify({path: location.pathname})); } catch (e) {}
        var page = form.querySelector('input[name="page"], input[name="p"]');
        if (page) page.disabled = true;  // a new search starts on the first page
        if (form.requestSubmit) form.requestSubmit(); else form.submit();
      }, DELAY);
    });
  });
})();
