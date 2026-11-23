/* Admin sidebar: collapse on desktop (remembered), slide in on phones. */
(function () {
  var body = document.body;
  if (!body.classList.contains('sd-shell')) return;
  var KEY = 'sd_admin_collapsed';
  try { if (localStorage.getItem(KEY) === '1') body.classList.add('sd-collapsed'); } catch (e) {}
  var col = document.getElementById('sdcollapse'), bur = document.getElementById('sdburger'), scrim = document.getElementById('sdscrim');
  function closeMobile() { body.classList.remove('sd-open'); if (scrim) scrim.hidden = true; }
  if (col) col.addEventListener('click', function () {
    var on = body.classList.toggle('sd-collapsed');
    try { localStorage.setItem(KEY, on ? '1' : '0'); } catch (e) {}
  });
  if (bur) bur.addEventListener('click', function () { body.classList.add('sd-open'); if (scrim) scrim.hidden = false; });
  if (scrim) scrim.addEventListener('click', closeMobile);
  document.addEventListener('keydown', function (e) { if (e.key === 'Escape') closeMobile(); });
  document.addEventListener('click', function (e) {
    var d = document.querySelector('.sduser[open]');
    if (d && !d.contains(e.target)) d.removeAttribute('open');
  });

  /* ---- Idle sign-out. Activity is shared between all open tabs, so a tab nobody is using can never sign you out
     while you work in another one. Shortly before time runs out a "Stay signed in" notice appears. ---- */
  var idle = parseInt(body.getAttribute('data-idle'), 10) * 1000;
  if (!idle) return;
  var WARN = Math.min(15000, Math.floor(idle / 3));
  var AKEY = 'sd_last_activity';
  var last = Date.now(), lastPing = Date.now(), done = false, warnBox = null;
  function shared() { try { return parseInt(localStorage.getItem(AKEY), 10) || 0; } catch (e) { return 0; } }
  function mark(t) { last = t; try { localStorage.setItem(AKEY, String(t)); } catch (e) {} }
  function lastSeen() { return Math.max(last, shared()); }
  function post(url) {
    return fetch(url, { method: 'POST', credentials: 'same-origin', keepalive: true,
      headers: { 'X-CSRFToken': body.getAttribute('data-csrf') || '' } });
  }
  function hideWarn() { if (warnBox) { warnBox.remove(); warnBox = null; } }
  function expired() {
    if (done) return; done = true; hideWarn();
    post(body.getAttribute('data-expire')).catch(function () {});
    var box = document.createElement('div');
    box.className = 'sdexpired'; box.setAttribute('role', 'alertdialog'); box.setAttribute('aria-modal', 'true');
    box.setAttribute('aria-labelledby', 'sdexp-t');
    box.innerHTML = '<div class="sdexpcard"><span class="sdexpicon" aria-hidden="true">!</span><h2 id="sdexp-t">Session expired</h2>' +
      '<p>For your security you were signed out for inactivity.</p><a class="sdexpbtn" href="' + body.getAttribute('data-login') + '?next=' + encodeURIComponent(location.pathname + location.search) + '">Log in again</a></div>';
    document.body.appendChild(box);
    var b = box.querySelector('a'); if (b) b.focus();
  }
  function ping() {
    lastPing = Date.now();
    post(body.getAttribute('data-ping')).then(function (r) { if (r.status === 401) expired(); }).catch(function () {});
  }
  function stay() { hideWarn(); mark(Date.now()); ping(); }
  function warn(left) {
    if (!warnBox) {
      warnBox = document.createElement('div');
      warnBox.className = 'sdexpired'; warnBox.setAttribute('role', 'alertdialog'); warnBox.setAttribute('aria-modal', 'true');
      warnBox.innerHTML = '<div class="sdexpcard"><span class="sdexpicon" aria-hidden="true">!</span><h2>Still there?</h2>' +
        '<p>You will be signed out in <b id="sdleft"></b> seconds because of inactivity.</p><button type="button" class="sdexpbtn" id="sdstay">Stay signed in</button></div>';
      document.body.appendChild(warnBox);
      document.getElementById('sdstay').addEventListener('click', stay);
      document.getElementById('sdstay').focus();
    }
    document.getElementById('sdleft').textContent = Math.max(1, Math.ceil(left / 1000));
  }
  function active() {
    if (done || warnBox) return;      // while the notice is showing, only its button counts
    var now = Date.now();
    if (now - lastSeen() > idle) { expired(); return; }
    mark(now);
    if (now - lastPing > Math.min(20000, idle / 3)) ping();
  }
  ['mousemove', 'pointermove', 'mousedown', 'click', 'keydown', 'input', 'scroll', 'touchstart', 'touchmove', 'wheel'].forEach(function (ev) {
    window.addEventListener(ev, active, { passive: true, capture: true });
  });
  window.addEventListener('focus', function () { if (!done && Date.now() - lastSeen() <= idle) active(); });
  function check() {
    if (done) return;
    var idleFor = Date.now() - lastSeen();
    if (idleFor > idle) { expired(); return; }
    if (idleFor > idle - WARN) warn(idle - idleFor);
    else if (warnBox) { hideWarn(); }   // another tab saw activity
  }
  document.addEventListener('visibilitychange', function () { if (!document.hidden) check(); });
  setInterval(check, 1000);
  mark(Date.now());
})();
