"""Общая шапка сайта — одна разметка на все три раздела.

Используется всеми генераторами (kb/build_index.py, news/build_feed.py,
hub/build_hub.py, build_portal.py), чтобы шапка была идентична везде.
Правится один раз здесь, а не в четырех шаблонах.
"""

SECTIONS = {
    "kb": ("/kb/index.html", "База знаний"),
    "news": ("/news/index.html", "Лента"),
}


def render_sitenav(active=None):
    links = []
    for key, (href, title) in SECTIONS.items():
        cls = ' class="on"' if key == active else ""
        links.append(f'<a href="{href}"{cls}>{title}</a>')
    links_html = "\n      ".join(links)
    return f"""<nav class="sitenav">
  <a class="sitenav-mark" href="/">
    <img class="brand-icon" src="/assets/brand/mark.png" alt="">
    <img class="brand-word" src="/assets/brand/wordmark.png" alt="AgenticBase">
    <img class="brand-mascot" src="/assets/brand/octopus.png" alt="">
  </a>
  <div class="sitenav-links">
      {links_html}
  </div>
</nav>
"""
