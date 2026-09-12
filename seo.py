# -*- coding: utf-8 -*-
"""Метаданные страниц: описание, канонический адрес, превью для соцсетей.

Зачем отдельным проходом, а не руками в каждом файле. Описание страницы уже
существует в одном месте — это поле summary в kb/manifest.json, по нему же
строится карточка в базе знаний. Дублировать его в разметке значит завести
второй источник правды, который разойдется с первым на третьей правке.
Поэтому здесь один проход по готовым страницам, который переписывает блок
метаданных из манифеста.

Блок ограничен маркерами и переписывается целиком при каждом запуске, так
что скрипт идемпотентен: повторный запуск ничего не меняет.

    python seo.py

Обычно не вызывается отдельно — см. build.py.
"""

import io
import json
import os
import re

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "kb", "manifest.json")
DOMAIN = "https://agenticbase.ru"
SITE = "AgenticBase"
PREVIEW = "/assets/brand/hero-octopus.png"
PREVIEW_SIZE = ("754", "754")

START = "<!-- метаданные: собраны seo.py, руками не править -->"
END = "<!-- конец метаданных -->"

SKIP = ("site", ".git", "__pycache__", "sources", "learning-records", "assets")

# Страницы, которых нет в манифесте: разделы сайта и служебные.
# Описание для них живет здесь, потому что больше нигде и не живет.
EXTRA = {
    "index.html": (
        "Запуск ИИ-агентов",
        "Курс о том, как довести ИИ-агента до работы: от выбора ступени "
        "автономии до эксплуатации. Плюс еженедельная лента материалов.",
        "WebSite",
    ),
    "kb/index.html": (
        "База знаний",
        "Десять уроков про запуск ИИ-агентов и статьи к ним: цикл агента, "
        "инструменты, память, мультиагентные схемы, проверка и эксплуатация.",
        "Course",
    ),
    "news/index.html": (
        "Лента",
        "Материалы про ИИ-агентов за неделю: разборы, ролики и статьи, "
        "отобранные и коротко пересказанные.",
        "CollectionPage",
    ),
    "news/archive/index.html": (
        "Архив ленты",
        "Прошлые выпуски еженедельной ленты материалов про ИИ-агентов.",
        "CollectionPage",
    ),
    "hub/index.html": (
        "Хаб агентов",
        "Каталог готовых ИИ-агентов и инструментов для их сборки.",
        "CollectionPage",
    ),
}

NOINDEX = ("404.html",)

# Семейства страниц, которые генератор создает по одной на сущность: перечислять
# их поштучно в EXTRA нельзя — список рос бы с каждым выпуском. Описание для
# такой страницы собирается из ее заголовка.
#
# news/weeks/<label>.html — архивный выпуск Ленты. Заголовок вида
# «Выпуск 7 — 5-11 сентября — Запуск ИИ-агентов», из него и берем период.
FAMILIES = (
    (
        re.compile(r"^news/weeks/[^/]+\.html$"),
        re.compile(r"^(Выпуск\s+\d+)\s+—\s+([^—]+?)\s+—"),
        "Архивный выпуск ленты за %s: ролики и статьи про ИИ-агентов, "
        "отобранные и коротко пересказанные. Материалы выпуска больше не меняются.",
        "CollectionPage",
    ),
)


def family_meta(relpath, text):
    """Заголовок, описание и тип для страницы из генерируемого семейства."""
    for path_re, title_re, template, kind in FAMILIES:
        if not path_re.match(relpath):
            continue
        match = re.search(r"<title>(.*?)</title>", text, re.S)
        raw = match.group(1).strip() if match else ""
        parts = title_re.match(raw)
        if not parts:
            continue
        return parts.group(1), template % parts.group(2), kind
    return None


def esc(text):
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def page_url(relpath):
    """Канонический адрес страницы по ее месту на диске."""
    path = relpath.replace(os.sep, "/")
    if path.endswith(".html"):
        path = path[: -len(".html")]
    if path == "index":
        return DOMAIN + "/"
    if path.endswith("/index"):
        return DOMAIN + "/" + path[: -len("index")]
    return DOMAIN + "/" + path


def manifest_pages():
    with io.open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    pages = {}
    for node in manifest["nodes"]:
        if node.get("status") != "published":
            continue
        path = node.get("path")
        if not path or not path.endswith(".html"):
            continue
        kind = "LearningResource" if node.get("type") == "lesson" else "Article"
        pages[path.replace("\\", "/")] = (node["title"], node["summary"], kind)
    return pages


def standfirst(text):
    """Запасной источник описания — вводный абзац самой страницы."""
    match = re.search(r'<p class="standfirst">(.*?)</p>', text, re.S)
    if not match:
        return ""
    plain = re.sub(r"<[^>]+>", " ", match.group(1))
    return " ".join(plain.split())


def structured_data(kind, title, description, url):
    data = {
        "@context": "https://schema.org",
        "@type": kind,
        "name": title,
        "description": description,
        "url": url,
        "inLanguage": "ru",
    }
    if kind == "Article":
        data["headline"] = title
        data["isPartOf"] = {
            "@type": "Course",
            "name": "Запуск ИИ-агентов",
            "url": DOMAIN + "/kb/",
        }
    if kind == "LearningResource":
        data["learningResourceType"] = "урок"
        data["isPartOf"] = {
            "@type": "Course",
            "name": "Запуск ИИ-агентов",
            "url": DOMAIN + "/kb/",
        }
    if kind == "Course":
        data["provider"] = {"@type": "Organization", "name": SITE, "url": DOMAIN + "/"}
    dumped = json.dumps(data, ensure_ascii=False, indent=2)
    return dumped.replace("</", "<\\/")


def block(title, description, url, kind, noindex):
    lines = [START]
    if noindex:
        lines.append('<meta name="robots" content="noindex">')
    lines.append('<meta name="description" content="%s">' % esc(description))
    if not noindex:
        # У закрытой от индексации страницы канонического адреса быть
        # не должно: он говорит поисковику обратное тому, что говорит robots.
        lines.append('<link rel="canonical" href="%s">' % url)
    lines.append('<meta property="og:type" content="website">')
    lines.append('<meta property="og:site_name" content="%s">' % SITE)
    lines.append('<meta property="og:locale" content="ru_RU">')
    lines.append('<meta property="og:title" content="%s">' % esc(title))
    lines.append('<meta property="og:description" content="%s">' % esc(description))
    lines.append('<meta property="og:url" content="%s">' % url)
    lines.append('<meta property="og:image" content="%s">' % (DOMAIN + PREVIEW))
    lines.append('<meta property="og:image:width" content="%s">' % PREVIEW_SIZE[0])
    lines.append('<meta property="og:image:height" content="%s">' % PREVIEW_SIZE[1])
    lines.append('<meta name="twitter:card" content="summary">')
    lines.append('<meta name="twitter:title" content="%s">' % esc(title))
    lines.append('<meta name="twitter:description" content="%s">' % esc(description))
    lines.append('<meta name="twitter:image" content="%s">' % (DOMAIN + PREVIEW))
    if not noindex:
        lines.append('<script type="application/ld+json">')
        lines.append(structured_data(kind, title, description, url))
        lines.append("</script>")
    lines.append(END)
    return "\n".join(lines)


def pages():
    known = manifest_pages()
    found = []
    for root, dirs, files in os.walk(BASE):
        dirs[:] = [d for d in dirs if d not in SKIP and not d.startswith(".")]
        for name in sorted(files):
            if not name.endswith(".html"):
                continue
            relpath = os.path.relpath(os.path.join(root, name), BASE)
            found.append((relpath.replace(os.sep, "/"), known))
    return found


def apply(relpath, known):
    full = os.path.join(BASE, relpath.replace("/", os.sep))
    with io.open(full, encoding="utf-8") as fh:
        text = fh.read()

    noindex = relpath in NOINDEX
    if relpath in known:
        title, description, kind = known[relpath]
    elif relpath in EXTRA:
        title, description, kind = EXTRA[relpath]
    elif family_meta(relpath, text):
        title, description, kind = family_meta(relpath, text)
    else:
        match = re.search(r"<title>(.*?)</title>", text, re.S)
        title = match.group(1).strip() if match else SITE
        description = standfirst(text)
        kind = "WebPage"
        if not description and not noindex:
            return "без описания"

    fresh = block(title, description, page_url(relpath), kind, noindex)

    if START in text and END in text:
        updated = re.sub(
            re.escape(START) + ".*?" + re.escape(END), lambda m: fresh, text, flags=re.S
        )
    else:
        match = re.search(r"</title>", text)
        if not match:
            return "нет заголовка"
        cut = match.end()
        updated = text[:cut] + "\n" + fresh + text[cut:]

    if updated == text:
        return "без изменений"

    with io.open(full, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(updated)
    return "обновлено"


def build():
    done = 0
    skipped = []
    for relpath, known in pages():
        result = apply(relpath, known)
        if result in ("обновлено", "без изменений"):
            done += 1
        else:
            skipped.append("%s (%s)" % (relpath, result))

    print("метаданные проставлены: %d страниц" % done)
    for line in skipped:
        print("  пропущено: %s" % line)


if __name__ == "__main__":
    build()
