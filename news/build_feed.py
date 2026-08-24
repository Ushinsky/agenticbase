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
from datetime import datetime
from urllib.parse import urlparse

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "kb"))
from sitenav import render_sitenav

FEED = os.path.join(BASE, "news", "feed.json")
OUT = os.path.join(BASE, "news", "index.html")

MONTHS = ["янв", "фев", "мар", "апр", "май", "июн",
          "июл", "авг", "сен", "окт", "ноя", "дек"]


def esc(value):
    return html.escape(str(value), quote=True)


def format_date(date_str):
    dt = datetime.strptime(date_str, "%Y-%m-%d")
    return "%d %s %d" % (dt.day, MONTHS[dt.month - 1], dt.year)


def domain_of(url):
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def render_item(item):
    url = item.get("url", "")
    label = domain_of(url) or item.get("source") or "источник"
    return "\n".join([
        '<a class="feed-item" href="%s">' % esc(url),
        '<p class="feed-date">%s</p>' % esc(format_date(item["date"])),
        '<div class="feed-body">',
        '<p class="feed-title">%s</p>' % esc(item["title"]),
        '<p class="feed-sum">%s</p>' % esc(item.get("summary", "")),
        "</div>",
        '<p class="feed-meta">%s &rarr;</p>' % esc(label),
        "</a>",
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
    add('<link rel="icon" href="/favicon.ico">')
    add("<title>Лента — Запуск ИИ-агентов</title>")
    add('<link rel="stylesheet" href="../assets/lesson.css">')
    add('<link rel="stylesheet" href="../assets/news.css">')
    add("</head>")
    add("<body>")
    add(render_sitenav("news"))
    add('<article class="sheet wide">')
    add('<div class="news-hero">')
    add('<div class="feed-page">')

    add('<header class="feed-head">')
    add("<h1>Лента</h1>")
    add(
        '<p class="feed-lede">Что меняется в индустрии ИИ-агентов — коротко, '
        "по датам, со ссылкой на источник.</p>"
    )
    add("</header>")

    if items:
        add('<div class="feed">')
        for item in items:
            add(render_item(item))
        add("</div>")
    else:
        add('<div class="feed-empty">')
        add("<p>Пока пусто. Первая запись появится здесь, как только "
            "наберется первая настоящая новость.</p>")
        add("</div>")

    add("</div>")
    add('<img class="news-mascot" src="../assets/brand/news-octopus.png" alt="">')
    add("</div>")

    add('<footer class="colophon">')
    add("<nav>")
    add('<a href="/kb/index.html">База знаний</a>')
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
