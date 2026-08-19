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


ICON_KB = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"><rect x="4" y="4" width="16" '
    'height="16" rx="3"/></svg>'
)
ICON_HUB = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="8"/></svg>'
)
ICON_NEWS = (
    '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" '
    'stroke-linecap="round" stroke-linejoin="round"><path d="M4 7h16M4 12h16M4 17h10"/></svg>'
)


def build():
    manifest = load("kb/manifest.json") or {"nodes": [], "course": {"title": "Запуск ИИ-агентов"}, "modules": []}
    feed = load("news/feed.json") or {"items": []}
    hub = load("hub/agents.json") or {"items": []}

    nodes = manifest["nodes"]
    modules = manifest.get("modules", [])
    lesson_count = sum(1 for n in nodes if n.get("type") == "lesson")
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
    add('<link rel="stylesheet" href="assets/portal.css">')
    add("</head>")
    add("<body>")
    add(render_sitenav(None))
    add('<main class="portal-shell">')

    # ---------- герой ----------
    add('<section class="portal-hero">')
    add("<h1>Стройте и поддерживайте ИИ-агентов, которые работают в продакшене</h1>")
    add(
        '<p class="lede">Практический курс: от первого прототипа до агента, '
        "обслуживающего реального заказчика. Без привязки к одной платформе — "
        "только рабочие принципы и инструменты.</p>"
    )
    add("</section>")

    # ---------- три раздела ----------
    add('<div class="portal-grid">')

    add('<a class="card portal-card" href="kb/index.html">')
    add('<div class="portal-head">')
    add('<span class="portal-icon" aria-hidden="true">%s</span>' % ICON_KB)
    add('<p class="portal-ttl">База знаний</p>')
    add("</div>")
    add(
        '<p class="portal-sub">Пошаговые уроки о проектировании, разработке '
        "и эксплуатации агентов, сгруппированные по модулям.</p>"
    )
    add('<div class="portal-foot">')
    add('<span class="portal-meta">%d модулей · %d уроков</span>' % (len(modules), lesson_count))
    add('<span class="portal-cta">Перейти →</span>')
    add("</div>")
    add("</a>")

    add('<a class="card portal-card" href="hub/index.html">')
    add('<div class="portal-head">')
    add('<span class="portal-icon" aria-hidden="true">%s</span>' % ICON_HUB)
    add('<p class="portal-ttl">Хаб агентов</p>')
    add("</div>")
    add(
        '<p class="portal-sub">Справочник платформ и агентов, которые реально '
        "используются в проектах, с фильтром по категориям.</p>"
    )
    add('<div class="portal-foot">')
    if hub_items:
        add('<span class="portal-meta">%d инструментов</span>' % len(hub_items))
    else:
        add('<span class="portal-meta">Каталог пока пуст</span>')
    add('<span class="portal-cta">Перейти →</span>')
    add("</div>")
    add("</a>")

    add('<a class="card portal-card" href="news/index.html">')
    add('<div class="portal-head">')
    add('<span class="portal-icon" aria-hidden="true">%s</span>' % ICON_NEWS)
    add('<p class="portal-ttl">Новости</p>')
    add("</div>")
    add(
        '<p class="portal-sub">Короткие карточки о том, что меняется '
        "в индустрии ИИ-агентов, со ссылкой на источник.</p>"
    )
    add('<div class="portal-foot">')
    add('<span class="portal-meta">Обновляется еженедельно</span>')
    add('<span class="portal-cta">Перейти →</span>')
    add("</div>")
    add("</a>")

    add("</div>")

    add("</main>")
    add("</body>")
    add("</html>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print("index.html (портал) собран")


if __name__ == "__main__":
    build()
