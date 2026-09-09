"""Сборка Ленты — еженедельного дайджеста ИИ-агентов.

Источник данных — news/digest.json, который собирает news/publish.py в конце
конвейера (collect -> filter -> classify -> score -> write -> publish). Прежний
внешний проект дайджеста, из которого снимок приходил раньше, больше не
существует. Здесь только рендер — три вида страниц:

    news/index.html          — текущий (незакрытый) выпуск
    news/archive/index.html  — архив закрытых выпусков по месяцам
    news/weeks/<label>.html  — неизменяемая страница одного закрытого выпуска

Верстка сделана по отдельному ТЗ дизайнера (DESIGN-BRIEF-LENTA.md). Два
принципа оттуда, которые важно не потерять при правках:

1. Видео и статьи — блоки одного выпуска, а не два раздела. Различаются
   плотностью верстки, а не оформлением.
2. Внутри блока иерархии нет: все карточки одной формы. Различие несут
   служебная строка и, у статей, иконка типа.

В отличие от уроков и статей базы знаний, в Ленте разрешены имена продуктов и
ссылки на источники — раздел справочный, а не учебный.

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
from sitenav import render_sitenav, asset_url

DIGEST = os.path.join(BASE, "news", "digest.json")
ICONS_DIR = os.path.join(BASE, "assets", "icons", "types")
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

# Порядок типов зафиксирован и одинаков везде: в легенде выпуска и в раскладке
# по типам в архиве. По неизменному порядку раскладку можно читать глазом, не
# сверяясь с подписями.
TYPES = [
    ("научная работа", "nauchnaya-rabota"),
    ("обсуждение", "obsuzhdenie"),
    ("инженерный блог", "inzhenerny-blog"),
    ("блог практика", "blog-praktika"),
    ("отраслевое издание", "otraslevoe-izdanie"),
]
TYPE_FILES = dict(TYPES)

NUMERALS = {1: "один", 2: "два", 3: "три", 4: "четыре", 5: "пять"}

ARCHIVE_PAGE_SIZE = 8   # сколько выпусков отдается сразу, до «показать более ранние»


def esc(value):
    return html.escape(str(value), quote=True)


def load_digest():
    if not os.path.exists(DIGEST):
        return None
    with open(DIGEST, "r", encoding="utf-8") as fh:
        return json.load(fh)


# --------------------------------------------------------------------------
# Мелкие форматтеры
# --------------------------------------------------------------------------

def icon(type_name):
    """Встраивает SVG иконки прямо в разметку.

    Именно встраивает, а не подключает картинкой: иконки нарисованы на
    currentColor и должны брать цвет служебной строки, в которой стоят.
    Через <img> это не работает.
    """
    name = TYPE_FILES.get(type_name)
    if not name:
        return ""
    path = os.path.join(ICONS_DIR, name + ".svg")
    if not os.path.exists(path):
        return ""
    with open(path, "r", encoding="utf-8") as fh:
        return fh.read().strip().replace("\n", "")


def short_date(iso_value):
    """«3 сен» — коротко, потому что стоит в служебной строке."""
    if not iso_value:
        return ""
    try:
        dt = datetime.fromisoformat(iso_value)
    except ValueError:
        return ""
    return "%d %s" % (dt.day, MONTHS_RU[dt.month - 1][:3])


def minutes(seconds):
    return max(1, round((seconds or 0) / 60))


def duration_label(videos):
    """«15-50 мин» — разброс длительности по блоку."""
    values = [minutes(v.get("duration_sec")) for v in videos if v.get("duration_sec")]
    if not values:
        return ""
    low, high = min(values), max(values)
    return "%d мин" % low if low == high else "%d—%d мин" % (low, high)


def plural(count, one, few, many):
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    tail = count % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def type_counts(issue):
    """Раскладка выпуска по типам, в фиксированном порядке. Нули опущены."""
    counts = {}
    for article in issue.get("web", []):
        name = article.get("type")
        if name:
            counts[name] = counts.get(name, 0) + 1
    return [(name, counts[name]) for name, _file in TYPES if counts.get(name)]


def lead_material(issue):
    """Главный материал выпуска — лучший по баллу среди видео и статей.

    Отдельного редакторского названия у выпуска нет: в архиве строка выпуска
    подписывается заголовком этого материала.
    """
    everything = list(issue.get("videos", [])) + list(issue.get("web", []))
    if not everything:
        return None
    return max(everything, key=lambda item: item.get("score", 0))


def rest_titles(issue, lead, limit):
    everything = list(issue.get("videos", [])) + list(issue.get("web", []))
    others = [i for i in everything if i is not lead]
    others.sort(key=lambda item: -item.get("score", 0))
    return [i["title"] for i in others[:limit]]


# --------------------------------------------------------------------------
# Выпуск
# --------------------------------------------------------------------------

def render_video_card(video):
    thumb = video.get("thumbnail_url")
    image = ("<img src='%s' alt='' loading='lazy'>" % esc(thumb)) if thumb else ""
    url = "https://www.youtube.com/watch?v=%s" % esc(video["video_id"])
    meta = " · ".join(part for part in [
        esc(video.get("channel_title", "")),
        short_date(video.get("published_at")),
        "%d мин" % minutes(video.get("duration_sec")) if video.get("duration_sec") else "",
    ] if part)
    return (
        "<article class=\"digest-card\">%s"
        "<div class=\"digest-card-body\">"
        "<p class=\"digest-meta\">%s</p>"
        "<h3><a href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s</a></h3>"
        "<p class=\"digest-summary\">%s</p>"
        "</div></article>"
    ) % (image, meta, url, esc(video["title"]), esc(video.get("summary_ru", "")))


def render_article_card(article):
    meta = " · ".join(part for part in [
        esc(article.get("domain", "")),
        short_date(article.get("published_at")),
    ] if part)
    return (
        "<article class=\"digest-card digest-card-text\">"
        "<div class=\"digest-card-body\">"
        "<p class=\"digest-meta digest-meta-typed\">"
        "<span class=\"digest-type-icon\" title=\"%s\" aria-label=\"%s\" role=\"img\">%s</span>"
        "<span>%s</span></p>"
        "<h3><a href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s</a></h3>"
        "<p class=\"digest-summary\">%s</p>"
        "</div></article>"
    ) % (
        esc(article.get("type", "")), esc(article.get("type", "")), icon(article.get("type", "")),
        meta, esc(article["url"]), esc(article["title"]), esc(article.get("summary_ru", "")),
    )


def render_legend():
    items = "".join(
        "<li><span class=\"digest-type-icon\" aria-hidden=\"true\">%s</span>%s</li>"
        % (icon(name), esc(name)) for name, _file in TYPES
    )
    return "<ul class=\"digest-legend\">%s</ul>" % items


def render_issue_page(issue, is_closed=False):
    videos = issue.get("videos", [])
    web = issue.get("web", [])
    number = issue.get("number", 1)

    if is_closed:
        crumb = ('<p class="digest-crumb"><a href="/news/">Лента</a> / '
                 '<a href="/news/archive/">Архив</a> / выпуск %d</p>' % number)
    else:
        crumb = '<p class="digest-crumb"><a href="/news/archive/">Архив выпусков &rarr;</a></p>'

    watch_count = "%d %s" % (len(videos), plural(len(videos), "ролик", "ролика", "роликов"))
    watch_meta = " · ".join(part for part in [watch_count, duration_label(videos)] if part)

    kinds = len(type_counts(issue))
    read_count = "%d %s" % (len(web), plural(len(web), "материал", "материала", "материалов"))
    read_meta = " · ".join(part for part in [
        read_count,
        "%s %s" % (NUMERALS.get(kinds, kinds), plural(kinds, "тип", "типа", "типов")) if kinds else "",
    ] if part)

    videos_block = (
        '<div class="digest-grid">%s</div>' % "".join(render_video_card(v) for v in videos)
        if videos else "<p class='digest-empty'>За эту неделю подходящих роликов не нашлось.</p>"
    )
    articles_block = (
        render_legend() + '<div class="digest-grid">%s</div>' % "".join(
            render_article_card(a) for a in web)
        if web else "<p class='digest-empty'>За эту неделю качественных статей не нашлось.</p>"
    )

    title = "Выпуск %d — %s — Запуск ИИ-агентов" % (number, issue["period_label"])

    return "\n".join([
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="/favicon.ico">',
        "<title>%s</title>" % esc(title),
        '<link rel="stylesheet" href="%s">' % asset_url('/assets/lesson.css'),
        '<link rel="stylesheet" href="%s">' % asset_url('/assets/news.css'),
        "</head>",
        "<body>",
        render_sitenav("news"),
        '<article class="sheet wide">',
        crumb,
        '<header class="issue-head">',
        "<h1>Выпуск %d</h1>" % number,
        '<p class="issue-dates">%s</p>' % esc(issue["period_label"]),
        "</header>",
        '<section class="issue-block" aria-label="Смотреть">',
        '<div class="block-head"><h2>Смотреть</h2><p class="block-meta">%s</p></div>' % esc(watch_meta),
        videos_block,
        "</section>",
        '<section class="issue-block" aria-label="Читать">',
        '<div class="block-head"><h2>Читать</h2><p class="block-meta">%s</p></div>' % esc(read_meta),
        articles_block,
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


# --------------------------------------------------------------------------
# Архив
# --------------------------------------------------------------------------

def render_type_breakdown(issue):
    """Раскладка по типам — главный смысл строки выпуска в архиве.

    По ней видно, был выпуск научным или про инженерную практику, не открывая
    его. Порядок иконок постоянный, типы с нулем не показываются.
    """
    parts = "".join(
        "<span class=\"type-count\" title=\"%s\">"
        "<span class=\"digest-type-icon\" aria-hidden=\"true\">%s</span>%d</span>"
        % (esc(name), icon(name), count)
        for name, count in type_counts(issue)
    )
    return "<p class=\"type-breakdown\">%s</p>" % parts if parts else ""


def render_counts(issue):
    videos, web = len(issue.get("videos", [])), len(issue.get("web", []))
    return "%d %s · %d %s" % (
        videos, plural(videos, "видео", "видео", "видео"),
        web, plural(web, "статья", "статьи", "статей"),
    )


def render_current_row(issue):
    lead = lead_material(issue)
    if lead is None:
        return ""
    rest = rest_titles(issue, lead, 3)
    rest_line = ("<p class=\"row-rest\">Еще в выпуске: %s</p>"
                 % esc(", ".join(rest))) if rest else ""
    return "\n".join([
        '<section class="archive-current">',
        '<h2 class="archive-subhead">Текущий выпуск</h2>',
        '<div class="current-row">',
        '<div class="row-num"><span class="num">%d</span>'
        '<span class="row-dates">%s</span></div>' % (issue.get("number", 1), esc(issue["period_label"])),
        '<div class="row-body"><p class="row-lead">%s</p>%s</div>' % (esc(lead["title"]), rest_line),
        '<div class="row-side"><p class="row-counts">%s</p>%s'
        '<a class="row-open" href="/news/">Открыть выпуск &rarr;</a></div>'
        % (render_counts(issue), render_type_breakdown(issue)),
        "</div>",
        "</section>",
    ])


def render_archive_row(week):
    lead = lead_material(week)
    if lead is None:
        return ""
    rest = rest_titles(week, lead, 2)
    rest_line = ("<p class=\"row-rest\">Еще: %s</p>" % esc(", ".join(rest))) if rest else ""
    href = "/news/%s" % week.get("html_path", "")
    return (
        '<a class="archive-row" href="%s">'
        '<div class="row-num"><span class="num">&#8470;%d</span>'
        '<span class="row-dates">%s</span></div>'
        '<div class="row-body"><p class="row-lead">%s</p>%s</div>'
        '<div class="row-side"><p class="row-counts">%s</p>%s</div>'
        "</a>"
    ) % (
        esc(href), week.get("number", 0), esc(week["period_label"]),
        esc(lead["title"]), rest_line, render_counts(week), render_type_breakdown(week),
    )


def render_archive(current, closed_weeks):
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

    shown = closed_weeks[:ARCHIVE_PAGE_SIZE]
    shown_keys = {id(week) for week in shown}

    sections = []
    for year, month in order:
        weeks = [w for w in groups[(year, month)] if id(w) in shown_keys]
        if not weeks:
            continue
        rows = "".join(render_archive_row(week) for week in weeks)
        sections.append(
            '<section class="archive-month">'
            '<div class="month-label"><h3>%s %d</h3>'
            '<p class="month-count">%d %s</p></div>'
            '<div class="month-rows">%s</div>'
            "</section>"
            % (MONTHS_NOM[month - 1], year, len(weeks),
               plural(len(weeks), "выпуск", "выпуска", "выпусков"), rows)
        )

    if sections:
        body = "".join(sections)
    else:
        body = ("<p class='digest-empty'>Закрытых выпусков пока нет — первый закроется, "
                "когда выйдет следующий.</p>")

    total = len(closed_weeks) + (1 if current else 0)
    since = ""
    if closed_weeks:
        oldest = datetime.fromisoformat(closed_weeks[-1]["week_start"])
        since = " · с %s %d" % (MONTHS_RU[oldest.month - 1], oldest.year)
    elif current:
        started = datetime.fromisoformat(current["week_start"])
        since = " · с %s %d" % (MONTHS_RU[started.month - 1], started.year)

    footer = ""
    if len(closed_weeks) > ARCHIVE_PAGE_SIZE:
        first = closed_weeks[len(shown) - 1].get("number", 0)
        last = closed_weeks[0].get("number", 0)
        footer = (
            '<div class="archive-foot">'
            '<p>Показаны выпуски %d—%d из %d</p>'
            '<a href="/news/archive/all.html">Показать более ранние &rarr;</a>'
            "</div>" % (first, last, total)
        )

    return "\n".join([
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="/favicon.ico">',
        "<title>Архив Ленты — Запуск ИИ-агентов</title>",
        '<link rel="stylesheet" href="%s">' % asset_url('/assets/lesson.css'),
        '<link rel="stylesheet" href="%s">' % asset_url('/assets/news.css'),
        "</head>",
        "<body>",
        render_sitenav("news"),
        '<article class="sheet wide">',
        '<header class="issue-head">',
        "<h1>Архив</h1>",
        '<p class="issue-dates">%d %s%s</p>'
        % (total, plural(total, "выпуск", "выпуска", "выпусков"), since),
        "</header>",
        render_current_row(current) if current else "",
        body,
        footer,
        '<footer class="colophon">',
        "<nav>",
        '<a href="/kb/">База знаний</a>',
        '<a href="/news/">Текущий выпуск</a>',
        "</nav>",
        "</footer>",
        "</article>",
        "</body>",
        "</html>",
    ]) + "\n"


def render_empty_index():
    return "\n".join([
        "<!doctype html>",
        '<html lang="ru">',
        "<head>",
        '<meta charset="utf-8">',
        '<meta name="viewport" content="width=device-width, initial-scale=1">',
        '<link rel="icon" href="/favicon.ico">',
        "<title>Лента — Запуск ИИ-агентов</title>",
        '<link rel="stylesheet" href="%s">' % asset_url('/assets/lesson.css'),
        '<link rel="stylesheet" href="%s">' % asset_url('/assets/news.css'),
        "</head>",
        "<body>",
        render_sitenav("news"),
        '<article class="sheet wide">',
        '<header class="issue-head"><h1>Лента</h1>',
        '<p class="issue-dates">выпусков еще нет</p></header>',
        "<p class=\"digest-empty\">Первый выпуск появится здесь после первой сборки.</p>",
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
    if data is None or not data.get("current"):
        write(OUT_INDEX, render_empty_index())
        print("news: digest.json не найден, собрана пустая Лента")
        return

    current = data["current"]
    closed = data.get("closed", [])

    write(OUT_INDEX, render_issue_page(current, is_closed=False))
    for week in closed:
        write(os.path.join(NEWS_DIR, week["html_path"]), render_issue_page(week, is_closed=True))
    write(OUT_ARCHIVE, render_archive(current, closed))

    print("news/index.html собран: выпуск %d, %d видео, %d статей, в архиве %d"
          % (current.get("number", 1), len(current.get("videos", [])),
             len(current.get("web", [])), len(closed)))


if __name__ == "__main__":
    build()
