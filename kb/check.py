"""Проверка базы перед публикацией.

Запуск из корня воркспейса:
    python kb/check.py

Ничего не правит, только проверяет. Ненулевой код выхода — публикация
останавливается (см. .github/workflows/deploy.yml). Список проверок
описан в NOTES.md, раздел «Жесткие правила подачи».
"""

import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

TEXT_EXT = (".html", ".md", ".py", ".json", ".css", ".js")
SKIP_DIRS = {".git", "__pycache__", "node_modules"}

# Страницы, которые видит ученик, — источники там не называются никогда.
PUBLIC_DIRS = ("lessons", "articles", "reference")
FORBIDDEN_IN_PUBLIC = re.compile(
    r"IBM|Microsoft|Grootendorst|Цзяншу|n8n|Zapier|Make\.com",
    re.IGNORECASE,
)

YO = chr(1105) + chr(1025)  # буква "е с двумя точками", строчная и прописная


def walk_text_files(root=BASE):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for name in filenames:
            if os.path.splitext(name)[1].lower() in TEXT_EXT:
                yield os.path.join(dirpath, name)


def rel(path):
    return os.path.relpath(path, BASE).replace("\\", "/")


def check_yo():
    problems = []
    for path in walk_text_files():
        with open(path, "r", encoding="utf-8") as fh:
            text = fh.read()
        count = sum(text.count(ch) for ch in YO)
        if count:
            problems.append(f"{rel(path)}: запрещенная буква встречается {count} раз")
    return problems


def check_forbidden_names():
    problems = []
    for public in PUBLIC_DIRS:
        folder = os.path.join(BASE, public)
        if not os.path.isdir(folder):
            continue
        for dirpath, _, filenames in os.walk(folder):
            for name in filenames:
                if not name.endswith(".html"):
                    continue
                path = os.path.join(dirpath, name)
                with open(path, "r", encoding="utf-8") as fh:
                    text = fh.read()
                found = sorted(set(FORBIDDEN_IN_PUBLIC.findall(text)))
                if found:
                    problems.append(f"{rel(path)}: упомянут источник {found}")
    return problems


LINK_CHECK_TARGETS = PUBLIC_DIRS + ("kb", "news", "hub", "index.html")


def check_internal_links():
    problems = []
    link_re = re.compile(r'(?:href|src)="([^"#][^"]*)"')
    for public in LINK_CHECK_TARGETS:
        base_path = os.path.join(BASE, public)
        paths = []
        if os.path.isfile(base_path):
            paths = [base_path]
        elif os.path.isdir(base_path):
            paths = [
                os.path.join(base_path, n)
                for n in os.listdir(base_path)
                if n.endswith(".html")
            ]
        for path in paths:
            folder = os.path.dirname(path)
            with open(path, "r", encoding="utf-8") as fh:
                text = fh.read()
            for target in link_re.findall(text):
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                if target.startswith("/"):
                    # Абсолютный путь от корня сайта — навигация в шапке.
                    resolved = os.path.normpath(os.path.join(BASE, target.lstrip("/")))
                else:
                    resolved = os.path.normpath(os.path.join(folder, target))
                # .htaccess на сервере дописывает .html к путям без расширения,
                # поэтому ссылка на "resolved" без файла, но с "resolved.html",
                # тоже рабочая.
                if not os.path.exists(resolved) and not os.path.exists(resolved + ".html"):
                    problems.append(f"{rel(path)}: битая ссылка {target}")
    return problems


def check_manifest_paths():
    import json

    problems = []
    manifest_path = os.path.join(BASE, "kb", "manifest.json")
    with open(manifest_path, "r", encoding="utf-8") as fh:
        manifest = json.load(fh)
    for node in manifest.get("nodes", []):
        if node.get("status") != "published":
            continue
        node_path = node.get("path")
        if not node_path:
            problems.append(f"манифест: узел {node.get('id')} без пути")
            continue
        full = os.path.join(BASE, node_path)
        if not os.path.exists(full):
            problems.append(
                f"манифест: узел {node.get('id')} указывает на {node_path}, файла нет"
            )
    return problems


def main():
    checks = [
        ("запрещенная буква", check_yo),
        ("упоминание источников на публичных страницах", check_forbidden_names),
        ("внутренние ссылки", check_internal_links),
        ("пути в манифесте", check_manifest_paths),
    ]

    all_problems = []
    for title, fn in checks:
        problems = fn()
        status = "чисто" if not problems else f"{len(problems)} проблем"
        print(f"[{status}] {title}")
        all_problems.extend(problems)

    if all_problems:
        print("\nНайденные проблемы:")
        for p in all_problems:
            print(f"  - {p}")
        return 1

    print("\nВсе проверки пройдены.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
