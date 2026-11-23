// Quick date ranges on the Reports page: fill the From and To boxes.
(function () {
  var form = document.getElementById('reportform');
  if (!form) return;
  var from = form.elements.date_from, to = form.elements.date_to;
  function iso(d) { return d.getFullYear() + '-' + String(d.getMonth() + 1).padStart(2, '0') + '-' + String(d.getDate()).padStart(2, '0'); }
  form.querySelectorAll('[data-range]').forEach(function (b) {
    b.addEventListener('click', function () {
      var now = new Date(), a = null, z = null, r = b.getAttribute('data-range');
      if (r === 'month') { a = new Date(now.getFullYear(), now.getMonth(), 1); z = now; }
      else if (r === 'lastmonth') { a = new Date(now.getFullYear(), now.getMonth() - 1, 1); z = new Date(now.getFullYear(), now.getMonth(), 0); }
      else if (r === '30') { a = new Date(now.getFullYear(), now.getMonth(), now.getDate() - 29); z = now; }
      else if (r === 'year') { a = new Date(now.getFullYear(), 0, 1); z = now; }
      from.value = a ? iso(a) : '';
      to.value = z ? iso(z) : '';
      form.querySelectorAll('[data-range]').forEach(function (o) { o.classList.toggle('on', o === b); });
    });
  });
})();
