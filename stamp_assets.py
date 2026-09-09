"""Отпечатки содержимого у ссылок на статику — проход по готовой выкладке.

Beget отдает статику с Cache-Control: max-age=604800. Без отпечатка правка
общих стилей доходит до вернувшегося читателя через неделю, и все это время
он видит новую разметку со старым оформлением.

Собираемые страницы (Лента, база знаний, хаб, главная) получают отпечаток
прямо при сборке — через asset_url() в kb/sitenav.py. Но страницы уроков,
статей и справочника лежат в репозитории готовыми файлами и генератором не
собираются: там ссылки написаны руками. Этот скрипт закрывает их.

Работает по копии для выкладки, а не по исходникам: репозиторий остается
чистым, отпечатки не попадают в историю и не создают шума в диффах при
каждой сборке.

Идемпотентен: ссылку, у которой отпечаток уже есть, не трогает.

Запуск (в воркфлоу — после сборки набора site/):

    python stamp_assets.py site
"""

import hashlib
import os
import re
import sys

# Только статика, которую кеширует сервер и которая меняется вместе с версткой.
ASSET_RE = re.compile(r'(?P<attr>href|src)="(?P<path>[^"?#]+\.(?:css|js))"')

_CACHE = {}


def fingerprint(full_path):
    if full_path in _CACHE:
        return _CACHE[full_path]
    with open(full_path, "rb") as handle:
        _CACHE[full_path] = hashlib.sha1(handle.read()).hexdigest()[:8]
    return _CACHE[full_path]


def stamp_file(page_path, root):
    with open(page_path, "r", encoding="utf-8") as handle:
        text = handle.read()

    folder = os.path.dirname(page_path)
    changed = [0]

    def replace(match):
        target = match.group("path")
        if target.startswith(("http://", "https://", "//")):
            return match.group(0)
        base = root if target.startswith("/") else folder
        full = os.path.normpath(os.path.join(base, target.lstrip("/")))
        if not os.path.exists(full):
            return match.group(0)
        changed[0] += 1
        return '%s="%s?v=%s"' % (match.group("attr"), target, fingerprint(full))

    updated = ASSET_RE.sub(replace, text)
    if updated != text:
        with open(page_path, "w", encoding="utf-8") as handle:
            handle.write(updated)
    return changed[0]


def main():
    if len(sys.argv) < 2:
        print("Укажите каталог выкладки, например: python stamp_assets.py site")
        return 1
    root = os.path.abspath(sys.argv[1])
    if not os.path.isdir(root):
        print("Каталог не найден: %s" % root)
        return 1

    pages = links = 0
    for folder, _dirs, files in os.walk(root):
        for name in files:
            if not name.endswith(".html"):
                continue
            count = stamp_file(os.path.join(folder, name), root)
            if count:
                pages += 1
                links += count

    print("Отпечатки проставлены: %d ссылок на %d страницах" % (links, pages))
    return 0


if __name__ == "__main__":
    sys.exit(main())
