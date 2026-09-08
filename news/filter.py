"""Механический отсев — первый ярус конвейера Ленты.

Здесь только те проверки, у которых есть однозначный ответ из структурных
данных: длительность, признак трансляции, язык дорожки, повтор уже
опубликованного. Ни одного смыслового суждения — «подкаст или нет»,
«реклама или нет», «вообще про агентов или нет» решает второй ярус моделью.

Правило, по которому проверка попадает сюда: если ответ можно вычислить,
ее нельзя отдавать модели. Модель на вопросе «PT2M47S — это меньше трех
минут?» почти всегда права, а код прав всегда.

Все, что отсеяно, попадает в журнал с причиной — чтобы на вопрос «почему
этого нет в выпуске» отвечали данные, а не память.

Запуск:

    python news/filter.py news/.cache/candidates-2026-09-08.json
    python news/filter.py <файл> --out news/.cache
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE_PATH = os.path.join(BASE, "news", "state.json")

MIN_DURATION_SEC = 180          # ролики короче трех минут не берем
ALLOWED_LANGS = {"ru", "en"}    # язык дорожки; отсутствие языка — не повод отсеивать

# Ниже — не решения, а подсказки для второго яруса. Совпадение метки НЕ
# отсеивает материал: слово "podcast" в заголовке туториала про расшифровку
# подкастов не делает его подкастом. Метки просто едут дальше вместе с
# кандидатом, чтобы модель смотрела внимательнее.
MARKERS = {
    "маркер_подкаст": re.compile(r"\b(podcast|episode\s*\d+|ep\.?\s*\d+|interview|подкаст|интервью|выпуск\s*\d+)\b", re.I),
    "маркер_реклама": re.compile(r"\b(course|masterclass|bootcamp|enroll|discount|coupon|promo\s?code|link in (bio|description)|курс|вебинар|скидк|промокод)\b", re.I),
    "маркер_новости": re.compile(r"\b(news|weekly (recap|roundup|digest)|this week in|top \d+|новости|дайджест)\b", re.I),
    "маркер_шортс": re.compile(r"#shorts?\b", re.I),
}


def load_state():
    """Служебная память. Отсутствие файла — нормальный первый запуск."""
    if not os.path.exists(STATE_PATH):
        return {"seen_video_ids": [], "seen_urls": [], "channel_last_featured": {}, "carryover": []}
    with open(STATE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def language_of(item):
    value = (item.get("language") or "").lower()
    return value.split("-")[0] if value else ""


def check(item, state, now):
    """Возвращает причину отсева или None, если материал проходит дальше.

    Порядок проверок — от самой дешевой и бесспорной к более тонкой.
    """
    seen_ids = set(state.get("seen_video_ids", []))
    seen_urls = set(state.get("seen_urls", []))
    rejected = {entry["url"] for entry in state.get("rejected", []) if entry.get("url")}

    if item.get("video_id") and item["video_id"] in seen_ids:
        return "уже публиковалось"
    if item.get("url_key") in seen_urls:
        return "уже публиковалось"
    if item.get("url_key") in rejected:
        # Забраковано вручную. Отсекаем здесь, на самом дешевом ярусе, чтобы
        # не платить за классификацию и оценку того, что уже решено.
        return "забраковано вручную"
    if not item.get("title"):
        return "нет заголовка"
    if not item.get("url"):
        return "нет ссылки"

    if item["kind"] == "video":
        if item.get("is_live"):
            return "трансляция"
        duration = item.get("duration_sec")
        if duration is None:
            return "неизвестна длительность"
        if duration < MIN_DURATION_SEC:
            return "короче %d минут" % (MIN_DURATION_SEC // 60)
        language = language_of(item)
        # Пустой язык не отсеиваем: YouTube проставляет его далеко не всем,
        # и отбрасывать по отсутствию метки значило бы терять нормальные ролики.
        if language and language not in ALLOWED_LANGS:
            return "язык дорожки: %s" % language

    published = item.get("published_at")
    if published:
        try:
            when = datetime.fromisoformat(published)
            if when > now:
                return "дата публикации в будущем"
        except ValueError:
            pass

    return None


def mark(item):
    """Проставляет подсказки для второго яруса. Ничего не отсеивает."""
    haystack = "%s %s" % (item.get("title", ""), item.get("description", ""))
    flags = [name for name, pattern in MARKERS.items() if pattern.search(haystack)]
    if flags:
        item["маркеры"] = flags
    return item


def run(items, state):
    kept, dropped = [], []
    now = datetime.now(timezone.utc)
    for item in items:
        reason = check(item, state, now)
        if reason:
            dropped.append({"title": item.get("title", "")[:120], "url": item.get("url"),
                            "source": item.get("source"), "reason": reason})
        else:
            kept.append(mark(item))
    return kept, dropped


def print_report(kept, dropped, total):
    counts = {}
    for entry in dropped:
        counts[entry["reason"]] = counts.get(entry["reason"], 0) + 1

    print()
    print("=" * 68)
    print("ЯРУС 1 — МЕХАНИЧЕСКИЙ ОТСЕВ")
    print("=" * 68)
    print()
    print("На входе:  %4d" % total)
    print("Отсеяно:   %4d" % len(dropped))
    for reason, count in sorted(counts.items(), key=lambda pair: -pair[1]):
        print("   %-32s %4d" % (reason, count))
    print("Прошло:    %4d" % len(kept))
    print("   видео:  %4d" % sum(1 for i in kept if i["kind"] == "video"))
    print("   веб:    %4d" % sum(1 for i in kept if i["kind"] == "web"))

    flagged = {}
    for item in kept:
        for flag in item.get("маркеры", []):
            flagged[flag] = flagged.get(flag, 0) + 1
    if flagged:
        print()
        print("Подсказки, переданные второму ярусу (не отсев):")
        for name, count in sorted(flagged.items(), key=lambda pair: -pair[1]):
            print("   %-32s %4d" % (name, count))
    print()


def main():
    parser = argparse.ArgumentParser(description="Механический отсев кандидатов")
    parser.add_argument("candidates", help="файл, созданный collect.py")
    parser.add_argument("--out", help="каталог для сохранения результата и журнала отсева")
    arguments = parser.parse_args()

    with open(arguments.candidates, "r", encoding="utf-8") as handle:
        data = json.load(handle)

    state = load_state()
    kept, dropped = run(data["items"], state)
    print_report(kept, dropped, len(data["items"]))

    if arguments.out:
        os.makedirs(arguments.out, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(os.path.join(arguments.out, "filtered-%s.json" % stamp), "w", encoding="utf-8") as handle:
            json.dump({"items": kept}, handle, ensure_ascii=False, indent=2)
        with open(os.path.join(arguments.out, "dropped-tier1-%s.json" % stamp), "w", encoding="utf-8") as handle:
            json.dump({"dropped": dropped}, handle, ensure_ascii=False, indent=2)
        print("Сохранено: filtered-%s.json (%d) и dropped-tier1-%s.json (%d)"
              % (stamp, len(kept), stamp, len(dropped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
