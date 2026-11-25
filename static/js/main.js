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
          if (box && !box.checked) {
            box.checked = true;
            box.dispatchEvent(new Event("change", { bubbles: true }));
          }
        }
        e.preventDefault();
        // On phones the intro text sits above the form, so go straight to the ticked options.
        var target = window.innerWidth <= 980 ? support : document.getElementById("register");
        if (target) target.scrollIntoView({ behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
        history.replaceState(null, "", service ? "?service=" + service + "#register" : "#register");
        var first = support.querySelector(".ms__add") || support.querySelector("input");
        if (first) setTimeout(function () { first.focus({ preventScroll: true }); }, 450);
      });
    });
  }

  // Multi-choice groups as an Airtable-style dropdown: chosen options show as removable pills and a
  // "+ Add" button opens a list of the remaining options. The real checkboxes stay in the form
  // (hidden), so the form still submits normally, and without JavaScript the plain chips show.
  document.querySelectorAll("[data-multiselect]").forEach(function (group, gi) {
    var inputs = Array.prototype.slice.call(group.querySelectorAll("input[type=checkbox]"));
    if (!inputs.length) return;
    var labelOf = function (input) { return input.closest("label").textContent.trim(); };
    var listId = "ms-list-" + gi;

    var ms = document.createElement("div");
    ms.className = "ms";
    ms.innerHTML =
      '<div class="ms__control"><div class="ms__values"></div>' +
      '<button type="button" class="ms__add" aria-haspopup="listbox" aria-expanded="false" aria-controls="' + listId + '">' +
      '<svg class="icon" aria-hidden="true"><use href="#i-plus"/></svg><span></span></button></div>' +
      '<div class="ms__menu" id="' + listId + '" role="listbox" aria-multiselectable="true" hidden></div>';
    group.hidden = true;
    group.parentNode.insertBefore(ms, group.nextSibling);

    var values = ms.querySelector(".ms__values"), add = ms.querySelector(".ms__add"),
        addText = add.querySelector("span"), menu = ms.querySelector(".ms__menu");
    var legend = group.closest("fieldset") && group.closest("fieldset").querySelector("legend");
    if (legend) add.setAttribute("aria-label", "Add " + legend.textContent.replace(/\(optional\)|\*/g, "").trim());

    var close = function (focusAdd) {
      menu.hidden = true;
      add.setAttribute("aria-expanded", "false");
      if (focusAdd) add.focus();
    };
    var render = function () {
      values.innerHTML = "";
      menu.innerHTML = "";
      var remaining = 0;
      inputs.forEach(function (input) {
        if (input.checked) {
          var pill = document.createElement("span");
          pill.className = "ms__pill";
          pill.innerHTML = '<span></span><button type="button" class="ms__remove"><svg class="icon" aria-hidden="true"><use href="#i-x"/></svg></button>';
          pill.firstChild.textContent = labelOf(input);
          var rm = pill.querySelector("button");
          rm.setAttribute("aria-label", "Remove " + labelOf(input));
          rm.addEventListener("click", function () {
            input.checked = false;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            add.focus();
          });
          values.appendChild(pill);
        } else {
          remaining++;
          var opt = document.createElement("button");
          opt.type = "button";
          opt.className = "ms__option";
          opt.setAttribute("role", "option");
          opt.setAttribute("aria-selected", "false");
          opt.innerHTML = '<svg class="icon" aria-hidden="true"><use href="#i-plus"/></svg><span></span>';
          opt.lastChild.textContent = labelOf(input);
          opt.addEventListener("click", function () {
            input.checked = true;
            input.dispatchEvent(new Event("change", { bubbles: true }));
            if (menu.querySelector(".ms__option")) { menu.hidden = false; menu.querySelector(".ms__option").focus(); }
            else close(true);
          });
          menu.appendChild(opt);
        }
      });
      var any = inputs.some(function (i) { return i.checked; });
      addText.textContent = any ? "Add" : group.getAttribute("data-placeholder") || "Add";
      ms.classList.toggle("has-values", any);
      add.hidden = remaining === 0;
      if (remaining === 0) close(false);
    };

    add.addEventListener("click", function () {
      var open = menu.hidden;
      menu.hidden = !open;
      add.setAttribute("aria-expanded", String(open));
      if (open && menu.firstChild) menu.firstChild.focus();
    });
    menu.addEventListener("keydown", function (e) {
      var items = Array.prototype.slice.call(menu.querySelectorAll(".ms__option"));
      var i = items.indexOf(document.activeElement);
      if (e.key === "ArrowDown") { e.preventDefault(); (items[i + 1] || items[0]).focus(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); (items[i - 1] || items[items.length - 1]).focus(); }
      else if (e.key === "Escape") { e.preventDefault(); close(true); }
      else if (e.key === "Tab") { close(false); }
    });
    add.addEventListener("keydown", function (e) {
      if (e.key === "ArrowDown" && menu.hidden) { e.preventDefault(); add.click(); }
      if (e.key === "Escape") close(false);
    });
    // Close when clicking elsewhere. Options and pills are rebuilt on click, so a click on one that
    // has just been removed from the page is not an "outside" click.
    document.addEventListener("click", function (e) {
      if (e.target.isConnected && !ms.contains(e.target)) close(false);
    });
    inputs.forEach(function (input) { input.addEventListener("change", render); });
    render();
  });

  // Candidate form: show the resume package, number of criteria and preferred times only when the
  // matching service is chosen. Without JavaScript all of them show.
  if (support) {
    var pkgSelect = support.querySelector('select[name="candidate-resume_package"]');
    var syncExtras = function () {
      var chosen = Array.prototype.map.call(support.querySelectorAll('input[name="candidate-support"]:checked'),
        function (i) { return i.value; });
      support.querySelectorAll("[data-support-for]").forEach(function (el) {
        var wanted = el.getAttribute("data-support-for").split(" ");
        var show = wanted.some(function (w) { return chosen.indexOf(w) !== -1; }) ||
          (wanted.indexOf("criteria") !== -1 && chosen.indexOf("resume") !== -1 && pkgSelect && pkgSelect.value === "criteria");
        el.hidden = !show;
      });
    };
    support.addEventListener("change", syncExtras);
    syncExtras();
  }

  // Current opportunities: show the most recent two rows, with "View more roles" for the rest.
  // Without JavaScript every job shows.
  var jobList = document.querySelector("[data-job-list]");
  var jobsToggle = document.querySelector("[data-jobs-toggle]");
  if (jobList && jobsToggle) {
    var jobs = jobList.querySelectorAll(".job");
    var visibleCount = function () {
      return window.matchMedia("(max-width: 640px)").matches ? 3 : window.matchMedia("(max-width: 980px)").matches ? 4 : 6;
    };
    var expanded = false;
    var renderJobs = function () {
      var extra = jobs.length - visibleCount();
      jobsToggle.parentNode.hidden = extra <= 0;
      jobList.classList.toggle("is-collapsed", !expanded && extra > 0);
      jobsToggle.setAttribute("aria-expanded", String(expanded));
      jobsToggle.textContent = expanded ? "Show fewer roles" : "View more roles (" + extra + ")";
    };
    jobsToggle.addEventListener("click", function () {
      expanded = !expanded;
      renderJobs();
      if (expanded) {
        var first = jobs[visibleCount()];
        var link = first && first.querySelector("a");
        if (link) link.focus({ preventScroll: true });
      } else {
        jobList.scrollIntoView({ block: "nearest" });
      }
    });
    window.addEventListener("resize", renderJobs);
    renderJobs();
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
