"""Сборка ленты новостей из news/feed.json.

feed.json — источник правды для этого раздела, как kb/manifest.json —
для базы знаний. news/index.html никогда не правится руками: изменили
feed.json, запустили этот скрипт, получили страницу.

В отличие от уроков и статей, в новостях разрешены имена продуктов
и ссылки на источники — раздел справочный, а не учебный.

Запуск из корня воркспейса:
    python news/build_feed.py
"""

import html
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "kb"))
from sitenav import render_sitenav

FEED = os.path.join(BASE, "news", "feed.json")
OUT = os.path.join(BASE, "news", "index.html")


def esc(value):
    return html.escape(str(value), quote=True)


def render_item(item):
    tags = "".join(
        '<span class="tag">%s</span>' % esc(t) for t in item.get("tags", [])
    )
    return "\n".join([
        '<li class="feed-item">',
        '<p class="feed-date">%s</p>' % esc(item["date"]),
        '<div class="feed-body">',
        '<p class="feed-title">%s</p>' % esc(item["title"]),
        '<p class="feed-sum">%s</p>' % esc(item.get("summary", "")),
        '<p class="feed-meta"><a href="%s">%s</a>%s</p>'
        % (esc(item["url"]), esc(item.get("source", "источник")), tags),
        "</div>",
        "</li>",
    ])


def build():
    with open(FEED, "r", encoding="utf-8") as fh:
        data = json.load(fh)

    items = sorted(data.get("items", []), key=lambda i: i["date"], reverse=True)

    out = []
    add = out.append

    add("<!doctype html>")
    add('<html lang="ru">')
    add("<head>")
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add("<title>Новости — Запуск ИИ-агентов</title>")
    add('<link rel="stylesheet" href="../assets/lesson.css">')
    add('<link rel="stylesheet" href="../assets/news.css">')
    add("</head>")
    add("<body>")
    add(render_sitenav("news"))
    add('<article class="sheet">')

    add('<header class="masthead">')
    add('<p class="course">Новости · обновлено <b>%s</b></p>' % esc(data.get("updated", "")))
    add("<h1>Новости про ИИ-агентов</h1>")
    add(
        '<p class="standfirst">Короткие карточки о том, что происходит в мире '
        "агентов: новые модели, инструменты, протоколы, заметные разборы. "
        "В отличие от уроков, здесь называются конкретные продукты и даются "
        "ссылки на источники.</p>"
    )
    add("</header>")

    if items:
        add('<ul class="feed">')
        for item in items:
            add(render_item(item))
        add("</ul>")
    else:
        add('<div class="feed-empty">')
        add("<p>Пока пусто. Первая запись появится здесь, как только "
            "наберется первая настоящая новость.</p>")
        add("</div>")

    add('<footer class="colophon">')
    add("<nav>")
    add('<a href="/kb/index.html">База знаний</a>')
    add('<a href="/hub/index.html">Хаб агентов</a>')
    add("</nav>")
    add("</footer>")

    add("</article>")
    add("</body>")
    add("</html>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print("news/index.html собран: %d записей" % len(items))


if __name__ == "__main__":
    build()
