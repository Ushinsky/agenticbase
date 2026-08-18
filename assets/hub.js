/* ============================================================
   Хаб агентов — фильтр по категории, без сети и без сборки.
   Кнопка задает data-filter, карточки скрываются по data-category.
   ============================================================ */

(function () {
  "use strict";

  function boot() {
    var buttons = Array.prototype.slice.call(
      document.querySelectorAll(".agent-filter button")
    );
    var cards = Array.prototype.slice.call(
      document.querySelectorAll(".agent-card")
    );
    if (!buttons.length || !cards.length) return;

    buttons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        buttons.forEach(function (b) { b.classList.remove("on"); });
        btn.classList.add("on");
        var filter = btn.getAttribute("data-filter");
        cards.forEach(function (card) {
          var show = filter === "all" || card.getAttribute("data-category") === filter;
          if (show) card.removeAttribute("hidden");
          else card.setAttribute("hidden", "");
        });
      });
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
