# -*- coding: utf-8 -*-
"""Синхронизация базы знаний: PDF и извлеченный текст в R2, оглавления в репозиторий.

Репозиторий публичный, поэтому содержимое источников в него не попадает —
только оглавления: заголовки разделов и номера страниц. По ним агент решает,
какие куски текста забрать из R2, а их изменение показывает, что источник
обновился.

Запуск из корня воркспейса:
    python sources/sync.py              — все источники с файлом
    python sources/sync.py lanham       — один источник
    python sources/sync.py --outline    — только оглавления, без обращения к R2

Доступы берутся из окружения или из файла .env рядом с этим скриптом:
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

import io
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(BASE, "kb", "manifest.json")
OUTLINE_DIR = os.path.join(BASE, "sources", "outline")

PAGE_MARK = "=== СТРАНИЦА %d ==="


def load_env():
    """Читает .env из корня, не перетирая уже заданное в окружении."""
    path = os.path.join(BASE, ".env")
    if not os.path.exists(path):
        return
    with io.open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def sources_with_files(only=None):
    with io.open(MANIFEST, encoding="utf-8") as fh:
        manifest = json.load(fh)
    out = []
    for source in manifest["sources"]:
        if not source.get("file"):
            continue
        if only and source["id"] != only:
            continue
        out.append(source)
    if only and not out:
        raise SystemExit("нет источника с файлом: %s" % only)
    return out


def read_pdf(path):
    from pypdf import PdfReader

    return PdfReader(path)


def build_outline(reader, source):
    """Карта разделов: заголовок, страница, уровень вложенности."""
    items = []

    def walk(entries, level=0):
        for entry in entries:
            if isinstance(entry, list):
                walk(entry, level + 1)
                continue
            try:
                page = reader.get_destination_page_number(entry) + 1
            except Exception:
                continue
            items.append({"title": str(entry.title).strip(), "page": page, "level": level})

    try:
        walk(reader.outline)
    except Exception:
        pass

    return {
        "id": source["id"],
        "title": source["title"],
        "pages": len(reader.pages),
        "sections": items,
    }


def build_text(reader):
    """Весь текст с разметкой страниц — по ней режутся куски из оглавления."""
    chunks = []
    for index, page in enumerate(reader.pages, start=1):
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""
        chunks.append(PAGE_MARK % index)
        chunks.append(text)
    return "\n".join(chunks)


def r2_client():
    import boto3

    missing = [
        name
        for name in ("R2_ACCOUNT_ID", "R2_ACCESS_KEY_ID", "R2_SECRET_ACCESS_KEY", "R2_BUCKET")
        if not os.environ.get(name)
    ]
    if missing:
        raise SystemExit(
            "не заданы доступы: %s. Положите их в .env в корне (файл в .gitignore)."
            % ", ".join(missing)
        )

    return boto3.client(
        "s3",
        endpoint_url="https://%s.r2.cloudflarestorage.com" % os.environ["R2_ACCOUNT_ID"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )


def put(client, key, body, content_type):
    client.put_object(
        Bucket=os.environ["R2_BUCKET"],
        Key=key,
        Body=body,
        ContentType=content_type,
    )
    print("      -> %s (%.1f МБ)" % (key, len(body) / 1048576.0))


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    outline_only = "--outline" in sys.argv
    skip_raw = "--no-raw" in sys.argv

    load_env()
    os.makedirs(OUTLINE_DIR, exist_ok=True)

    client = None if outline_only else r2_client()

    for source in sources_with_files(args[0] if args else None):
        path = os.path.join(BASE, source["file"])
        if not os.path.exists(path):
            print("%-8s файла нет на диске: %s" % (source["id"], source["file"]))
            continue

        print("%s: %s" % (source["id"], source["file"]))
        reader = read_pdf(path)

        outline = build_outline(reader, source)
        outline_path = os.path.join(OUTLINE_DIR, "%s.json" % source["id"])
        with io.open(outline_path, "w", encoding="utf-8", newline="\n") as fh:
            fh.write(json.dumps(outline, ensure_ascii=False, indent=2) + "\n")
        print("      оглавление: %d разделов, %d страниц" % (len(outline["sections"]), outline["pages"]))

        if outline_only:
            continue

        text = build_text(reader)
        put(client, "extracted/%s.txt" % source["id"], text.encode("utf-8"), "text/plain; charset=utf-8")

        if not skip_raw:
            with open(path, "rb") as fh:
                put(client, "raw/%s.pdf" % source["id"], fh.read(), "application/pdf")


if __name__ == "__main__":
    main()
