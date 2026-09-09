"""Сборка Ленты — еженедельного дайджеста ИИ-агентов.

Источник данных — news/digest.json, который собирает news/publish.py в конце
конвейера (collect -> filter -> classify -> score -> write -> publish). Прежний
внешний проект дайджеста, из которого снимок приходил раньше, больше не
существует. Здесь только рендер — три вида страниц:

    news/index.html          — текущая (незакрытая) неделя
    news/archive/index.html  — архив закрытых недель по месяцам
    news/weeks/<label>.html  — неизменяемая страница одной закрытой недели

В отличие от уроков и статей, в Ленте разрешены имена продуктов и ссылки
на источники — раздел справочный, а не учебный.

Все ссылки на CSS/JS/картинки в этом разделе — абсолютные (/assets/...),
не относительные: страницы лежат на разной глубине (news/, news/weeks/,
news/archive/), а сайт всегда открывается от корня домена.

Запуск из корня воркспейса:
    python news/build_feed.py
"""

import html
import json
import os
import sys
from datetime import datetime

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(BASE, "kb"))
from sitenav import render_sitenav

DIGEST = os.path.join(BASE, "news", "digest.json")
OUT_INDEX = os.path.join(BASE, "news", "index.html")
OUT_ARCHIVE = os.path.join(BASE, "news", "archive", "index.html")
NEWS_DIR = os.path.join(BASE, "news")

MONTHS_RU = [
    "января", "февраля", "марта", "апреля", "мая", "июня",
    "июля", "августа", "сентября", "октября", "ноября", "декабря",
]
MONTHS_NOM = [
    "январь", "февраль", "март", "апрель", "май", "июнь",
    "июль", "август", "сентябрь", "октябрь", "ноябрь", "декабрь",
]

def esc(value):
    return html.escape(str(value), quote=True)


def load_digest():
    if not os.path.exists(DIGEST):
        return None
    with open(DIGEST, "r", encoding="utf-8") as fh:
        return json.load(fh)


def render_video_card(video):
    """Карточка ролика: превью, заголовок, анонс. Больше ничего.

    Выводы, ожидаемый результат и ограничения по-прежнему лежат в digest.json,
    но на странице не показываются: карточка — это анонс, по которому решают,
    открывать или нет, а не сам разбор. Когда все это выводилось разом, карточка
    вырастала до 856 пикселей, а выпуск — до восьми тысяч.
    """
    thumb = video.get("thumbnail_url")
    image = f"<img src='{esc(thumb)}' alt='' loading='lazy'>" if thumb else ""
    url = "https://www.youtube.com/watch?v=%s" % esc(video["video_id"])
    return (
        f"<article class=\"card digest-card\">{image}"
        f"<div class=\"digest-card-body\">"
        f"<h3><a href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(video['title'])}</a></h3>"
        f"<p class=\"digest-summary\">{esc(video['summary_ru'])}</p>"
        f"</div></article>"
    )


def render_web_item(article):
    return (
        "<article class=\"digest-article\">"
        "<h3><a href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s</a></h3>"
        "<p class=\"digest-summary\">%s</p></article>"
    ) % (esc(article["url"]), esc(article["title"]), esc(article["summary_ru"]))


def render_lead_article(article):
    """Главная статья выпуска — единственное место, где ломается ровная сетка.

    Набирается серифом, тем же, которым набраны уроки: это связывает статьи с
    чтением, а видео оставляет интерфейсу. Порядок статей задает конвейер
    оценкой по рубрике, и первая в списке действительно первая по баллу —
    верстка просто перестает эту разницу прятать.
    """
    return (
        "<article class=\"digest-lead\">"
        "<h3><a href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s</a></h3>"
        "<p class=\"digest-lead-summary\">%s</p></article>"
    ) % (esc(article["url"]), esc(article["title"]), esc(article["summary_ru"]))


def render_issue_page(issue, is_closed=False):
    videos = issue["videos"]
    web = issue["web"]

    videos_html = "".join(render_video_card(v) for v in videos)
    videos_empty = "" if videos else "<p class='digest-empty'>За эту неделю подходящих роликов не нашлось.</p>"

    if web:
        web_body = render_lead_article(web[0])
        if len(web) > 1:
            web_body += "<div class='digest-articles'>%s</div>" % "".join(
                render_web_item(article) for article in web[1:])
    else:
        web_body = "<p class='digest-empty'>За эту неделю качественных статей не нашлось.</p>"

    crumb = ""
    if is_closed:
        crumb = '<p class="digest-crumb"><a href="/news/">Лента</a> / <a href="/news/archive/">Архив</a> / %s</p>' % esc(issue["period_label"])
        lede = "Архивный выпуск — материалы этой недели больше не меняются."
    else:
        lede = "Что нового у ИИ-агентов на YouTube и в вебе — коротко, на русском, со ссылкой на первоисточник."
        crumb = '<p class="digest-crumb"><a href="/news/archive/">Архив прошлых недель &rarr;</a></p>'

    # Панель фильтров и сортировки убрана вместе со скриптом: на десяти роликах
    # она предлагала работу вместо чтения, а порядок и так задан оценкой.
    title = "Лента — %s — Запуск ИИ-агентов" % issue["period_label"]

    return "\n".join([
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="/favicon.ico">',
        "<title>%s</title>" % esc(title),
        '<link rel="stylesheet" href="/assets/lesson.css">',
        '<link rel="stylesheet" href="/assets/news.css">',
        "</head>",
        "<body>",
        render_sitenav("news"),
        '<article class="sheet wide">',
        '<div class="digest-head">',
        '<div class="digest-head-text">',
        crumb,
        "<h1>%s</h1>" % esc(issue["period_label"]),
        '<p class="digest-lede">%s</p>' % lede,
        '<div class="digest-stats"><span><strong>%d</strong>видео</span><span><strong>%d</strong>статей</span></div>' % (len(videos), len(web)),
        "</div>",
        '<img class="digest-mascot" src="/assets/brand/news-octopus.png" alt="Осьминог — талисман Ленты">',
        "</div>",
        '<section aria-label="Видео недели">',
        '<h2 class="digest-section">Видео недели</h2>',
        videos_empty,
        '<div class="digest-grid">%s</div>' % videos_html,
        "</section>",
        '<section class="digest-issue-articles" aria-label="Статьи недели">',
        '<h2 class="digest-section">Статьи недели</h2>',
        web_body,
        "</section>",
        '<footer class="colophon">',
        "<nav>",
        '<a href="/kb/">База знаний</a>',
        '<a href="/news/archive/">Архив</a>',
        "</nav>",
        "</footer>",
        "</article>",
        "</body>",
        "</html>",
    ]) + "\n"


def render_archive(closed_weeks):
    groups = {}
    order = []
    for week in closed_weeks:
        dt = datetime.fromisoformat(week["week_start"])
        key = (dt.year, dt.month)
        if key not in groups:
            groups[key] = []
            order.append(key)
        groups[key].append(week)
    order = sorted(set(order), reverse=True)

    sections = []
    for index, (year, month) in enumerate(order):
        weeks = groups[(year, month)]
        cards = "".join(_archive_week_card(w) for w in weeks)
        open_attr = " open" if index == 0 else ""
        sections.append(
            "<details%s><summary>%s %d</summary>%s</details>" % (open_attr, MONTHS_NOM[month - 1], year, cards)
        )
    body = "".join(sections) if sections else "<p class='digest-empty'>Пока нет закрытых выпусков — первая неделя закроется в ближайший понедельник.</p>"

    return "\n".join([
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="/favicon.ico">',
        "<title>Архив Ленты — Запуск ИИ-агентов</title>",
        '<link rel="stylesheet" href="/assets/lesson.css">',
        '<link rel="stylesheet" href="/assets/news.css">',
        "</head>",
        "<body>",
        render_sitenav("news"),
        '<article class="sheet wide">',
        '<header class="masthead">',
        "<h1>Архив Ленты</h1>",
        '<p class="standfirst">Все закрытые выпуски недельного дайджеста — по месяцам, сначала новые.</p>',
        "</header>",
        '<div class="digest-archive">%s</div>' % body,
        '<footer class="colophon">',
        "<nav>",
        '<a href="/kb/">База знаний</a>',
        '<a href="/news/">Текущая неделя</a>',
        "</nav>",
        "</footer>",
        "</article>",
        "</body>",
        "</html>",
    ]) + "\n"


def _archive_week_card(week):
    thumbs = [v["thumbnail_url"] for v in week["videos"][:5] if v.get("thumbnail_url")]
    collage = "".join("<img src='%s' alt=''>" % esc(t) for t in thumbs)
    return (
        '<article class="digest-week-card"><div class="digest-collage">%s</div>'
        '<div class="digest-week-body"><h3>%s</h3>'
        '<p class="digest-meta">%d видео &middot; %d статей</p></div>'
        '<a class="digest-open-link" href="/%s">Открыть выпуск &rarr;</a></article>'
    ) % (collage, esc(week["period_label"]), len(week["videos"]), len(week["web"]), esc(week["html_path"]))


def render_empty_index():
    return "\n".join([
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="/favicon.ico">',
        "<title>Лента — Запуск ИИ-агентов</title>",
        '<link rel="stylesheet" href="/assets/lesson.css">',
        '<link rel="stylesheet" href="/assets/news.css">',
        "</head>",
        "<body>",
        render_sitenav("news"),
        '<article class="sheet wide">',
        '<header class="masthead"><h1>Лента</h1>',
        "<p class=\"standfirst\">Дайджест еще не собирался. Первый выпуск появится здесь после первой сборки.</p>",
        "</header>",
        '<footer class="colophon"><nav><a href="/kb/">База знаний</a></nav></footer>',
        "</article>",
        "</body>",
        "</html>",
    ]) + "\n"


def write(path, content):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        fh.write(content)


def build():
    data = load_digest()
    if data is None:
        write(OUT_INDEX, render_empty_index())
        print("news: digest.json не найден, собрана пустая Лента")
        return

    write(OUT_INDEX, render_issue_page(data["current"], is_closed=False))
    for week in data["closed"]:
        write(os.path.join(NEWS_DIR, week["html_path"]), render_issue_page(week, is_closed=True))
    write(OUT_ARCHIVE, render_archive(data["closed"]))
    print(
        "news/index.html собран: %d видео текущей недели, %d закрытых недель"
        % (len(data["current"]["videos"]), len(data["closed"]))
    )


if __name__ == "__main__":
    build()
