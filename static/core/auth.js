(function () {
  // Show / hide password buttons: every .authpw box holds one password input and one eye button.
  document.querySelectorAll('.authpw').forEach(function (box) {
    var btn = box.querySelector('.authpweye'), input = box.querySelector('input');
    if (!btn || !input) return;
    btn.addEventListener('click', function () {
      var show = input.type === 'password';
      input.type = show ? 'text' : 'password';
      btn.setAttribute('aria-pressed', show ? 'true' : 'false');
      btn.setAttribute('aria-label', show ? 'Hide password' : 'Show password');
    });
  });
})();
