"""Общая шапка сайта — одна разметка на все три раздела.

Используется всеми генераторами (kb/build_index.py, news/build_feed.py,
hub/build_hub.py, build_portal.py), чтобы шапка была идентична везде.
Правится один раз здесь, а не в четырех шаблонах.
"""

SECTIONS = {
    "kb": ("/kb/index.html", "База знаний"),
    "news": ("/news/index.html", "Новости"),
    "hub": ("/hub/index.html", "Хаб агентов"),
}


def render_sitenav(active=None):
    links = []
    for key, (href, title) in SECTIONS.items():
        cls = ' class="on"' if key == active else ""
        links.append(f'<a href="{href}"{cls}>{title}</a>')
    links_html = "\n      ".join(links)
    return f"""<nav class="sitenav">
  <a class="sitenav-mark" href="/">Запуск ИИ-агентов</a>
  <div class="sitenav-links">
      {links_html}
  </div>
</nav>
"""
