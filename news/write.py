"""Отбор финалистов и написание текстов — ярус 3б конвейера Ленты.

Делает две вещи, которые дальше уже не переиграть:

1. Отбирает финалистов из оценённого пула. Отбор детерминированный: сортировка
   по итоговому баллу плюс потолки, ниже которых выпуск не имеет права
   перекоситься в одну сторону. Один материал от канала, один от источника,
   отдельный жёсткий потолок для препринтов arXiv — без него AWS с его
   одиннадцатью статьями про собственный AgentCore занял бы четверть выпуска.

2. Пишет для отобранных тексты на самой сильной модели: анонс, три вывода,
   ожидаемый результат применения и ограничения. Это единственное место
   конвейера, где работает Opus, и материалов здесь пара десятков, а не сотни.

Правило про букву «ё» не доверяется модели: запрет стоит в промте И механически
применяется к результату. Мелкое механическое правило нельзя оставлять на
усмотрение — kb/check.py всё равно остановит публикацию, а разбираться придётся
человеку.

Запуск:

    python news/write.py news/.cache/scored-2026-09-08.json --out news/.cache
    python news/write.py <файл> --videos 10 --web 8
"""

import argparse
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone

import anthropic

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASTE_PATH = os.path.join(BASE, "news", "taste.md")
STATE_PATH = os.path.join(BASE, "news", "state.json")

MODEL = "claude-opus-5"
BATCH_SIZE = 5
DEFAULT_VIDEOS = 10
DEFAULT_WEB = 8
CHANNEL_COOLDOWN_WEEKS = 3

# Правило «один материал от источника» защищает от перекоса в сторону одного
# издателя: AWS с одиннадцатью статьями про собственный AgentCore иначе занял бы
# четверть выпуска. Но агрегатор — не издатель. Hacker News и arXiv не пишут
# материалы, а собирают чужие, и ограничивать их одной позицией бессмысленно:
# у каждой записи там свой автор. Им отводится собственная квота.
AGGREGATOR_CAPS = {
    "arxiv": 4,             # препринты — другой жанр, держим меньшинством
    "hackernews": 3,
    "reddit": 2,
}


def aggregator_of(item):
    """Возвращает имя агрегатора или None, если это обычный издатель."""
    source = item.get("source") or ""
    if item["kind"] == "video":
        return None
    root = source.split("/")[0]
    return root if root in AGGREGATOR_CAPS else None
MIN_SCORE = 35             # ниже этого материал не стоит места даже при пустом выпуске

SYSTEM = """Ты пишешь тексты для ленты сайта agenticbase.ru про запуск ИИ-агентов в продакшене.

<вкус>
%s
</вкус>

Для каждого материала напиши на русском языке:

- анонс: одно-два предложения о том, что внутри и зачем это открывать. Не пересказ содержания и не реклама. Читатель должен понять, стоит ли ему тратить время.
- выводы: ровно три коротких пункта — что конкретно человек отсюда унесет.
- результат: одна фраза о том, что читатель сможет сделать после применения.
- ограничения: одна фраза о том, где это не сработает или чего материал не покрывает. Если ограничения неизвестны из описания — так и напиши, не выдумывай.
- уверенность: "высокая", если материал явно на своем месте; "низкая", если ты не уверен, что он заслуживает выпуска, и решение стоит показать человеку.

Жесткие требования к языку:

1. НИКОГДА не используй букву "е" с двумя точками сверху. Это правило сайта, оно проверяется автоматически, нарушение останавливает публикацию. Пиши "еще", "все", "берет", "объем".
2. Не выдумывай факты, цифры и подробности, которых нет во входных данных. Если описание скудное — пиши обобщенно, но честно. Выдуманная деталь хуже скупого анонса.
3. Не пиши "революционный", "прорывной", "меняет все", "must-have". Если автор материала сам так не говорил, не добавляй от себя.
4. Названия продуктов, компаний и инструментов называть можно и нужно.

Ответ — только JSON-массив, без пояснений до и после, по объекту на материал в том же порядке:

[{"n": 1, "анонс": "...", "выводы": ["...", "...", "..."], "результат": "...", "ограничения": "...", "уверенность": "высокая|низкая"}]"""


def load_taste():
    if not os.path.exists(TASTE_PATH):
        return "(файл вкуса не найден)"
    with open(TASTE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def load_state():
    if not os.path.exists(STATE_PATH):
        return {"seen_video_ids": [], "seen_urls": [], "channel_last_featured": {}, "carryover": []}
    with open(STATE_PATH, "r", encoding="utf-8") as handle:
        return json.load(handle)


def no_yo(text):
    """Механическое снятие буквы «ё». Модели тут не доверяем принципиально."""
    if isinstance(text, list):
        return [no_yo(part) for part in text]
    if not isinstance(text, str):
        return text
    return text.replace("ё", "е").replace("Ё", "Е")


def on_cooldown(item, state, now):
    """Канал, попавший в выпуск недавно, пропускает ход.

    Иначе Лента превращается в витрину одного блогера: он публикуется чаще
    других, значит чаще выигрывает, значит выигрывает ещё чаще.
    """
    channel = item.get("channel_id") or item.get("source")
    last = state.get("channel_last_featured", {}).get(channel)
    if not last:
        return False
    try:
        return datetime.fromisoformat(last) > now - timedelta(weeks=CHANNEL_COOLDOWN_WEEKS)
    except ValueError:
        return False


def select(items, state, want_videos, want_web):
    """Детерминированный отбор. Никакой модели — только сортировка и потолки."""
    now = datetime.now(timezone.utc)
    ranked = sorted(items, key=lambda x: -x.get("итог", 0))

    chosen = {"video": [], "web": []}
    used_owners, skipped = set(), []
    aggregator_taken = defaultdict(int)
    rejected = {entry["url"] for entry in state.get("rejected", []) if entry.get("url")}

    for item in ranked:
        kind = item["kind"]
        want = want_videos if kind == "video" else want_web
        if len(chosen[kind]) >= want:
            continue
        if item.get("url_key") in rejected:
            # Продублировано с filter.py намеренно: при повторном прогоне отбора
            # на уже собранных данных первый ярус не выполняется заново.
            skipped.append((item, "забраковано вручную"))
            continue
        if item["оценка"]["качество"] < MIN_SCORE:
            skipped.append((item, "балл ниже порога %d" % MIN_SCORE))
            continue

        aggregator = aggregator_of(item)
        if aggregator:
            cap = AGGREGATOR_CAPS[aggregator]
            if aggregator_taken[aggregator] >= cap:
                skipped.append((item, "исчерпана квота агрегатора %s (%d)" % (aggregator, cap)))
                continue
            aggregator_taken[aggregator] += 1
        else:
            owner = item.get("channel_id") or item.get("source")
            if owner in used_owners:
                skipped.append((item, "от этого издателя уже есть материал"))
                continue
            if on_cooldown(item, state, now):
                skipped.append((item, "издатель был в выпуске меньше %d недель назад" % CHANNEL_COOLDOWN_WEEKS))
                continue
            used_owners.add(owner)

        chosen[kind].append(item)

    return chosen, skipped


def describe(index, item):
    lines = ["%d. %s" % (index, item.get("title", ""))]
    if item["kind"] == "video":
        lines.append("   канал: %s | %d мин | %d просмотров"
                     % (item.get("channel_title", "?"),
                        (item.get("duration_sec") or 0) // 60,
                        item.get("view_count", 0)))
    else:
        lines.append("   источник: %s" % item.get("source", "?"))
    lines.append("   ссылка: %s" % item.get("url", ""))
    description = (item.get("description") or "").strip().replace("\n", " ")
    if description:
        lines.append("   описание: %s" % description[:1200])
    note = (item.get("оценка") or {}).get("заметка")
    if note:
        lines.append("   отмечено при оценке: %s" % note)
    return "\n".join(lines)


def parse_answer(text, size):
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) and len(parsed) == size else None


def write_batch(client, taste, batch, attempt=0):
    payload = "\n".join(describe(index + 1, item) for index, item in enumerate(batch))
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "medium"},
            system=[{"type": "text", "text": SYSTEM % taste, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": payload}],
        )
    except anthropic.APIError as error:
        print("   ! пачка не написана (%s)" % type(error).__name__)
        return None

    text = "".join(block.text for block in response.content if block.type == "text")
    texts = parse_answer(text, len(batch))
    if texts is None and attempt == 0:
        return write_batch(client, taste, batch, attempt + 1)
    if texts is None:
        print("   ! ответ не разобран (stop_reason=%s)" % response.stop_reason)
        return None
    return texts, response.usage


def run(client, taste, finalists):
    tokens_in = tokens_out = 0
    written = []
    for start in range(0, len(finalists), BATCH_SIZE):
        batch = finalists[start:start + BATCH_SIZE]
        print("   пачка %d-%d из %d" % (start + 1, start + len(batch), len(finalists)))
        result = write_batch(client, taste, batch)
        if result is None:
            # Без текста материал в выпуск не идет: лучше выпуск короче,
            # чем позиция с пустым анонсом.
            for item in batch:
                item["тексты"] = None
            written.extend(batch)
            continue
        texts, usage = result
        tokens_in += usage.input_tokens
        tokens_out += usage.output_tokens
        for item, text in zip(batch, texts):
            item["тексты"] = {key: no_yo(value) for key, value in text.items() if key != "n"}
            written.append(item)
    return written, tokens_in, tokens_out


def print_report(chosen, skipped, written, tokens_in, tokens_out):
    ok = [i for i in written if i.get("тексты")]
    unsure = [i for i in ok if i["тексты"].get("уверенность") == "низкая"]

    print()
    print("=" * 76)
    print("ЯРУС 3Б — ОТБОР И ТЕКСТЫ")
    print("=" * 76)
    print()
    print("Отобрано: %d видео, %d веб-материалов" % (len(chosen["video"]), len(chosen["web"])))
    print("Тексты написаны: %d из %d" % (len(ok), len(written)))
    if unsure:
        print("Требуют твоего решения: %d" % len(unsure))

    print()
    print("ВЫПУСК:")
    for kind, label in (("video", "Видео"), ("web", "Веб")):
        print()
        print("  --- %s ---" % label)
        for item in chosen[kind]:
            texts = item.get("тексты") or {}
            flag = "  [?]" if texts.get("уверенность") == "низкая" else ""
            print("  %5.1f  %-18s %s%s"
                  % (item["итог"], (item.get("channel_title") or item.get("source") or "")[:18],
                     item["title"][:56], flag))
            if texts.get("анонс"):
                print("         %s" % texts["анонс"][:150])

    reasons = defaultdict(int)
    for _, reason in skipped:
        reasons[reason] += 1
    if reasons:
        print()
        print("Не вошли (журнал отбора):")
        for reason, count in sorted(reasons.items(), key=lambda pair: -pair[1]):
            print("   %-52s %4d" % (reason, count))

    cost = tokens_in / 1_000_000 * 5.0 + tokens_out / 1_000_000 * 25.0
    print()
    print("Токены: %d на входе, %d на выходе. Стоимость: $%.3f" % (tokens_in, tokens_out, cost))
    print()


def main():
    parser = argparse.ArgumentParser(description="Отбор финалистов и написание текстов")
    parser.add_argument("candidates", help="файл, созданный score.py")
    parser.add_argument("--out", help="каталог для результата")
    parser.add_argument("--videos", type=int, default=DEFAULT_VIDEOS)
    parser.add_argument("--web", type=int, default=DEFAULT_WEB)
    arguments = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Нет ANTHROPIC_API_KEY в окружении.")
        return 1

    with open(arguments.candidates, "r", encoding="utf-8") as handle:
        items = json.load(handle)["items"]

    chosen, skipped = select(items, load_state(), arguments.videos, arguments.web)
    finalists = chosen["video"] + chosen["web"]
    if not finalists:
        print("Ни один материал не прошел отбор. Выпуск пропускается — это нормальный исход.")
        return 0

    client = anthropic.Anthropic()
    written, tokens_in, tokens_out = run(client, load_taste(), finalists)
    print_report(chosen, skipped, written, tokens_in, tokens_out)

    if arguments.out:
        os.makedirs(arguments.out, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(arguments.out, "issue-%s.json" % stamp)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({
                "videos": [i for i in chosen["video"] if i.get("тексты")],
                "web": [i for i in chosen["web"] if i.get("тексты")],
                "skipped": [{"title": i["title"][:120], "url": i.get("url"), "reason": r}
                            for i, r in skipped],
            }, handle, ensure_ascii=False, indent=2)
        print("Сохранено: %s" % path)
    return 0


if __name__ == "__main__":
    sys.exit(main())
