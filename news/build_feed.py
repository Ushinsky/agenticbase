"""Сборка Ленты — еженедельного дайджеста ИИ-агентов.

Источник данных — news/digest.json: снимок текущей и закрытых недель,
экспортированный из отдельного локального проекта дайджеста (сам этот
проект и его база данных в репозитории не хранятся, только снимок).
Здесь только рендер — три вида страниц:

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
from urllib.parse import urlparse

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

# Оценщик дайджеста пишет content_type свободным текстом ("technical
# webinar / AI infrastructure", "интервью/подкаст о ...") — не по
# фиксированному словарю. Раскладываем по ключевым словам на несколько
# стабильных категорий для фильтра вместо десятков почти дублирующихся
# вариантов.
TYPE_BUCKETS = [
    ("tutorial", "Туториалы", ("tutorial", "how to", "how-to", "guide", "course", "webinar", "workshop", "educational", "explainer", "lecture", "обучающ", "гайд", "курс", "туториал")),
    ("interview", "Интервью и подкасты", ("interview", "podcast", "talk", "discussion", "meetup", "presentation", "интервью", "подкаст", "беседа", "выступлен")),
    ("analysis", "Обзоры и аналитика", ("review", "analysis", "commentary", "research", "study", "разбор", "обзор", "аналитик", "исследован")),
    ("news", "Новости и бизнес", ("news", "business", "release", "launch", "announcement", "finance", "новост", "бизнес", "финанс", "релиз")),
]
LANGUAGE_OPTIONS = [
    ("ru", "Русский"), ("en", "Английский"), ("de", "Немецкий"),
    ("fr", "Французский"), ("es", "Испанский"), ("other", "Другие"),
]


def esc(value):
    return html.escape(str(value), quote=True)


def type_bucket(content_type):
    lowered = (content_type or "").lower()
    for key, _label, keywords in TYPE_BUCKETS:
        if any(keyword in lowered for keyword in keywords):
            return key
    return "other"


def lang_bucket(language):
    code = (language or "").split("-")[0].lower()
    return code if code in {"ru", "en", "de", "fr", "es"} else "other"


def format_date(iso_value):
    dt = datetime.fromisoformat(iso_value)
    return dt.date().isoformat()


def domain_of(url):
    netloc = urlparse(url).netloc
    return netloc[4:] if netloc.startswith("www.") else netloc


def load_digest():
    if not os.path.exists(DIGEST):
        return None
    with open(DIGEST, "r", encoding="utf-8") as fh:
        return json.load(fh)


def render_video_card(video):
    thumb = video.get("thumbnail_url")
    image = f"<img src='{esc(thumb)}' alt=''>" if thumb else ""
    date = format_date(video["published_at"])
    views = video.get("view_count") or 0
    url = "https://www.youtube.com/watch?v=%s" % esc(video["video_id"])
    return (
        f"<article class=\"card digest-card\" data-type=\"{type_bucket(video['content_type'])}\" "
        f"data-lang=\"{lang_bucket(video.get('language'))}\" data-score=\"{video['score']}\" "
        f"data-views=\"{views}\" data-date=\"{date}\">{image}"
        f"<div class=\"digest-card-body\">"
        f"<h3><a href=\"{url}\" target=\"_blank\" rel=\"noopener noreferrer\">{esc(video['title'])}</a></h3>"
        f"<p class=\"digest-summary\">{esc(video['summary_ru'])}</p>"
        f"</div></article>"
    )


def render_web_item(article):
    return (
        "<li><p class=\"digest-meta\">%s &middot; %s &middot; %s &middot; <span class=\"digest-score\">%s/100</span></p>"
        "<h3><a href=\"%s\" target=\"_blank\" rel=\"noopener noreferrer\">%s</a></h3>"
        "<p class=\"digest-summary\">%s</p></li>"
    ) % (
        esc(article["source_type"]), esc(domain_of(article["url"])), format_date(article["published_at"]),
        article["score"], esc(article["url"]), esc(article["title"]), esc(article["summary_ru"]),
    )


def render_issue_page(issue, is_closed=False):
    videos = issue["videos"]
    web = issue["web"]

    type_options = "".join('<option value="%s">%s</option>' % (key, esc(label)) for key, label, _kw in TYPE_BUCKETS)
    type_options += '<option value="other">Другое</option>'
    lang_options = "".join('<option value="%s">%s</option>' % (code, esc(label)) for code, label in LANGUAGE_OPTIONS)

    videos_html = "".join(render_video_card(v) for v in videos)
    videos_empty = "" if videos else "<p class='digest-empty'>За эту неделю подходящих роликов не нашлось.</p>"
    toolbar = "" if not videos else (
        '<div class="digest-toolbar">'
        '<label>Тип <select id="f-type"><option value="">Все</option>%s</select></label>'
        '<label>Язык <select id="f-lang"><option value="">Все языки</option>%s</select></label>'
        '<label>Сортировка <select id="f-sort"><option value="score">По оценке</option>'
        '<option value="views">По просмотрам</option><option value="date">По дате</option></select></label>'
        '</div>'
    ) % (type_options, lang_options)

    if web:
        web_body = "<ol class='digest-web-list'>%s</ol>" % "".join(render_web_item(a) for a in web)
    else:
        web_body = "<p class='digest-empty'>За эту неделю качественных веб-материалов не нашлось.</p>"

    crumb = ""
    if is_closed:
        crumb = '<p class="digest-crumb"><a href="/news/index.html">Лента</a> / <a href="/news/archive/index.html">Архив</a> / %s</p>' % esc(issue["period_label"])
        lede = "Архивный выпуск — материалы этой недели больше не меняются."
    else:
        lede = "Что нового у ИИ-агентов на YouTube и в вебе — с оценкой и коротким анонсом на русском."
        crumb = '<p class="digest-crumb"><a href="/news/archive/index.html">Архив прошлых недель &rarr;</a></p>'

    script = "" if not videos else """
<script>
(function(){
var grid = document.querySelector('.digest-grid');
if (!grid) return;
var cards = Array.prototype.slice.call(grid.children);
var typeSel = document.getElementById('f-type');
var langSel = document.getElementById('f-lang');
var sortSel = document.getElementById('f-sort');
if (!typeSel || !langSel || !sortSel) return;
function apply(){
  var type = typeSel.value, lang = langSel.value, sort = sortSel.value;
  cards.forEach(function(c){
    var show = (!type || c.dataset.type === type) && (!lang || c.dataset.lang === lang);
    c.style.display = show ? '' : 'none';
  });
  var sorted = cards.slice().sort(function(a, b){
    if (sort === 'views') return (Number(b.dataset.views) || 0) - (Number(a.dataset.views) || 0);
    if (sort === 'date') return (b.dataset.date || '').localeCompare(a.dataset.date || '');
    return (Number(b.dataset.score) || 0) - (Number(a.dataset.score) || 0);
  });
  sorted.forEach(function(c){ grid.appendChild(c); });
}
typeSel.addEventListener('change', apply);
langSel.addEventListener('change', apply);
sortSel.addEventListener('change', apply);
})();
</script>
"""

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
        '<div class="digest-stats"><span><strong>%d</strong>видео</span><span><strong>%d</strong>веб-материалов</span></div>' % (len(videos), len(web)),
        "</div>",
        '<img class="digest-mascot" src="/assets/brand/news-octopus.png" alt="Осьминог — талисман Ленты">',
        "</div>",
        '<section aria-label="Видео недели">',
        toolbar,
        videos_empty,
        '<div class="digest-grid">%s</div>' % videos_html,
        "</section>",
        '<section aria-label="Веб-материалы недели">',
        "<h2>Веб-материалы недели</h2>",
        web_body,
        "</section>",
        '<footer class="colophon">',
        "<nav>",
        '<a href="/kb/index.html">База знаний</a>',
        '<a href="/news/archive/index.html">Архив</a>',
        "</nav>",
        "</footer>",
        "</article>",
        script,
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
        '<a href="/kb/index.html">База знаний</a>',
        '<a href="/news/index.html">Текущая неделя</a>',
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
        '<p class="digest-meta">%d видео &middot; %d веб-материалов</p></div>'
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
        '<footer class="colophon"><nav><a href="/kb/index.html">База знаний</a></nav></footer>',
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
