# -*- coding: utf-8 -*-
"""База знаний источников: PDF и извлеченный текст в R2, оглавления в репозитории.

Репозиторий публичный, поэтому содержимое источников в него не попадает —
только оглавления: заголовки разделов и номера страниц. По ним агент решает,
какие куски текста забрать из R2, а их изменение показывает, что источник
обновился.

Два способа положить источник в базу.

Основной — бросить PDF в бакет через панель Cloudflare. Имя файла при этом
служит идентификатором источника: lanham.pdf даст источник lanham. Дальше
разбором занимается GitHub Actions, запуская этот скрипт так:

    python sources/sync.py --from-bucket

Он находит в бакете PDF, для которых оглавления еще нет или которые
перезалили, скачивает их, извлекает текст обратно в R2 и записывает
оглавления в репозиторий.

Запасной — разобрать файл, лежащий на диске рядом с репозиторием. Путь
берется из поля file в kb/manifest.json:

    python sources/sync.py              — все источники с файлом
    python sources/sync.py lanham       — один источник
    python sources/sync.py --outline    — только оглавления, без обращения к R2
    python sources/sync.py --no-raw     — не заливать сам PDF, только текст

Доступы берутся из окружения или из файла .env в корне:
    R2_ACCOUNT_ID, R2_ACCESS_KEY_ID, R2_SECRET_ACCESS_KEY, R2_BUCKET
"""

import io
import json
import os
import re
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(BASE, "kb", "manifest.json")
OUTLINE_DIR = os.path.join(BASE, "sources", "outline")

PAGE_MARK = "=== СТРАНИЦА %d ==="
RAW_PREFIX = "raw/"
ID_SHAPE = re.compile(r"^[a-z0-9][a-z0-9_-]*$")
# Регистр в имени файла роли не играет: Infante.pdf и infante.pdf дают infante.


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


def manifest_sources():
    with io.open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)["sources"]


def sources_with_files(only=None):
    out = []
    for source in manifest_sources():
        if not source.get("file"):
            continue
        if only and source["id"] != only:
            continue
        out.append(source)
    if only and not out:
        raise SystemExit("нет источника с файлом: %s" % only)
    return out


def read_pdf(path_or_stream):
    from pypdf import PdfReader

    return PdfReader(path_or_stream)


def build_outline(reader, source_id, title):
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
        "id": source_id,
        "title": title,
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


def outline_path(source_id):
    return os.path.join(OUTLINE_DIR, "%s.json" % source_id)


def write_outline(outline):
    path = outline_path(outline["id"])
    with io.open(path, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(outline, ensure_ascii=False, indent=2) + "\n")
    print("      оглавление: %d разделов, %d страниц" % (len(outline["sections"]), outline["pages"]))


def known_version(source_id):
    """Метка версии файла, с которой было построено имеющееся оглавление."""
    path = outline_path(source_id)
    if not os.path.exists(path):
        return None
    try:
        with io.open(path, encoding="utf-8") as fh:
            return json.load(fh).get("etag")
    except Exception:
        return None


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


def bucket_pdfs(client):
    """PDF в бакете: в папке raw/ и в корне, куда файл попадает при перетаскивании.

    Возвращает список записей с ключом объекта, предполагаемым идентификатором
    и меткой версии. Разбирать пригодны не все — имя проверяется отдельно.
    """
    found = []
    token = None
    while True:
        kwargs = {"Bucket": os.environ["R2_BUCKET"]}
        if token:
            kwargs["ContinuationToken"] = token
        response = client.list_objects_v2(**kwargs)
        for obj in response.get("Contents", []):
            key = obj["Key"]
            if not key.lower().endswith(".pdf"):
                continue
            if "/" in key and not key.startswith(RAW_PREFIX):
                continue
            found.append(
                {
                    "key": key,
                    "id": os.path.basename(key)[:-4].lower(),
                    "etag": obj.get("ETag", "").strip('"'),
                }
            )
        if not response.get("IsTruncated"):
            break
        token = response.get("NextContinuationToken")
    return found


def near_miss(name, known_ids):
    """Похоже ли имя на опечатку в известном идентификаторе.

    Чистое имя, которого нет в реестре, обычно означает новый источник.
    Но bbook.pdf при существующем book - это не новый источник, а лишняя
    буква, и заводить по ней вторую запись хуже, чем остановиться.
    """
    import difflib

    return bool(difflib.get_close_matches(name, sorted(known_ids), n=1, cutoff=0.85))


def resolve_id(raw_name, known_ids):
    """Идентификатор источника по имени файла.

    Чистое имя годится как есть: lanham.pdf даст lanham. Если имя содержит
    лишнее, оно сверяется с реестром: "Lanham Micheal.pdf" опознается как
    lanham, потому что ровно один известный источник встречается в имени
    отдельным словом. Двусмысленность идентификатор не дает.
    """
    name = raw_name.lower()
    if ID_SHAPE.match(name):
        return name if name in known_ids or not near_miss(name, known_ids) else None
    words = set(re.split(r"[^a-z0-9]+", name))
    matched = sorted(known_ids & words)
    return matched[0] if len(matched) == 1 else None


def sync_from_bucket(client):
    """Разбирает PDF из бакета: текст обратно в R2, оглавление в репозиторий."""
    titles = {source["id"]: source["title"] for source in manifest_sources()}
    objects = bucket_pdfs(client)

    if not objects:
        print("в бакете нет PDF")
        return 0

    bad_names = []
    need_manifest = []
    stray = []
    done = 0

    for entry in objects:
        source_id = resolve_id(entry["id"], set(titles))

        if source_id is None:
            bad_names.append(entry["key"])
            continue

        if entry["etag"] and entry["etag"] == known_version(source_id):
            print("%-10s без изменений" % source_id)
            continue

        print("%s: %s" % (source_id, entry["key"]))
        body = client.get_object(Bucket=os.environ["R2_BUCKET"], Key=entry["key"])["Body"].read()
        reader = read_pdf(io.BytesIO(body))

        outline = build_outline(reader, source_id, titles.get(source_id, source_id))
        outline["etag"] = entry["etag"]
        write_outline(outline)

        text = build_text(reader)
        put(client, "extracted/%s.txt" % source_id, text.encode("utf-8"), "text/plain; charset=utf-8")

        canonical = "%s%s.pdf" % (RAW_PREFIX, source_id)
        if entry["key"] != canonical:
            client.copy_object(
                Bucket=os.environ["R2_BUCKET"],
                Key=canonical,
                CopySource={"Bucket": os.environ["R2_BUCKET"], "Key": entry["key"]},
            )
            print("      -> %s (копия исходного объекта)" % canonical)
            stray.append(entry["key"])

        if source_id not in titles:
            need_manifest.append(source_id)
        done += 1

    print("\nразобрано: %d" % done)

    if bad_names:
        print("\nимя файла должно быть идентификатором источника: строчные латинские")
        print("буквы, цифры, дефис или подчеркивание, и расширение .pdf. Например")
        print("lanham.pdf. Имя, похожее на известный источник с точностью")
        print("до опечатки, тоже отвергается: bbook при существующем book -")
        print("это лишняя буква, а не новый источник.")
        print("Имя с лишними словами годится, если один")
        print("из известных источников входит в него отдельным словом.")
        print("Переименовать объект в R2 нельзя, такой операции там нет:")
        print("переименуйте файл у себя и залейте заново. Не разобраны:")
        for key in bad_names:
            print("  - %s" % key)

    if stray:
        print("\nэти объекты лежали не на своем месте и скопированы в raw/.")
        print("Исходные копии можно удалить в панели Cloudflare:")
        for key in stray:
            print("  - %s" % key)

    if need_manifest:
        print("\nнет записи в kb/manifest.json — источник разобран, но в сверке")
        print("не участвует, пока его туда не внесли:")
        for source_id in need_manifest:
            print("  - %s" % source_id)

    return 1 if (bad_names or need_manifest) else 0


def sync_from_disk(only, outline_only, skip_raw):
    """Запасной путь: разбор файла, лежащего на диске рядом с репозиторием."""
    client = None if outline_only else r2_client()

    for source in sources_with_files(only):
        path = os.path.join(BASE, source["file"])
        if not os.path.exists(path):
            print("%-10s файла нет на диске: %s" % (source["id"], source["file"]))
            continue

        print("%s: %s" % (source["id"], source["file"]))
        reader = read_pdf(path)

        write_outline(build_outline(reader, source["id"], source["title"]))

        if outline_only:
            continue

        text = build_text(reader)
        put(client, "extracted/%s.txt" % source["id"], text.encode("utf-8"), "text/plain; charset=utf-8")

        if not skip_raw:
            with open(path, "rb") as fh:
                put(client, "%s%s.pdf" % (RAW_PREFIX, source["id"]), fh.read(), "application/pdf")

    return 0


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    from_bucket = "--from-bucket" in sys.argv
    outline_only = "--outline" in sys.argv
    skip_raw = "--no-raw" in sys.argv

    load_env()
    os.makedirs(OUTLINE_DIR, exist_ok=True)

    if from_bucket:
        code = sync_from_bucket(r2_client())
    else:
        code = sync_from_disk(args[0] if args else None, outline_only, skip_raw)

    sys.exit(code)


if __name__ == "__main__":
    main()
