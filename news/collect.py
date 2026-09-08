"""Сбор кандидатов для Ленты — первый ярус конвейера.

Ходит по источникам из news/sources.json и складывает всё найденное в единый
плоский список кандидатов. Ничего не оценивает и ничего не отсеивает по смыслу —
это работа следующих ярусов (filter.py, judge.py).

Принципы, заложенные в этот файл:

1. Только стандартная библиотека. Никаких pip install — в GitHub Actions нечему
   ломаться и нечего обновлять.
2. Каждый источник изолирован. Упал arXiv — в отчёте строка про arXiv, остальные
   двенадцать источников отработали. Ни одно исключение не роняет прогон целиком.
3. Квота YouTube считается заранее и ограничивается конфигом. Скрипт
   останавливает поиск сам, не доводя API до отказа.
4. Сухой прогон (по умолчанию) ничего не пишет на диск — только печатает отчёт.

Запуск из корня репозитория:

    python news/collect.py                    # сухой прогон, отчёт в консоль
    python news/collect.py --out news/.cache  # то же плюс сохранение кандидатов
    python news/collect.py --only youtube     # один источник (для отладки)

Ключ YouTube берётся из переменной окружения YOUTUBE_API_KEY. Без него
YouTube-часть пропускается, веб-часть работает — она ключей не требует.
"""

import argparse
import json
import os
import re
import sys
import time
import traceback
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CONFIG_PATH = os.path.join(BASE, "news", "sources.json")

UA = "agenticbase-digest/1.0 (+https://agenticbase.ru)"
TIMEOUT = 25

# Reddit (и не он один) отвечает 429 на запрос без заголовков Accept — для их
# защиты это признак примитивного скрипта. Заголовки честные, User-Agent
# по-прежнему наш и представляется.
DEFAULT_HEADERS = {
    "User-Agent": UA,
    "Accept": "application/atom+xml,application/rss+xml,application/xml;q=0.9,application/json;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

# Стоимость операций YouTube Data API v3 в единицах квоты. Дневной лимит — 10 000.
QUOTA_SEARCH = 100
QUOTA_VIDEOS = 1
QUOTA_CHANNELS = 1
QUOTA_PLAYLIST_ITEMS = 1


# --------------------------------------------------------------------------
# Инфраструктура: сеть, квота, изоляция источников
# --------------------------------------------------------------------------

class Quota:
    """Счётчик квоты YouTube с жёстким потолком."""

    def __init__(self, limit=9000):
        self.used = 0
        self.limit = limit

    def can(self, cost):
        return self.used + cost <= self.limit

    def spend(self, cost):
        self.used += cost


def fetch(url, headers=None, attempts=3):
    """GET с User-Agent, таймаутом и повтором на временных отказах.

    Повторяем только то, что имеет смысл повторять: 429 (лимит запросов) и 5xx.
    На 403/404 повтор бессмысленен — отдаём ошибку сразу, пусть источник
    честно попадёт в отчёт как сломанный.
    """
    request = urllib.request.Request(url, headers={**DEFAULT_HEADERS, **(headers or {})})
    delay = 5
    for attempt in range(attempts):
        try:
            with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
                return response.read()
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            wait = int(error.headers.get("Retry-After") or 0) or delay
            time.sleep(min(wait, 60))
            delay *= 3
        except urllib.error.URLError:
            if attempt == attempts - 1:
                raise
            time.sleep(delay)
            delay *= 3


def fetch_json(url):
    return json.loads(fetch(url).decode("utf-8"))


class Report:
    """Отчёт о прогоне: что дал каждый источник и где что упало."""

    def __init__(self):
        self.rows = []
        self.errors = []

    def ok(self, source, found, note=""):
        self.rows.append((source, found, note))

    def fail(self, source, error):
        self.rows.append((source, 0, "ОШИБКА"))
        self.errors.append((source, error))


def isolated(report, name):
    """Обёртка: любое исключение внутри источника не роняет прогон.

    При успехе возвращает список, при падении — None. Вызывающий код по None
    понимает, что строку в отчёт уже добавил сам обработчик ошибки, и второй
    раз не пишет.
    """
    def wrapper(function, *args, **kwargs):
        try:
            return function(*args, **kwargs)
        except Exception as error:  # noqa: BLE001 — тут ловим намеренно всё
            report.fail(name, "%s: %s" % (type(error).__name__, error))
            if os.environ.get("COLLECT_DEBUG"):
                traceback.print_exc()
            return None
    return wrapper


# --------------------------------------------------------------------------
# Общие утилиты
# --------------------------------------------------------------------------

ISO_DURATION = re.compile(r"P(?:(\d+)D)?T?(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?")


def duration_seconds(iso_value):
    """PT2M47S -> 167. Возвращает None, если разобрать не удалось."""
    if not iso_value:
        return None
    match = ISO_DURATION.fullmatch(iso_value)
    if not match:
        return None
    days, hours, minutes, seconds = (int(part) if part else 0 for part in match.groups())
    return days * 86400 + hours * 3600 + minutes * 60 + seconds


def parse_date(value):
    """Разбирает даты из RSS/Atom/API в aware datetime. None, если не вышло."""
    if not value:
        return None
    value = value.strip()
    formats = [
        "%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%M:%S.%fZ",
        "%a, %d %b %Y %H:%M:%S %z", "%a, %d %b %Y %H:%M:%S %Z",
        "%Y-%m-%d %H:%M:%S", "%Y-%m-%d",
    ]
    for fmt in formats:
        try:
            parsed = datetime.strptime(value.replace("Z", "+0000") if fmt.endswith("%z") else value, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    return None


def normalize_url(url):
    """Убирает utm-метки и якоря, чтобы один материал не считался дважды."""
    try:
        parts = urllib.parse.urlsplit(url)
    except ValueError:
        return url
    query = [
        (key, value) for key, value in urllib.parse.parse_qsl(parts.query)
        if not key.lower().startswith(("utm_", "fbclid", "gclid", "ref"))
    ]
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urllib.parse.urlunsplit((parts.scheme, host, parts.path.rstrip("/"), urllib.parse.urlencode(query), ""))


def strip_tags(text):
    return re.sub(r"<[^>]+>", " ", text or "").replace("&nbsp;", " ").strip()


def candidate(kind, source, title, url, published, **extra):
    item = {
        "kind": kind,                     # video | web
        "source": source,
        "title": (title or "").strip(),
        "url": url,
        "url_key": normalize_url(url),
        "published_at": published.isoformat() if published else None,
    }
    item.update(extra)
    return item


# --------------------------------------------------------------------------
# YouTube
# --------------------------------------------------------------------------

# Причины 403, означающие «на сегодня хватит», а не «сломано».
QUOTA_REASONS = {"quotaExceeded", "dailyLimitExceeded", "rateLimitExceeded", "userRateLimitExceeded"}


def youtube_error_reason(error):
    """Достаёт машинную причину отказа из тела ответа Google.

    Google кладёт в 403 поле reason: quotaExceeded, accessNotConfigured,
    ipRefererBlocked и так далее. Различать их обязательно — иначе невключённый
    в проекте API выглядит как исчерпанный лимит, и отчёт врёт.
    """
    try:
        body = json.loads(error.read().decode("utf-8"))
        return body.get("error", {}).get("errors", [{}])[0].get("reason", "")
    except Exception:  # noqa: BLE001 — диагностика не должна ронять прогон
        return ""


def youtube_search(api_key, config, quota, since):
    """Поиск по матрице запросов. Возвращает список id роликов."""
    video_ids = []
    seen = set()
    queries = config["queries"][: config.get("search_query_limit", 40)]
    published_after = since.strftime("%Y-%m-%dT%H:%M:%SZ")

    for query in queries:
        if not quota.can(QUOTA_SEARCH):
            break
        params = urllib.parse.urlencode({
            "part": "id",
            "q": query,
            "type": "video",
            "order": "relevance",
            "maxResults": config.get("results_per_query", 25),
            "publishedAfter": published_after,
            "key": api_key,
        })
        try:
            data = fetch_json("https://www.googleapis.com/youtube/v3/search?" + params)
        except urllib.error.HTTPError as error:
            # 403 у YouTube означает разное. Кончилась квота — молча
            # останавливаемся, это штатный конец рабочего дня. Всё остальное
            # (API не включён в проекте, ключ ограничен по адресу) — настоящая
            # поломка, и она должна попасть в отчёт своими словами, а не
            # притвориться исчерпанным лимитом.
            reason = youtube_error_reason(error) if error.code == 403 else ""
            if reason in QUOTA_REASONS and reason:
                quota.spend(quota.limit)
                break
            if reason:
                raise RuntimeError("YouTube отказал, причина «%s» (запрос: %s)" % (reason, query))
            raise
        quota.spend(QUOTA_SEARCH)
        for entry in data.get("items", []):
            video_id = entry.get("id", {}).get("videoId")
            if video_id and video_id not in seen:
                seen.add(video_id)
                video_ids.append(video_id)
        time.sleep(0.1)
    return video_ids


def youtube_enrich(api_key, video_ids, quota):
    """videos.list пачками по 50 — длительность, просмотры, язык, канал."""
    results = []
    for start in range(0, len(video_ids), 50):
        chunk = video_ids[start:start + 50]
        if not quota.can(QUOTA_VIDEOS):
            break
        params = urllib.parse.urlencode({
            "part": "snippet,contentDetails,statistics,liveStreamingDetails",
            "id": ",".join(chunk),
            "key": api_key,
        })
        data = fetch_json("https://www.googleapis.com/youtube/v3/videos?" + params)
        quota.spend(QUOTA_VIDEOS)

        for entry in data.get("items", []):
            snippet = entry.get("snippet", {})
            stats = entry.get("statistics", {})
            details = entry.get("contentDetails", {})
            published = parse_date(snippet.get("publishedAt"))
            results.append(candidate(
                "video",
                "youtube",
                snippet.get("title"),
                "https://www.youtube.com/watch?v=" + entry["id"],
                published,
                video_id=entry["id"],
                channel_title=snippet.get("channelTitle"),
                channel_id=snippet.get("channelId"),
                description=(snippet.get("description") or "")[:1500],
                language=snippet.get("defaultAudioLanguage") or snippet.get("defaultLanguage"),
                duration_sec=duration_seconds(details.get("duration")),
                view_count=int(stats.get("viewCount", 0) or 0),
                like_count=int(stats.get("likeCount", 0) or 0),
                comment_count=int(stats.get("commentCount", 0) or 0),
                is_live=bool(entry.get("liveStreamingDetails")) or snippet.get("liveBroadcastContent") not in (None, "none"),
                thumbnail_url=(snippet.get("thumbnails", {}).get("high") or {}).get("url"),
            ))
        time.sleep(0.1)
    return results


# --------------------------------------------------------------------------
# Веб-источники
# --------------------------------------------------------------------------

def parse_feed(raw, source_name):
    """Разбирает RSS 2.0 и Atom одним кодом — нам нужны только четыре поля."""
    root = ET.fromstring(raw)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    items = []

    # RSS 2.0
    for node in root.findall(".//item"):
        link = (node.findtext("link") or "").strip()
        if not link:
            continue
        items.append(candidate(
            "web", source_name,
            node.findtext("title"),
            link,
            parse_date(node.findtext("pubDate") or node.findtext("{http://purl.org/dc/elements/1.1/}date")),
            description=strip_tags(node.findtext("description"))[:1500],
        ))

    # Atom
    for node in root.findall(".//atom:entry", namespace):
        link_node = node.find("atom:link[@rel='alternate']", namespace)
        if link_node is None:
            link_node = node.find("atom:link", namespace)
        link = (link_node.get("href") if link_node is not None else "") or ""
        if not link:
            continue
        summary = node.findtext("atom:summary", default="", namespaces=namespace) \
            or node.findtext("atom:content", default="", namespaces=namespace)
        items.append(candidate(
            "web", source_name,
            node.findtext("atom:title", default="", namespaces=namespace),
            link,
            parse_date(node.findtext("atom:updated", default="", namespaces=namespace)
                       or node.findtext("atom:published", default="", namespaces=namespace)),
            description=strip_tags(summary)[:1500],
        ))
    return items


def collect_feed(feed, keywords, since):
    """Одна лента. Фильтр по ключевым словам — механический, чтобы не тащить
    в конвейер весь блог целиком: это отбор по теме, а не по качеству."""
    items = parse_feed(fetch(feed["url"]), feed["name"])
    kept = []
    for item in items:
        published = parse_date(item["published_at"])
        if published and published < since:
            continue
        haystack = (item["title"] + " " + item.get("description", "")).lower()
        if any(word in haystack for word in keywords):
            kept.append(item)
    return kept


def collect_hackernews(config, since):
    """Algolia API — открытый, без ключа. Берём истории выше порога очков."""
    results = []
    seen = set()
    timestamp = int(since.timestamp())
    for query in config["queries"]:
        params = urllib.parse.urlencode({
            "query": query,
            "tags": "story",
            "numericFilters": "created_at_i>%d,points>=%d" % (timestamp, config["min_points"]),
            "hitsPerPage": 50,
        })
        data = fetch_json("https://hn.algolia.com/api/v1/search?" + params)
        for hit in data.get("hits", []):
            url = hit.get("url") or ("https://news.ycombinator.com/item?id=%s" % hit.get("objectID"))
            if url in seen:
                continue
            seen.add(url)
            results.append(candidate(
                "web", "hackernews",
                hit.get("title"), url,
                parse_date(hit.get("created_at")),
                description="",
                points=hit.get("points", 0),
                comments=hit.get("num_comments", 0),
                discussion_url="https://news.ycombinator.com/item?id=%s" % hit.get("objectID"),
            ))
        time.sleep(0.2)
    return results


def collect_arxiv(config, since):
    """Atom-выдача arXiv. Ключей не требует.

    Булеву логику arXiv разбирает вольно: скобки и AND между группами он
    фактически игнорирует, из-за чего запрос про агентов притаскивает работы
    о распространении болезней в лагерях беженцев. Поэтому запрос к API
    держим широким (по категориям), а отбор по теме делаем здесь — обычным
    сопоставлением слов, которое можно прочитать и проверить.
    """
    params = urllib.parse.urlencode({
        "search_query": config["search"],
        "sortBy": "submittedDate",
        "sortOrder": "descending",
        "max_results": config.get("max_results", 200),
    })
    raw = fetch("http://export.arxiv.org/api/query?" + params)
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    root = ET.fromstring(raw)
    keywords = [word.lower() for word in config.get("keywords", [])]
    results = []

    for node in root.findall("atom:entry", namespace):
        published = parse_date(node.findtext("atom:published", default="", namespaces=namespace))
        if published and published < since:
            continue
        title = " ".join((node.findtext("atom:title", default="", namespaces=namespace) or "").split())
        summary = " ".join((node.findtext("atom:summary", default="", namespaces=namespace) or "").split())
        if keywords and not any(word in (title + " " + summary).lower() for word in keywords):
            continue
        results.append(candidate(
            "web", "arxiv", title,
            node.findtext("atom:id", default="", namespaces=namespace),
            published,
            description=summary[:1500],
        ))
    return results


HREF = re.compile(r'href="(https?://[^"]+)"')


def collect_reddit(config, since):
    """RSS сабреддита.

    JSON-эндпойнт Reddit возвращает 403 любому серверному клиенту независимо от
    User-Agent, RSS отдаётся свободно. Плата за это — из ленты не приходит счёт
    голосов, поэтому порога по очкам нет: выдача /top за неделю уже отсортирована
    по популярности, берём первые limit записей.

    В теле записи Reddit кладёт ссылку на внешний материал. Если она есть —
    кандидатом становится сам материал, а обсуждение остаётся справочной ссылкой.
    """
    namespace = {"atom": "http://www.w3.org/2005/Atom"}
    results = []
    limit = config.get("limit", 25)

    for sub in config["subreddits"]:
        url = "https://www.reddit.com/r/%s/top/.rss?t=%s" % (sub, config.get("period", "week"))
        root = ET.fromstring(fetch(url))
        taken = 0
        for node in root.findall("atom:entry", namespace):
            if taken >= limit:
                break
            link_node = node.find("atom:link", namespace)
            permalink = link_node.get("href") if link_node is not None else ""
            if not permalink:
                continue
            published = parse_date(node.findtext("atom:updated", default="", namespaces=namespace))
            if published and published < since:
                continue

            content = node.findtext("atom:content", default="", namespaces=namespace) or ""
            external = next(
                (href for href in HREF.findall(content)
                 if "reddit.com" not in href and "redd.it" not in href),
                None,
            )
            results.append(candidate(
                "web", "reddit/" + sub,
                node.findtext("atom:title", default="", namespaces=namespace),
                external or permalink,
                published,
                description="",
                discussion_url=permalink,
            ))
            taken += 1
        time.sleep(1.0)
    return results


# --------------------------------------------------------------------------
# Сборка и отчёт
# --------------------------------------------------------------------------

def dedupe(items):
    seen = set()
    unique = []
    for item in items:
        key = item.get("video_id") or item["url_key"]
        if key in seen:
            continue
        seen.add(key)
        unique.append(item)
    return unique


def print_report(report, items, quota, since):
    videos = [item for item in items if item["kind"] == "video"]
    web = [item for item in items if item["kind"] == "web"]

    print()
    print("=" * 72)
    print("СБОР КАНДИДАТОВ — окно с %s" % since.strftime("%Y-%m-%d"))
    print("=" * 72)
    print()
    print("%-28s %8s   %s" % ("Источник", "Найдено", "Примечание"))
    print("-" * 72)
    for source, found, note in report.rows:
        print("%-28s %8d   %s" % (source[:28], found, note))
    print("-" * 72)
    print("%-28s %8d" % ("ВСЕГО (после дедупликации)", len(items)))
    print("%-28s %8d" % ("  из них видео", len(videos)))
    print("%-28s %8d" % ("  из них веб", len(web)))
    print()
    print("Квота YouTube: израсходовано %d из %d единиц дневного лимита 10000."
          % (quota.used, quota.limit))

    if videos:
        channels = {}
        for item in videos:
            name = item.get("channel_title") or "?"
            channels[name] = channels.get(name, 0) + 1
        top = sorted(channels.items(), key=lambda pair: -pair[1])[:15]
        print()
        print("Каналы, встретившиеся чаще всего (заготовка белого списка):")
        for name, count in top:
            print("   %3d  %s" % (count, name))

    if report.errors:
        print()
        print("Источники с ошибками:")
        for source, error in report.errors:
            print("   %-24s %s" % (source[:24], error))

    print()


def main():
    parser = argparse.ArgumentParser(description="Сбор кандидатов для Ленты")
    parser.add_argument("--out", help="каталог для сохранения кандидатов (по умолчанию ничего не пишется)")
    parser.add_argument("--only", help="обработать только один источник: youtube, feeds, hackernews, arxiv, reddit")
    arguments = parser.parse_args()

    with open(CONFIG_PATH, "r", encoding="utf-8") as handle:
        config = json.load(handle)

    since = datetime.now(timezone.utc) - timedelta(days=config.get("window_days", 8))
    report = Report()
    quota = Quota()
    items = []

    def wanted(name):
        return arguments.only is None or arguments.only == name

    def gather(label, function, *args, note=""):
        """Один источник: выполнить, забрать результат, вписать строку в отчёт."""
        found = isolated(report, label)(function, *args)
        if found is None:          # упал, строка про ошибку уже записана
            return
        items.extend(found)
        report.ok(label, len(found), note)

    # --- YouTube -----------------------------------------------------------
    api_key = os.environ.get("YOUTUBE_API_KEY")
    if wanted("youtube") and config["youtube"].get("enabled"):
        if not api_key:
            report.ok("youtube", 0, "нет YOUTUBE_API_KEY — пропущен")
        else:
            video_ids = isolated(report, "youtube (поиск)")(
                youtube_search, api_key, config["youtube"], quota, since)
            if video_ids:
                gather("youtube", youtube_enrich, api_key, video_ids, quota,
                       note="%d id из поиска" % len(video_ids))
            elif video_ids is not None:
                report.ok("youtube", 0, "поиск не вернул ни одного ролика")

    # --- Ленты -------------------------------------------------------------
    if wanted("feeds"):
        keywords = [word.lower() for word in config.get("feed_keywords", [])]
        for feed in config.get("feeds", []):
            gather(feed["name"], collect_feed, feed, keywords, since)

    # --- Hacker News -------------------------------------------------------
    if wanted("hackernews") and config["hackernews"].get("enabled"):
        gather("hackernews", collect_hackernews, config["hackernews"], since)

    # --- arXiv -------------------------------------------------------------
    if wanted("arxiv") and config["arxiv"].get("enabled"):
        gather("arxiv", collect_arxiv, config["arxiv"], since)

    # --- Reddit ------------------------------------------------------------
    if wanted("reddit") and config["reddit"].get("enabled"):
        gather("reddit", collect_reddit, config["reddit"], since)

    items = dedupe(items)
    print_report(report, items, quota, since)

    if arguments.out:
        os.makedirs(arguments.out, exist_ok=True)
        path = os.path.join(arguments.out, "candidates-%s.json" % datetime.now(timezone.utc).strftime("%Y-%m-%d"))
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({
                "collected_at": datetime.now(timezone.utc).isoformat(),
                "window_start": since.isoformat(),
                "quota_used": quota.used,
                "errors": [{"source": s, "error": e} for s, e in report.errors],
                "items": items,
            }, handle, ensure_ascii=False, indent=2)
        print("Сохранено: %s (%d кандидатов)" % (path, len(items)))

    return 0


if __name__ == "__main__":
    sys.exit(main())
