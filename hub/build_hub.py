"""Сборка каталога агентов из hub/agents.json.

agents.json — источник правды, как kb/manifest.json и news/feed.json
для своих разделов. hub/index.html не правится руками.

Как в новостях, здесь разрешены имена продуктов и ссылки — раздел
справочный, а не учебный.

Запуск из корня воркспейса:
    python hub/build_hub.py
"""

import html
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "kb"))
from sitenav import render_sitenav

AGENTS = os.path.join(BASE, "hub", "agents.json")
OUT = os.path.join(BASE, "hub", "index.html")


def esc(value):
    return html.escape(str(value), quote=True)


def render_card(item):
    tags = "".join(
        '<span class="tag">%s</span>' % esc(t) for t in item.get("tags", [])
    )
    return "\n".join([
        '<li class="card agent-card" data-category="%s">' % esc(item.get("category", "")),
        '<p class="agent-cat">%s</p>' % esc(item.get("category", "")),
        '<p class="agent-name"><a href="%s">%s</a></p>'
        % (esc(item["url"]), esc(item["name"])),
        '<p class="agent-task">%s</p>' % esc(item.get("task", "")),
        '<p class="agent-tags">%s</p>' % tags,
        "</li>",
    ])


def build():
    with open(AGENTS, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    items = sorted(data.get("items", []), key=lambda i: i["name"].lower())
    categories = data.get("categories", [])

    out = []
    add = out.append

    add("<!doctype html>")
    add('<html lang="ru">')
    add("<head>")
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add('<link rel="icon" href="/favicon.ico">')
    add("<title>Хаб агентов — Запуск ИИ-агентов</title>")
    add('<link rel="stylesheet" href="../assets/lesson.css">')
    add('<link rel="stylesheet" href="../assets/hub.css">')
    add("</head>")
    add("<body>")
    add(render_sitenav("hub"))
    add('<article class="sheet wide">')

    add('<header class="masthead">')
    add('<p class="course">Хаб · обновлено <b>%s</b></p>' % esc(data.get("updated", "")))
    add("<h1>Хаб агентов</h1>")
    add(
        '<p class="standfirst">Справочник конкретных инструментов, которые можно '
        "применять: имя, задача, ссылка. Это каталог, а не учебный материал — "
        "здесь, в отличие от уроков, продукты называются напрямую.</p>"
    )
    add("</header>")

    if items:
        if categories:
            add('<div class="agent-filter" role="group" aria-label="Фильтр по категории">')
            add('<button type="button" class="on" data-filter="all">Все</button>')
            for cat in categories:
                add('<button type="button" data-filter="%s">%s</button>' % (esc(cat), esc(cat)))
            add("</div>")
        add('<ul class="agent-grid">')
        for item in items:
            add(render_card(item))
        add("</ul>")
    else:
        add('<div class="feed-empty">')
        add("<p>Каталог пока пуст. Первые записи появятся здесь, как только "
            "наберется первая проверенная подборка инструментов.</p>")
        add("</div>")

    add('<footer class="colophon">')
    add("<nav>")
    add('<a href="/kb/index.html">База знаний</a>')
    add('<a href="/news/index.html">Новости</a>')
    add("</nav>")
    add("</footer>")

    add("</article>")
    if categories:
        add('<script src="../assets/hub.js"></script>')
    add("</body>")
    add("</html>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print("hub/index.html собран: %d записей" % len(items))


if __name__ == "__main__":
    build()
