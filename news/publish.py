"""Сборка выпуска в формат сайта — последний шаг конвейера Ленты.

Превращает issue-*.json, собранный write.py, в news/digest.json — файл, из
которого news/build_feed.py рисует страницы. Здесь же происходит закрытие
недели: то, что было текущим выпуском, уезжает в архив и больше не меняется.

Заодно обновляется служебная память: опубликованное попадает в seen_*, чтобы
на следующей неделе не предлагаться заново, а источники — в
channel_last_featured, чтобы отработал кулдаун.

Запуск:

    python news/publish.py news/.cache/issue-2026-09-08.json
    python news/publish.py <файл> --fresh    # начать архив с нуля
"""

import argparse
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from urllib.parse import urlsplit

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGEST_PATH = os.path.join(BASE, "news", "digest.json")
STATE_PATH = os.path.join(BASE, "news", "state.json")
SOURCES_PATH = os.path.join(BASE, "news", "sources.json")

TYPE_FALLBACK = "отраслевое издание"

MONTHS = ["января", "февраля", "марта", "апреля", "мая", "июня",
          "июля", "августа", "сентября", "октября", "ноября", "декабря"]

# Те же агрегаторы, что в write.py: они не издатели, кулдаун к ним не применяется.
AGGREGATORS = {"arxiv", "hackernews", "reddit"}


def period_label(start, end):
    """«1-7 сентября», «29 августа - 4 сентября»."""
    last = end - timedelta(days=1)
    if start.month == last.month:
        return "%d-%d %s" % (start.day, last.day, MONTHS[start.month - 1])
    return "%d %s - %d %s" % (start.day, MONTHS[start.month - 1], last.day, MONTHS[last.month - 1])


def load_types():
    """Карта «источник -> тип материала» из реестра.

    Тип берется из реестра, а не выводится из домена: домен у источника может
    смениться, а природа его — нет. Пять типов, каждому в верстке отвечает
    своя иконка.
    """
    registry = load_json(SOURCES_PATH, {})
    mapping = {feed["name"]: feed.get("type", TYPE_FALLBACK)
               for feed in registry.get("feeds", [])}
    mapping.update(registry.get("aggregator_types", {}))
    return mapping


def type_of(item, types):
    source = item.get("source") or ""
    if source in types:
        return types[source]
    # Сабреддиты приходят как "reddit/AI_Agents" — тип задан корню.
    root = source.split("/")[0]
    return types.get(root, TYPE_FALLBACK)


def domain_of(url):
    """Домен для служебной строки. У arXiv показываем сам arXiv, а не хост."""
    try:
        host = urlsplit(url).netloc.lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def texts_of(item):
    """Новые поля выпуска. Их может не быть у старых записей — тогда пусто."""
    texts = item.get("тексты") or {}
    return {
        "summary_ru": texts.get("анонс", ""),
        "takeaways": texts.get("выводы", []),
        "expected": texts.get("результат", ""),
        "limits": texts.get("ограничения", ""),
    }


def as_video(item):
    return {
        "video_id": item["video_id"],
        "title": item["title"],
        "channel_title": item.get("channel_title", ""),
        "published_at": item.get("published_at"),
        "thumbnail_url": item.get("thumbnail_url"),
        "language": item.get("language") or "en",
        "view_count": item.get("view_count", 0),
        "duration_sec": item.get("duration_sec") or 0,
        "score": int(round(item.get("итог", 0))),
        **texts_of(item),
    }


def as_web(item, types):
    return {
        "type": type_of(item, types),
        "source": item.get("source", ""),
        "domain": domain_of(item.get("url", "")),
        "title": item["title"],
        "url": item["url"],
        "published_at": item.get("published_at"),
        "score": int(round(item.get("итог", 0))),
        **texts_of(item),
    }


def load_json(path, fallback):
    if not os.path.exists(path):
        return fallback
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as handle:
        json.dump(data, handle, ensure_ascii=False, indent=2)


def main():
    parser = argparse.ArgumentParser(description="Сборка выпуска в digest.json")
    parser.add_argument("issue", help="файл, созданный write.py")
    parser.add_argument("--fresh", action="store_true",
                        help="не переносить прежний выпуск в архив, начать заново")
    parser.add_argument("--week-end", help="конец недели в формате YYYY-MM-DD (по умолчанию сегодня)")
    arguments = parser.parse_args()

    issue = load_json(arguments.issue, None)
    if issue is None:
        print("Файл выпуска не найден: %s" % arguments.issue)
        return 1

    end = (datetime.strptime(arguments.week_end, "%Y-%m-%d").replace(tzinfo=timezone.utc)
           if arguments.week_end else datetime.now(timezone.utc))
    end = end.replace(hour=7, minute=0, second=0, microsecond=0)
    start = end - timedelta(days=7)

    previous = load_json(DIGEST_PATH, {"current": None, "closed": []})
    closed = [] if arguments.fresh else list(previous.get("closed", []))
    number = 1

    if not arguments.fresh and previous.get("current"):
        old = previous["current"]
        if old.get("period_label") != period_label(start, end):
            label = datetime.fromisoformat(old["week_start"]).strftime("%Y-W%V")
            old["html_path"] = "weeks/%s.html" % label
            closed.insert(0, old)
            number = old.get("number", 0) + 1
        else:
            # Пересборка той же недели — номер не меняется.
            number = old.get("number", 1)

    types = load_types()
    digest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "current": {
            "number": number,
            "week_start": start.isoformat(),
            "week_end": end.isoformat(),
            "period_label": period_label(start, end),
            "videos": [as_video(i) for i in issue.get("videos", [])],
            "web": [as_web(i, types) for i in issue.get("web", [])],
        },
        "closed": closed,
    }
    save_json(DIGEST_PATH, digest)

    # Служебная память: что опубликовано — то больше не предлагаем.
    state = load_json(STATE_PATH, {"seen_video_ids": [], "seen_urls": [],
                                   "rejected": [], "channel_last_featured": {}, "carryover": []})
    stamp = datetime.now(timezone.utc).isoformat()
    for item in issue.get("videos", []) + issue.get("web", []):
        if item.get("video_id") and item["video_id"] not in state["seen_video_ids"]:
            state["seen_video_ids"].append(item["video_id"])
        if item.get("url_key") and item["url_key"] not in state["seen_urls"]:
            state["seen_urls"].append(item["url_key"])
        # Кулдаун ставится издателям, но не агрегаторам: Hacker News и arXiv
        # не пишут материалы, а собирают чужие. Заблокировав их на три недели,
        # мы отрезали бы половину источников выпуска на ровном месте.
        owner = item.get("channel_id") or item.get("source")
        if owner and str(owner).split("/")[0] not in AGGREGATORS:
            state.setdefault("channel_last_featured", {})[owner] = stamp
    state["updated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    save_json(STATE_PATH, state)

    print("Выпуск «%s» собран: %d видео, %d веб-материалов, в архиве %d недель."
          % (digest["current"]["period_label"], len(digest["current"]["videos"]),
             len(digest["current"]["web"]), len(closed)))
    print("Память обновлена: %d видео и %d ссылок помечены как опубликованные."
          % (len(state["seen_video_ids"]), len(state["seen_urls"])))
    return 0


if __name__ == "__main__":
    sys.exit(main())
