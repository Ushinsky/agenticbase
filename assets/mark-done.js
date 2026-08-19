/* ============================================================
   Кнопка «Отметить урок пройденным» в конце страницы урока.

   Читатель сам решает, пройден урок или нет, — это не выводится
   из ответов на квиз. Флаг лежит в localStorage под тем же ключом,
   что читает assets/progress.js на главной: agents-course:done:<id>.
   Повторный клик снимает отметку — на случай, если нажали случайно
   или решили пройти урок заново.
   ============================================================ */

(function () {
  "use strict";

  var PREFIX = "agents-course:done:";

  function boot() {
    var btn = document.querySelector("[data-mark-done]");
    if (!btn) return;

    var key = btn.getAttribute("data-mark-done");

    function render(done) {
      btn.classList.toggle("is-done", done);
      btn.textContent = done ? "✓ Урок отмечен пройденным" : "Отметить урок пройденным";
    }

    var done = false;
    try {
      done = window.localStorage.getItem(PREFIX + key) === "1";
    } catch (e) {}
    render(done);

    btn.addEventListener("click", function () {
      done = !done;
      try {
        if (done) window.localStorage.setItem(PREFIX + key, "1");
        else window.localStorage.removeItem(PREFIX + key);
      } catch (e) {}
      render(done);
    });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
