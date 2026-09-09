"""Общая шапка сайта — одна разметка на все три раздела.

Используется всеми генераторами (kb/build_index.py, news/build_feed.py,
hub/build_hub.py, build_portal.py), чтобы шапка была идентична везде.
Правится один раз здесь, а не в четырех шаблонах.

Здесь же asset_url() — общий помощник против кеша, см. его докстринг.
"""

import hashlib
import os

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

_HASHES = {}


def asset_url(path):
    """Ссылка на файл в /assets/ с отпечатком содержимого: /assets/news.css?v=1a2b3c4d

    Зачем. Beget отдает статику с Cache-Control: max-age=604800 — неделя.
    Без отпечатка правка стилей доходит до вернувшегося читателя через семь
    дней, и все это время он видит новую разметку со старым оформлением.
    Проявилось наглядно: иконки типов без своих правил рисовались размером
    по умолчанию, 300 на 150 пикселей.

    Отпечаток считается от содержимого, поэтому меняется ровно тогда, когда
    файл действительно изменился, и не трогает кеш при простой пересборке.

    path пишется так же, как в разметке страницы, — генераторы ссылаются на
    статику по-разному: "/assets/news.css", "assets/portal.css",
    "../assets/home.css". Ведущие "/" и "../" отбрасываются только для поиска
    файла на диске, в готовую ссылку путь возвращается неизменным.
    """
    if path in _HASHES:
        return _HASHES[path]
    relative = path.lstrip("/")
    while relative.startswith("../"):
        relative = relative[3:]
    full = os.path.join(BASE, relative.replace("/", os.sep))
    if not os.path.exists(full):
        _HASHES[path] = path
        return path
    with open(full, "rb") as fh:
        digest = hashlib.sha1(fh.read()).hexdigest()[:8]
    _HASHES[path] = "%s?v=%s" % (path, digest)
    return _HASHES[path]


SECTIONS = {
    "kb": ("/kb/", "База знаний"),
    "news": ("/news/", "Лента"),
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
