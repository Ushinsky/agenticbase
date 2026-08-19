/* ============================================================
   Курс «Запуск ИИ-агентов» — отметки о пройденном на главной

   Прогресс — это то, что читатель сам отметил кнопкой в конце
   урока (assets/mark-done.js пишет флаг). Никакого автоматического
   счетчика по квизу: ответил на все вопросы — не значит «понял
   и прошел», это решает сам человек. Ключ в localStorage:
   agents-course:done:<id урока из манифеста>.

   Что делает:
   — помечает пройденные уроки в траектории и в списке материалов;
   — переводит крупную ссылку «продолжить» на первый непройденный урок.

   Если хранилище недоступно или пусто, страница остается ровно такой,
   какой пришла с диска: ссылка ведет на первый урок, отметок нет.
   Ни один элемент содержания от скрипта не зависит.
   ============================================================ */

(function () {
  "use strict";

  var PREFIX = "agents-course:done:";

  function isDone(key) {
    try {
      return window.localStorage.getItem(PREFIX + key) === "1";
    } catch (e) {
      return false;
    }
  }

  function boot() {
    var steps = Array.prototype.slice.call(
      document.querySelectorAll("[data-done-key]")
    );
    if (!steps.length) return;

    var firstUnfinished = null;

    steps.forEach(function (el) {
      var key = el.getAttribute("data-done-key");
      var done = isDone(key);

      if (done) {
        el.setAttribute("data-done", "");
        var slot = el.querySelector("[data-done-slot]");
        if (slot) slot.textContent = "пройден";
      } else if (!firstUnfinished) {
        firstUnfinished = el;
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

    setResume(
      resume,
      firstUnfinished.getAttribute("data-href"),
      "Дальше по курсу",
      firstUnfinished.getAttribute("data-title"),
      null
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
