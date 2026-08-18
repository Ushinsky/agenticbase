/* ============================================================
   Курс «Запуск ИИ-агентов» — компонент «скопировать блок»

   Разметка:
     <button class="link" data-copy="#tpl">скопировать как markdown</button>
     <pre id="tpl" class="plain">…текст…</pre>

   Кладет текст цели в буфер. Если буфер недоступен — а на file://
   он часто недоступен, — выделяет текст, чтобы скопировать вручную.
   Обе ветки оставляют пользователя с рабочим результатом.
   ============================================================ */

(function () {
  "use strict";

  function flash(btn, text) {
    var original = btn.getAttribute("data-label-original") || btn.textContent;
    btn.setAttribute("data-label-original", original);
    btn.textContent = text;
    window.setTimeout(function () {
      btn.textContent = original;
    }, 2000);
  }

  function selectNode(node) {
    if (!node || !window.getSelection || !document.createRange) return;
    var range = document.createRange();
    range.selectNodeContents(node);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  function init(btn) {
    btn.type = "button";
    btn.addEventListener("click", function () {
      var target = document.querySelector(btn.getAttribute("data-copy"));
      if (!target) return;
      var text = target.textContent;

      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(text).then(
          function () {
            flash(btn, "скопировано");
          },
          function () {
            selectNode(target);
            flash(btn, "выделено — Ctrl+C");
          }
        );
      } else {
        selectNode(target);
        flash(btn, "выделено — Ctrl+C");
      }
    });
  }

  function boot() {
    Array.prototype.forEach.call(document.querySelectorAll("[data-copy]"), init);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
