/* ============================================================
   Курс «Запуск ИИ-агентов» — отметки о пройденном на главной

   Прогресс лежит там же, где его пишут квизы: в localStorage
   браузера, под ключами agents-course:quiz:<код>. Никакого сервера
   и никакого канала наружу — страница просто читает то, что уже
   есть в этом браузере.

   Что делает:
   — помечает пройденные уроки в траектории и в списке материалов;
   — переводит крупную ссылку «продолжить» на первый непройденный урок.

   Если хранилище недоступно или пусто, страница остается ровно такой,
   какой пришла с диска: ссылка ведет на первый урок, отметок нет.
   Ни один элемент содержания от скрипта не зависит.
   ============================================================ */

(function () {
  "use strict";

  var PREFIX = "agents-course:quiz:";

  function answeredCount(key) {
    try {
      var raw = window.localStorage.getItem(PREFIX + key);
      if (!raw) return 0;
      var data = JSON.parse(raw);
      return data && typeof data === "object" ? Object.keys(data).length : 0;
    } catch (e) {
      return 0;
    }
  }

  function boot() {
    var steps = Array.prototype.slice.call(
      document.querySelectorAll("[data-quiz-key]")
    );
    if (!steps.length) return;

    var firstUnfinished = null;

    steps.forEach(function (el) {
      var key = el.getAttribute("data-quiz-key");
      var total = parseInt(el.getAttribute("data-quiz-total") || "0", 10);
      var done = answeredCount(key);
      var complete = total > 0 && done >= total;

      if (complete) {
        el.setAttribute("data-done", "");
        var slot = el.querySelector("[data-done-slot]");
        if (slot) slot.textContent = "пройден";
      } else if (!firstUnfinished) {
        firstUnfinished = { el: el, done: done, total: total };
      }
    });

    var resume = document.querySelector(".resume");
    if (!resume) return;

    if (!firstUnfinished) {
      var last = steps[steps.length - 1];
      setResume(
        resume,
        last.getAttribute("data-href"),
        "Все уроки пройдены",
        last.getAttribute("data-title"),
        "Можно вернуться к любому или ждать следующего."
      );
      return;
    }

    var started = firstUnfinished.done > 0;
    setResume(
      resume,
      firstUnfinished.el.getAttribute("data-href"),
      started ? "Продолжить" : "Дальше по курсу",
      firstUnfinished.el.getAttribute("data-title"),
      started
        ? "Практика начата: отвечено " +
            firstUnfinished.done +
            " из " +
            firstUnfinished.total +
            "."
        : null
    );
  }

  function setResume(node, href, label, title, sub) {
    if (href) node.setAttribute("href", href);

    var lbl = node.querySelector(".lbl");
    var ttl = node.querySelector(".ttl");
    var subEl = node.querySelector(".sub");

    if (lbl && label) lbl.textContent = label;
    if (ttl && title) ttl.textContent = title;
    if (subEl && sub) subEl.textContent = sub;
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
