"""Сборка sitemap.xml для поисковиков.

Собирает список опубликованных страниц из kb/manifest.json плюс
статические разделы (главная, база знаний, лента). Запускать
после kb/build_index.py, чтобы манифест был актуален. Обычно не
вызывается отдельно — см. build.py.

    python build_sitemap.py
"""

import json
import os

BASE = os.path.dirname(os.path.abspath(__file__))
DOMAIN = "https://agenticbase.ru"
OUT = os.path.join(BASE, "sitemap.xml")


def build():
    with open(os.path.join(BASE, "kb", "manifest.json"), "r", encoding="utf-8") as fh:
        manifest = json.load(fh)

    urls = ["/", "/kb/index.html", "/news/index.html"]
    for node in manifest["nodes"]:
        if node.get("status") != "published":
            continue
        path = node.get("path")
        if path:
            urls.append("/" + path.replace("\\", "/"))

    out = ['<?xml version="1.0" encoding="UTF-8"?>']
    out.append('<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">')
    for url in urls:
        out.append("  <url><loc>%s%s</loc></url>" % (DOMAIN, url))
    out.append("</urlset>")

    with open(OUT, "w", encoding="utf-8") as fh:
        fh.write("\n".join(out) + "\n")

    print("sitemap.xml собран: %d адресов" % len(urls))


if __name__ == "__main__":
    build()
