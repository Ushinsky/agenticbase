/* ============================================================
   Курс «Запуск ИИ-агентов» — компонент «квиз с мгновенным разбором»

   Разметка, которую он ожидает:

   <div class="quiz" data-quiz="0001-a" data-label="Урок 1 · блок A">
     <ol>
       <li class="q" data-answer="no" data-tag="чат-бот">
         <p class="q-stem">Текст вопроса</p>
         <div class="q-opts">
           <button data-v="yes">Агент</button>
           <button data-v="no">Не агент</button>
         </div>
         <div class="q-fb" hidden>
           <p>Разбор — почему так, независимо от того, что выбрали.</p>
         </div>
       </li>
     </ol>
     <div class="quiz-foot">
       <p class="quiz-score" data-score></p>
       <button class="link" data-reset>пройти заново</button>
       <button class="link" data-report>скопировать отчет</button>
     </div>
     <p class="quiz-out" hidden></p>
   </div>

   Обратная связь появляется сразу после ответа: петля должна быть тугой.
   Разбор один на вопрос и не зависит от выбора — цель в том, чтобы ученик
   прочитал объяснение и при верном ответе тоже.

   Прогресс живет в localStorage браузера. Никакого канала наружу нет:
   чтобы преподаватель увидел результат, ученик копирует отчет и вставляет
   его в чат. Это осознанный выбор — честный и работающий без инфраструктуры.
   ============================================================ */

(function () {
  "use strict";

  var VERDICT = { right: "Верно", wrong: "Мимо" };
  var STORE_PREFIX = "agents-course:quiz:";

  function load(key) {
    try {
      var raw = window.localStorage.getItem(STORE_PREFIX + key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function save(key, data) {
    try {
      window.localStorage.setItem(STORE_PREFIX + key, JSON.stringify(data));
    } catch (e) {
      /* приватный режим или переполненное хранилище — молча работаем без памяти */
    }
  }

  function clear(key) {
    try {
      window.localStorage.removeItem(STORE_PREFIX + key);
    } catch (e) {
      /* см. выше */
    }
  }

  function initQuiz(quiz) {
    var storeKey = quiz.getAttribute("data-quiz") || "";
    var label = quiz.getAttribute("data-label") || "квиз";
    var questions = Array.prototype.slice.call(quiz.querySelectorAll(".q"));
    var scoreEl = quiz.querySelector("[data-score]");
    var outEl = quiz.querySelector(".quiz-out");
    var picks = {};

    if (scoreEl) scoreEl.setAttribute("aria-live", "polite");

    function tally() {
      var answered = 0;
      var correct = 0;
      questions.forEach(function (q, i) {
        if (picks[i] === undefined) return;
        answered += 1;
        if (picks[i] === q.getAttribute("data-answer")) correct += 1;
      });
      return { answered: answered, correct: correct, total: questions.length };
    }

    function renderScore() {
      if (!scoreEl) return;
      var t = tally();
      if (t.answered === 0) {
        scoreEl.textContent = "Вопросов: " + t.total;
        return;
      }
      var text =
        "Отвечено " + t.answered + " из " + t.total + " · верно " + t.correct;
      if (t.answered === t.total) {
        text += t.correct === t.total ? " · чисто" : " · разберите промахи выше";
      }
      scoreEl.textContent = text;
    }

    function buildReport() {
      var t = tally();
      var misses = [];
      questions.forEach(function (q, i) {
        if (picks[i] === undefined) return;
        if (picks[i] === q.getAttribute("data-answer")) return;
        var tag = q.getAttribute("data-tag");
        misses.push(tag ? i + 1 + " (" + tag + ")" : String(i + 1));
      });
      var line = label + ": " + t.correct + "/" + t.total;
      if (t.answered < t.total) {
        line += " · отвечено " + t.answered;
      }
      line += misses.length ? " · промахи: " + misses.join(", ") : " · без промахов";
      return line;
    }

    function showReport() {
      var line = buildReport();
      if (outEl) {
        outEl.textContent = line;
        outEl.hidden = false;
      }
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(line).then(
          function () {
            if (outEl) outEl.setAttribute("data-copied", "");
          },
          function () {
            selectText(outEl);
          }
        );
      } else {
        selectText(outEl);
      }
    }

    function selectText(el) {
      if (!el || !window.getSelection || !document.createRange) return;
      var range = document.createRange();
      range.selectNodeContents(el);
      var sel = window.getSelection();
      sel.removeAllRanges();
      sel.addRange(range);
    }

    function applyAnswer(q, index, picked, persist) {
      if (q.hasAttribute("data-done")) return;
      q.setAttribute("data-done", "");

      var expected = q.getAttribute("data-answer");
      var isRight = picked === expected;
      picks[index] = picked;

      Array.prototype.forEach.call(
        q.querySelectorAll(".q-opts button"),
        function (other) {
          other.disabled = true;
          var v = other.getAttribute("data-v");
          if (v === expected) {
            other.setAttribute("data-state", "right");
          } else if (v === picked) {
            other.setAttribute("data-state", "wrong");
          } else {
            other.setAttribute("data-state", "muted");
          }
        }
      );

      var feedback = q.querySelector(".q-fb");
      if (feedback) {
        var verdict = feedback.querySelector(".verdict");
        if (!verdict) {
          verdict = document.createElement("p");
          verdict.className = "verdict";
          feedback.insertBefore(verdict, feedback.firstChild);
        }
        verdict.textContent = isRight ? VERDICT.right : VERDICT.wrong;
        feedback.setAttribute("data-verdict", isRight ? "right" : "wrong");
        feedback.hidden = false;
      }

      renderScore();
      if (persist && storeKey) save(storeKey, picks);
    }

    questions.forEach(function (q, index) {
      Array.prototype.forEach.call(
        q.querySelectorAll(".q-opts button"),
        function (btn) {
          btn.type = "button";
          btn.addEventListener("click", function () {
            applyAnswer(q, index, btn.getAttribute("data-v"), true);
          });
        }
      );
    });

    function reset() {
      picks = {};
      if (storeKey) clear(storeKey);
      questions.forEach(function (q) {
        q.removeAttribute("data-done");
        Array.prototype.forEach.call(
          q.querySelectorAll(".q-opts button"),
          function (btn) {
            btn.disabled = false;
            btn.removeAttribute("data-state");
          }
        );
        var feedback = q.querySelector(".q-fb");
        if (feedback) {
          feedback.hidden = true;
          feedback.removeAttribute("data-verdict");
          var verdict = feedback.querySelector(".verdict");
          if (verdict) verdict.remove();
        }
      });
      if (outEl) {
        outEl.hidden = true;
        outEl.removeAttribute("data-copied");
        outEl.textContent = "";
      }
      renderScore();
      var first = quiz.querySelector(".q-opts button");
      if (first) first.focus();
    }

    var resetBtn = quiz.querySelector("[data-reset]");
    if (resetBtn) {
      resetBtn.type = "button";
      resetBtn.addEventListener("click", reset);
    }

    var reportBtn = quiz.querySelector("[data-report]");
    if (reportBtn) {
      reportBtn.type = "button";
      reportBtn.addEventListener("click", showReport);
    }

    // восстановление прошлого захода
    var saved = storeKey ? load(storeKey) : null;
    if (saved) {
      questions.forEach(function (q, index) {
        if (saved[index] !== undefined) applyAnswer(q, index, saved[index], false);
      });
    }

    renderScore();
  }

  function boot() {
    Array.prototype.forEach.call(
      document.querySelectorAll("[data-quiz]"),
      initQuiz
    );
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
