/* ============================================================
   Курс «Запуск ИИ-агентов» — якорное меню и кнопка «наверх»

   Ничего не требует от разметки: меню собирается из разделов
   <section> с заголовком <h2>. Номер берется из .num, если он есть,
   иначе проставляется по порядку. Каждому разделу выдается id,
   если его не задали руками.

   Подсветка текущего раздела — по видимой части страницы, без
   дерганья: активным считается последний раздел, чей заголовок
   прошел верхнюю треть окна.
   ============================================================ */

(function () {
  "use strict";

  function slug(text, index) {
    var base = text
      .toLowerCase()
      .replace(/[^a-zа-я0-9]+/gi, "-")
      .replace(/^-+|-+$/g, "");
    return base ? "r-" + base.slice(0, 40) : "r-" + index;
  }

  function collect() {
    var out = [];
    Array.prototype.forEach.call(
      document.querySelectorAll(".sheet > section"),
      function (section, i) {
        var h = section.querySelector("h2");
        if (!h) return;
        if (!section.id) section.id = slug(h.textContent || "", i);
        var numEl = section.querySelector(".num");
        out.push({
          id: section.id,
          num: numEl ? numEl.textContent.trim() : String(i + 1),
          title: (h.textContent || "").trim(),
          el: section
        });
      }
    );
    return out;
  }

  function buildRail() {
    var rail = document.createElement("div");
    rail.className = "pagerail";
    document.body.appendChild(rail);
    return rail;
  }

  function buildNav(items, rail) {
    var nav = document.createElement("nav");
    nav.className = "pagenav";
    nav.setAttribute("aria-label", "Разделы страницы");

    var ol = document.createElement("ol");
    items.forEach(function (item) {
      var li = document.createElement("li");
      var a = document.createElement("a");
      a.href = "#" + item.id;

      var n = document.createElement("span");
      n.className = "n";
      n.textContent = item.num;

      var t = document.createElement("span");
      t.className = "t";
      t.textContent = item.title;

      a.appendChild(n);
      a.appendChild(t);
      li.appendChild(a);
      ol.appendChild(li);
      item.link = a;
    });

    nav.appendChild(ol);
    rail.appendChild(nav);
    return nav;
  }

  var ARROW =
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" ' +
    'stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" ' +
    'aria-hidden="true"><path d="M12 19V5"/><path d="M5 12l7-7 7 7"/></svg>';

  function buildTopButton(rail) {
    var btn = document.createElement("button");
    btn.type = "button";
    btn.className = "to-top";
    btn.title = "Наверх";
    btn.setAttribute("aria-label", "Наверх");
    btn.innerHTML = ARROW;
    btn.addEventListener("click", function () {
      window.scrollTo({ top: 0, behavior: "smooth" });
      var first = document.querySelector(".masthead h1");
      if (first) {
        first.setAttribute("tabindex", "-1");
        first.focus({ preventScroll: true });
      }
    });
    rail.appendChild(btn);
    return btn;
  }

  function boot() {
    var items = collect();
    var rail = buildRail();
    if (items.length > 1) buildNav(items, rail);
    buildTopButton(rail);

    var timer = null;

    function update() {
      timer = null;
      if (!items.length || !items[0].link) return;
      var line = window.innerHeight / 3;
      var active = items[0];
      items.forEach(function (item) {
        if (item.el.getBoundingClientRect().top <= line) active = item;
      });
      items.forEach(function (item) {
        if (item.link) {
          if (item === active) item.link.setAttribute("aria-current", "true");
          else item.link.removeAttribute("aria-current");
        }
      });
    }

    /* Троттлинг таймером, а не кадром отрисовки: requestAnimationFrame
       не срабатывает в фоновой вкладке и в скрытом окне, и тогда подсветка
       раздела молча перестает обновляться. */
    function schedule() {
      if (timer !== null) return;
      timer = window.setTimeout(update, 16);
    }

    window.addEventListener("scroll", schedule, { passive: true });
    window.addEventListener("resize", schedule, { passive: true });
    update();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
