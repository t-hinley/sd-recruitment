(function () {
  "use strict";
  document.documentElement.classList.add("js");

  // Header shadow once the page scrolls
  var header = document.getElementById("site-header");
  var onScroll = function () {
    if (header) header.classList.toggle("is-scrolled", window.scrollY > 8);
  };
  window.addEventListener("scroll", onScroll, { passive: true });
  onScroll();

  // Mobile navigation
  var toggle = document.querySelector(".nav-toggle");
  var nav = document.getElementById("site-nav");
  if (toggle && nav) {
    var setOpen = function (open) {
      if (open && header) nav.style.setProperty("--nav-top", header.getBoundingClientRect().bottom + "px");
      toggle.setAttribute("aria-expanded", String(open));
      toggle.setAttribute("aria-label", open ? "Close menu" : "Open menu");
      nav.classList.toggle("is-open", open);
      document.body.style.overflow = open ? "hidden" : "";
    };
    toggle.addEventListener("click", function () { setOpen(toggle.getAttribute("aria-expanded") !== "true"); });
    nav.addEventListener("click", function (e) { if (e.target.closest("a")) setOpen(false); });
    document.addEventListener("keydown", function (e) { if (e.key === "Escape") setOpen(false); });
    window.addEventListener("resize", function () { if (window.innerWidth > 980) setOpen(false); });
  }

  // Candidates page: the career support buttons open the same form with that service ticked.
  // Without JavaScript the links still work (?service=... pre-selects it on the server).
  var support = document.getElementById("support-options");
  if (support) {
    document.querySelectorAll("a[data-service]").forEach(function (link) {
      link.addEventListener("click", function (e) {
        var service = link.getAttribute("data-service");
        if (service) {
          var box = support.querySelector('input[value="' + service + '"]');
          if (box) box.checked = true;
        }
        e.preventDefault();
        // On phones the intro text sits above the form, so go straight to the ticked options.
        var target = window.innerWidth <= 980 ? support : document.getElementById("register");
        if (target) target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        history.replaceState(null, "", service ? "?service=" + service + "#register" : "#register");
        var first = support.querySelector("input");
        if (first) setTimeout(function () { first.focus({ preventScroll: true }); }, 450);
      });
    });
  }

  // Resume upload: show the chosen file name, and allow dropping a file.
  document.querySelectorAll(".upload").forEach(function (zone) {
    var input = zone.querySelector("input[type=file]");
    var text = zone.querySelector("[data-upload-text]");
    if (!input || !text) return;
    var original = text.innerHTML;
    var show = function () {
      var f = input.files && input.files[0];
      zone.classList.toggle("has-file", !!f);
      if (f) {
        var mb = (f.size / 1048576).toFixed(1);
        text.textContent = f.name + " (" + mb + " MB) – click to change";
      } else {
        text.innerHTML = original;
      }
    };
    input.addEventListener("change", show);
    ["dragenter", "dragover"].forEach(function (ev) {
      zone.addEventListener(ev, function () { zone.classList.add("is-drag"); });
    });
    ["dragleave", "drop"].forEach(function (ev) {
      zone.addEventListener(ev, function () { zone.classList.remove("is-drag"); });
    });
  });

  // Move keyboard / screen reader focus to a form's error or thank-you message after submitting.
  var msg = document.querySelector("[data-focus]");
  if (msg) {
    var place = function () {
      msg.scrollIntoView({ block: "center", behavior: "instant" });
      msg.focus({ preventScroll: true });
    };
    // Run after fonts and layout settle, so the message ends up in view.
    if (document.readyState === "complete") place(); else window.addEventListener("load", place);
  }
})();
