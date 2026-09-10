# -*- coding: utf-8 -*-
"""Глоссарий: из GLOSSARY.md в обычную страницу сайта.

Исходник остается разметкой markdown — его удобно править и читать
в репозитории. Но публиковать сам .md нельзя: он отдается как text/plain,
без заголовка, описания и шапки сайта, а в выдаче поисковика выглядит
куском текста без структуры. Поэтому здесь он превращается
в glossary/index.html — такую же страницу, как остальные справочники.

    python build_glossary.py

Обычно не вызывается отдельно — см. build.py.
"""

import io
import os
import re
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(BASE, "kb"))

from sitenav import asset_url, render_sitenav  # noqa: E402

SOURCE = os.path.join(BASE, "GLOSSARY.md")
OUT_DIR = os.path.join(BASE, "glossary")
OUT = os.path.join(OUT_DIR, "index.html")

AVOID = "_Избегать_:"


def esc(text):
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def inline(text):
    """Разметка внутри абзаца: жирный, курсив, код."""
    text = esc(text)
    text = re.sub(r"`([^`]+)`", r"<code>\1</code>", text)
    text = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", text)
    text = re.sub(r"_([^_]+)_", r"<em>\1</em>", text)
    return text


def parse(text):
    """Заголовок, вводные абзацы и разделы с терминами."""
    lines = text.split("\n")
    title = ""
    intro = []
    sections = []
    current = None
    item = None
    buffer = []

    def flush_paragraph():
        if not buffer:
            return None
        joined = " ".join(part.strip() for part in buffer).strip()
        del buffer[:]
        return joined

    for line in lines:
        stripped = line.strip()

        if stripped.startswith("# "):
            title = stripped[2:].strip()
            continue

        if stripped.startswith("## "):
            paragraph = flush_paragraph()
            if paragraph and current is None:
                intro.append(paragraph)
            elif paragraph and item is not None:
                item["body"].append(paragraph)
            item = None
            current = {"title": stripped[3:].strip(), "terms": [], "notes": []}
            sections.append(current)
            continue

        if stripped.startswith("**") and stripped.endswith("**:"):
            paragraph = flush_paragraph()
            if paragraph and item is not None:
                item["body"].append(paragraph)
            elif paragraph and current is None:
                intro.append(paragraph)
            item = {"term": stripped[2:-3].strip(), "body": [], "avoid": ""}
            current["terms"].append(item)
            continue

        if stripped.startswith(AVOID) and item is not None:
            paragraph = flush_paragraph()
            if paragraph:
                item["body"].append(paragraph)
            item["avoid"] = stripped[len(AVOID):].strip()
            continue

        if stripped.startswith("- "):
            paragraph = flush_paragraph()
            if paragraph and item is not None:
                item["body"].append(paragraph)
            item = None
            current["notes"].append(stripped[2:].strip())
            continue

        if not stripped:
            paragraph = flush_paragraph()
            if paragraph is None:
                continue
            if item is not None:
                item["body"].append(paragraph)
            elif current is None:
                intro.append(paragraph)
            elif current["notes"]:
                current["notes"][-1] += " " + paragraph
            continue

        if current is not None and current["notes"] and item is None and not buffer:
            current["notes"][-1] += " " + stripped
            continue

        buffer.append(stripped)

    paragraph = flush_paragraph()
    if paragraph:
        if item is not None:
            item["body"].append(paragraph)
        elif current is None:
            intro.append(paragraph)

    return title, intro, sections


def render(title, intro, sections):
    out = []
    add = out.append

    add("<!doctype html>")
    add('<html lang="ru">')
    add("<head>")
    add('<meta charset="utf-8">')
    add('<meta name="viewport" content="width=device-width, initial-scale=1">')
    add('<link rel="icon" href="/favicon.ico">')
    add("<title>%s</title>" % esc(title))
    add('<link rel="stylesheet" href="%s">' % asset_url("/assets/lesson.css"))
    add("</head>")
    add("<body>")
    add(render_sitenav("kb"))
    add('<article class="sheet">')
    add('  <header class="masthead">')
    add('    <p class="course">Курс 1 · Справочник</p>')
    add("    <h1>%s</h1>" % esc(title))
    if intro:
        add('    <p class="standfirst">%s</p>' % inline(intro[0]))
    add("  </header>")

    for index, section in enumerate(sections, start=1):
        add("  <section>")
        add('    <span class="num" aria-hidden="true">%d</span>' % index)
        add("    <h2>%s</h2>" % esc(section["title"]))

        if section["terms"]:
            add('    <dl class="ref-grid">')
            for term in section["terms"]:
                add("      <dt>—</dt>")
                add("      <dd>")
                add("        <b>%s</b>" % inline(term["term"]))
                for paragraph in term["body"]:
                    add("        <span>%s</span>" % inline(paragraph))
                if term["avoid"]:
                    add(
                        "        <span><em>Избегать:</em> %s</span>"
                        % inline(term["avoid"])
                    )
                add("      </dd>")
            add("    </dl>")

        if section["notes"]:
            add("    <ul>")
            for note in section["notes"]:
                add("      <li>%s</li>" % inline(note))
            add("    </ul>")

        add("  </section>")

    add("</article>")
    add("</body>")
    add("</html>")
    return "\n".join(out) + "\n"


def build():
    with io.open(SOURCE, encoding="utf-8") as fh:
        title, intro, sections = parse(fh.read())

    if not os.path.isdir(OUT_DIR):
        os.makedirs(OUT_DIR)

    with io.open(OUT, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(render(title, intro, sections))

    terms = sum(len(section["terms"]) for section in sections)
    print("glossary/index.html собран: %d разделов, %d терминов" % (len(sections), terms))


if __name__ == "__main__":
    build()
