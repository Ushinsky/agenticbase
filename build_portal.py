"""Сборка портальной главной страницы (корневой index.html).

Собирает превью из трех разделов: kb/manifest.json, news/feed.json,
hub/agents.json. Сама ничего не решает — только показывает, что уже
собрано их собственными скриптами. Запускать после них:

    python kb/build_index.py
    python news/build_feed.py
    python hub/build_hub.py
    python build_portal.py

Или все разом — build.py.
"""

import html
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "kb"))
from sitenav import render_sitenav

OUT = os.path.join(BASE, "index.html")


def esc(value):
    return html.escape(str(value), quote=True)


def load(path):
    full = os.path.join(BASE, path)
    if not os.path.exists(full):
        return None
    with open(full, "r", encoding="utf-8") as fh:
        return json.load(fh)


def build():
    manifest = load("kb/manifest.json") or {"nodes": [], "course": {"title": "Запуск ИИ-агентов"}}
    feed = load("news/feed.json") or {"items": []}
    hub = load("hub/agents.json") or {"items": []}

    nodes = manifest["nodes"]
    total = len(nodes)
    done = sum(1 for n in nodes if n.get("status") == "published")

    lessons = sorted(
        [n for n in nodes if n.get("type") == "lesson" and n.get("status") == "published"],
        key=lambda n: (n.get("path") or ""),
    )
    first = lessons[0] if lessons else None

    news_items = sorted(feed.get("items", []), key=lambda i: i["date"], reverse=True)[:3]
    hub_items = hub.get("items", [])

    out = []
    add = out.append

    add("<!doctype html>")
    add('<html lang="ru">')
    add("<head>")
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add("<title>%s</title>" % esc(manifest["course"]["title"]))
    add('<link rel="stylesheet" href="assets/lesson.css">')
    add('<link rel="stylesheet" href="assets/home.css">')
    add('<link rel="stylesheet" href="assets/portal.css">')
    add("</head>")
    add("<body>")
    add(render_sitenav(None))
    add('<article class="sheet">')

    add('<header class="masthead home-hero">')
    add("<h1>%s</h1>" % esc(manifest["course"]["title"]))
    add(
        '<p class="tagline">Учебная база, новости по теме и справочник инструментов '
        "в одном месте — три разных способа читать один и тот же предмет.</p>"
    )
    add("</header>")

    add('<div class="portal-grid">')

    # ---------- база знаний ----------
    add('<a class="portal-card" href="kb/index.html">')
    add('<p class="portal-kind">База знаний</p>')
    add('<p class="portal-ttl">%s</p>' % esc(first["title"] if first else "Курс готовится"))
    add(
        '<p class="portal-sub">%d материалов готово из %d. Уроки с практикой, '
        "статьи и рабочие листы.</p>" % (done, total)
    )
    add('<span class="portal-cta">Продолжить обучение →</span>')
    add("</a>")

    # ---------- новости ----------
    add('<a class="portal-card" href="news/index.html">')
    add('<p class="portal-kind">Новости</p>')
    if news_items:
        add('<p class="portal-ttl">%s</p>' % esc(news_items[0]["title"]))
        add('<ul class="portal-list">')
        for item in news_items[1:]:
            add('<li>%s</li>' % esc(item["title"]))
        add("</ul>")
    else:
        add('<p class="portal-ttl">Пока пусто</p>')
        add('<p class="portal-sub">Первая запись появится, как только наберется первая настоящая новость.</p>')
    add('<span class="portal-cta">Все новости →</span>')
    add("</a>")

    # ---------- хаб ----------
    add('<a class="portal-card" href="hub/index.html">')
    add('<p class="portal-kind">Хаб агентов</p>')
    if hub_items:
        add('<p class="portal-ttl">%d инструментов в каталоге</p>' % len(hub_items))
        add('<ul class="portal-list">')
        for item in hub_items[:3]:
            add('<li>%s</li>' % esc(item["name"]))
        add("</ul>")
    else:
        add('<p class="portal-ttl">Каталог пока пуст</p>')
        add('<p class="portal-sub">Справочник конкретных агентов появится здесь по мере отбора.</p>')
    add('<span class="portal-cta">Открыть каталог →</span>')
    add("</a>")

    add("</div>")

    add('<footer class="colophon">')
    add("<nav>")
    add('<a href="GLOSSARY.md">Глоссарий</a>')
    add('<a href="MISSION.md">Миссия</a>')
    add("</nav>")
    add("</footer>")

    add("</article>")
    add("</body>")
    add("</html>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print("index.html (портал) собран")


if __name__ == "__main__":
    build()
