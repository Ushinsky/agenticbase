"""Сборка главной страницы базы знаний из манифеста.

Манифест — источник правды. index.html никогда не правится руками:
поменяли kb/manifest.json, запустили этот скрипт, получили страницу.

Отметка «пройден» — не автоматическая: читатель ставит ее сам кнопкой
в конце урока (assets/mark-done.js), сборка только готовит атрибут
data-done-key, по которому эта отметка потом ищется в localStorage.

Запуск из корня воркспейса:
    python kb/build_index.py
"""

import html
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "kb"))
from sitenav import render_sitenav

MANIFEST = os.path.join(BASE, "kb", "manifest.json")
OUT = os.path.join(BASE, "kb", "index.html")

KIND = {
    "lesson": "урок",
    "article": "статья",
    "reference": "рабочий лист",
    "index": "навигация",
}

STATUS = {
    "published": "готово",
    "draft": "черновик",
    "planned": "в плане",
}


def esc(value):
    return html.escape(str(value), quote=True)


def href_of(node):
    # index.html теперь лежит в kb/, на уровень глубже lessons/articles/reference,
    # поэтому все пути из манифеста получают "../".
    path = node.get("path")
    return "../" + path.replace("\\", "/") if path else None


def render_material(node):
    link = href_of(node)
    status = node.get("status", "planned")
    title = esc(node["title"])

    head = (
        '<a href="%s">%s</a>' % (esc(link), title)
        if link
        else '<span class="pending">%s</span>' % title
    )

    done_slot = ""
    attrs = ""
    if node.get("type") == "lesson" and link:
        attrs = ' data-done-key="%s"' % esc(node["id"])
        done_slot = ' <span class="done" data-done-slot></span>'

    return "\n".join([
        '<li data-status="%s"%s>' % (esc(status), attrs),
        '<p class="mat-kind">%s · %s</p>'
        % (esc(KIND.get(node.get("type"), "")), esc(STATUS.get(status, status))),
        '<div class="mat-body">',
        '<p class="mat-title">%s%s</p>' % (head, done_slot),
        '<p class="mat-sum">%s</p>' % esc(node.get("summary", "")),
        "</div>",
        "</li>",
    ])


def build():
    with open(MANIFEST, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    nodes = data["nodes"]
    modules = data["modules"]
    course = data["course"]

    def sort_key(node):
        return (node.get("order", 99), node["title"])

    by_module = {}
    for module in modules:
        picked = [n for n in nodes if n.get("module") == module["id"]]
        by_module[module["id"]] = sorted(picked, key=sort_key)

    lessons = sorted(
        [n for n in nodes if n.get("type") == "lesson" and n.get("status") == "published"],
        key=lambda n: (n.get("path") or ""),
    )
    sheets = [
        n for n in nodes
        if n.get("type") == "reference" and n.get("status") == "published"
    ]

    modorder = {m["id"]: m["num"] for m in modules}
    articles = sorted(
        [n for n in nodes
         if n.get("type") == "article" and n.get("status") == "published"],
        key=lambda n: (modorder.get(n.get("module"), 99), n.get("order", 99)),
    )

    total = len(nodes)
    done = sum(1 for n in nodes if n.get("status") == "published")
    concepts = len({c for n in nodes for c in n.get("concepts", [])})

    out = []
    add = out.append

    add("<!doctype html>")
    add('<html lang="ru">')
    add("<head>")
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add("<title>%s</title>" % esc(course["title"]))
    add('<link rel="stylesheet" href="../assets/lesson.css">')
    add('<link rel="stylesheet" href="../assets/home.css">')
    add("</head>")
    add("<body>")
    add(render_sitenav("kb"))
    add('<article class="sheet wide">')

    # ---------- шапка ----------
    add('<header class="masthead home-hero">')
    add('<p class="course">База знаний · обновлено <b>%s</b></p>' % esc(data["updated"]))
    add("<h1>%s</h1>" % esc(course["title"]))
    add(
        '<p class="tagline">Путь от «что такое агент» до «развернул, поддерживаю '
        "и масштабирую» — уроки с практикой, статьи по каждой теме и рабочие листы, "
        "к которым возвращаются.</p>"
    )

    first = lessons[0] if lessons else None
    add(
        '<a class="resume" href="%s">' % esc(href_of(first) if first else "#")
    )
    add('<span class="lbl">Начать здесь</span>')
    add('<span class="ttl">%s</span>' % esc(first["title"] if first else "Курс готовится"))
    add(
        '<span class="sub">%s</span>'
        % esc(first["summary"] if first else "")
    )
    add("</a>")

    # полоса состояния: по штриху на материал, сгруппировано по разделам
    add('<div class="strip" role="img" aria-label="Состояние программы: %d материалов из %d готово">' % (done, total))
    for module in modules:
        items = by_module[module["id"]]
        if not items:
            continue
        add('<span class="grp">')
        for n in items:
            add('<i data-s="%s"></i>' % esc(n.get("status", "planned")))
        add("</span>")
    add("</div>")
    add(
        '<p class="strip-legend"><b>%d</b> материалов готово из <b>%d</b> · '
        "<b>%d</b> разделов · <b>%d</b> понятий в базе</p>"
        % (done, total, len(modules), concepts)
    )
    add("</header>")

    # ---------- траектория ----------
    add('<section id="put">')
    add('<span class="num" aria-hidden="true">→</span>')
    add("<h2>Путь</h2>")
    add(
        "<p>Уроки идут подряд и опираются друг на друга: каждый следующий "
        "пользуется языком предыдущего. Статьи внутри модуля читаются не "
        "по порядку, а по надобности; рабочие листы не читают, а берут "
        "с собой. Отметку о прохождении урока ставит сам читатель — "
        "кнопкой в конце урока.</p>"
    )

    # Первый готовый урок все еще нужен скрипту для ссылки "Продолжить" —
    # это отдельный элемент вне сетки, скрипт находит его по классу .resume.

    add('<div class="lesson-modules">')
    for module in modules:
        mod_lessons = [n for n in lessons if n.get("module") == module["id"]]
        mod_articles = [n for n in articles if n.get("module") == module["id"]]
        mod_sheets = [n for n in sheets if n.get("module") == module["id"]]
        if not mod_lessons and not mod_articles and not mod_sheets:
            continue

        add('<div class="lesson-module">')
        add('<div class="lesson-module-head">')
        add('<h3>Модуль %d · %s</h3>' % (module["num"], esc(module["title"])))
        if mod_lessons:
            add(
                '<span class="lesson-module-count" data-module-count '
                'data-module-total="%d">0 / %d пройдено</span>'
                % (len(mod_lessons), len(mod_lessons))
            )
        add("</div>")

        if mod_lessons:
            add('<p class="group-label">Уроки</p>')
            add('<ul class="lesson-grid">')
            for n in mod_lessons:
                link = href_of(n)
                add(
                    '<li class="card lesson-card" data-done-key="%s" '
                    'data-href="%s" data-title="%s">'
                    % (esc(n["id"]), esc(link), esc(n["title"]))
                )
                add('<span class="lesson-check" data-done-mark aria-hidden="true"></span>')
                add('<p class="lesson-title"><a href="%s">%s</a></p>' % (esc(link), esc(n["title"])))
                add('<p class="lesson-sum">%s</p>' % esc(n.get("summary", "")))
                add("</li>")
            add("</ul>")

        if mod_articles:
            add('<p class="group-label">Статьи</p>')
            add('<ul class="article-grid">')
            for n in mod_articles:
                link = href_of(n)
                add('<li class="card article-card">')
                add('<span class="genre-mark" aria-hidden="true">&para;</span>')
                add('<div class="body">')
                add('<p class="lesson-title"><a href="%s">%s</a></p>' % (esc(link), esc(n["title"])))
                add('<p class="lesson-sum">%s</p>' % esc(n.get("summary", "")))
                add("</div>")
                add("</li>")
            add("</ul>")

        if mod_sheets:
            add('<p class="group-label">Рабочие листы</p>')
            add('<ul class="sheet-tags">')
            for n in mod_sheets:
                link = href_of(n)
                add('<li class="sheet-tag">')
                add('<a href="%s"><span class="genre-mark-sm" aria-hidden="true">&sect;</span>%s</a>' % (esc(link), esc(n["title"])))
                add("</li>")
            add("</ul>")

        add("</div>")
    add("</div>")

    add(
        "<p>Дальше по пути — механика агента: инструменты, память, знания. "
        "Порядок можно менять: скажите, какая тема нужна раньше, и она "
        "поднимется в очереди.</p>"
    )
    add("</section>")

    # ---------- программа ----------
    for module in modules:
        items = by_module[module["id"]]
        if not items:
            continue
        ready = sum(1 for n in items if n.get("status") == "published")
        add('<section id="m-%s">' % esc(module["id"]))
        add('<span class="num" aria-hidden="true">%d</span>' % module["num"])
        add("<h2>%s</h2>" % esc(module["title"]))
        add(
            '<p class="mod-sum">%s <span class="mod-count">%d из %d готово</span></p>'
            % (esc(module["summary"]), ready, len(items))
        )
        add('<ul class="mats">')
        for n in items:
            add(render_material(n))
        add("</ul>")
        add("</section>")

    add('<footer class="colophon">')
    add("<nav>")
    add('<a href="../GLOSSARY.md">Глоссарий</a>')
    add('<a href="../MISSION.md">Миссия</a>')
    add('<a href="manifest.json">Манифест</a>')
    add("</nav>")
    add(
        '<p class="ask">Серым отмечено то, что еще не написано. Отметки '
        "о пройденном хранятся в этом браузере и никуда не отправляются — "
        "чтобы я увидел результат, пришлите отчет из урока в чат.</p>"
    )
    add("</footer>")

    add("</article>")
    add('<script src="../assets/progress.js"></script>')
    add("</body>")
    add("</html>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print(
        "kb/index.html собран: %d материалов (%d готово), %d разделов, "
        "%d уроков в пути, %d понятий"
        % (total, done, len(modules), len(lessons), concepts)
    )


if __name__ == "__main__":
    build()
