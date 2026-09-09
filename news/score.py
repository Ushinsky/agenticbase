"""Оценка по рубрике — ярус 3а конвейера Ленты.

Считает баллы всем, кто прошел классификацию. Только цифры, без прозы:
анонс пишет следующий шаг (write.py) и только для финалистов. Считать баллы
и писать тексты — разные задачи, и платить за вторую там, где нужна первая,
незачем.

Рубрика задана владельцем сайта:

    практическая применимость   до 30
    конкретность                до 20
    доказательства или кейс     до 15
    связь с ИИ-агентами         до 15
    новизна                     до 10
    универсальность             до  5
    надежность источника        до  5
    коммерческая насыщенность   штраф до 5

Три защиты от того, чем рубрика сломалась в прошлый раз (все 20 роликов
выпуска 24 августа получили 83–93 при просмотрах от 0 до 12):

1. Модель возвращает подоценки по отдельности, сумму считает Python.
   Арифметику модели не проверяет никто, а ошибку в ней не видно.
2. В промт зашиты три якоря — эталон на 90, на 60 и на 25, взятые из
   реальной выдачи. Без калибровки любая рубрика уползает вверх.
3. Разброс оценок проверяется после прогона. Если он схлопнулся — это
   признак сломавшегося промта, и прогон об этом говорит.

Популярность считается процентилем внутри пула, а не абсолютом: иначе
свежий материал всегда проигрывает старому, а вирусная пустышка выигрывает
у всех. Итог = 0.75 * качество + 0.25 * популярность.

Запуск:

    python news/score.py news/.cache/classified-2026-09-08.json --out news/.cache
"""

import argparse
import json
import math
import os
import re
import statistics
import sys
from datetime import datetime, timezone

import anthropic

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASTE_PATH = os.path.join(BASE, "news", "taste.md")

MODEL = "claude-sonnet-5"
BATCH_SIZE = 15
QUALITY_WEIGHT = 0.75
POPULARITY_WEIGHT = 0.25
MIN_SPREAD = 8.0        # стандартное отклонение ниже — рубрика схлопнулась

CRITERIA = [
    ("применимость", 30),
    ("конкретность", 20),
    ("доказательства", 15),
    ("связь_с_агентами", 15),
    ("новизна", 10),
    ("универсальность", 5),
    ("надежность_источника", 5),
]
PENALTY = ("коммерческая_насыщенность", 5)

SYSTEM = """Ты оцениваешь материалы для ленты сайта agenticbase.ru про запуск ИИ-агентов в продакшене.

<вкус>
%s
</вкус>

Выставь каждому материалу подоценки строго в этих границах:

- применимость (0-30): сможет ли читатель после этого материала сделать то, чего не мог. Максимум — пошаговый рабочий подход; ноль — общие рассуждения.
- конкретность (0-20): названы ли инструменты, версии, параметры, конкретные решения. Ноль — все на уровне "нужно правильно настроить".
- доказательства (0-15): есть ли опыт из первых рук — числа, замеры, названные ограничения, подробности, видные только изнутри задачи. Обещание опыта без подробностей — не опыт.
- связь_с_агентами (0-15): насколько прямо материал про ИИ-агентов, а не про модели, инфраструктуру или ИИ вообще.
- новизна (0-10): узнает ли читатель что-то, чего не было в десяти похожих материалах.
- универсальность (0-5): применимо у многих или только в узком стеке одного вендора.
- надежность_источника (0-5): практик с именем и репутацией против анонимного канала.
- коммерческая_насыщенность (0-5): ШТРАФ. 0 — рекламы нет, 5 — материал существует ради продажи.

Калибровочные якоря, держи шкалу по ним:

ЯКОРЬ 88 — "Which tools do Claude, Codex and Cursor choose? We measured 17k runs to find out": собственный замер на большой серии прогонов, числа вместо мнения, прямо применимо к проектированию обвязки агента. Опыт из первых рук.

ЯКОРЬ 60 — "AI Agent System Design Explained in 15 Minutes" (обучающий канал): грамотный разбор архитектуры, все верно и понятно, но это пересказ общеизвестного без собственного опыта и без цифр.

ЯКОРЬ 25 — "101 Ways To Use AI Agents In Your Daily Life": перечисление без глубины, ни одного доведенного до конца примера, ценность близка к нулю.

Большинство материалов — между 40 и 70. Оценка выше 85 должна быть редкой и требует опыта из первых рук. Если ты ставишь почти всем больше 80, ты ошибаешься.

Ответ — только JSON-массив, без пояснений до и после, по объекту на материал в том же порядке:

[{"n": 1, "применимость": 0, "конкретность": 0, "доказательства": 0, "связь_с_агентами": 0, "новизна": 0, "универсальность": 0, "надежность_источника": 0, "коммерческая_насыщенность": 0, "заметка": "до 15 слов, чем силен или слаб"}]"""


def load_taste():
    if not os.path.exists(TASTE_PATH):
        return "(файл вкуса не найден)"
    with open(TASTE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def describe(index, item):
    lines = ["%d. %s" % (index, item.get("title", ""))]
    if item["kind"] == "video":
        lines.append("   канал: %s | %d мин | %d просмотров"
                     % (item.get("channel_title", "?"),
                        (item.get("duration_sec") or 0) // 60,
                        item.get("view_count", 0)))
    else:
        lines.append("   источник: %s" % item.get("source", "?"))
    description = (item.get("description") or "").strip().replace("\n", " ")
    if description:
        lines.append("   описание: %s" % description[:700])
    note = (item.get("ярус2") or {}).get("причина")
    if note:
        lines.append("   отмечено на отборе: %s" % note)
    return "\n".join(lines)


def quality_of(verdict):
    """Сумму считаем здесь, а не доверяем модели."""
    total = 0
    for name, cap in CRITERIA:
        total += max(0, min(int(verdict.get(name, 0) or 0), cap))
    penalty_name, penalty_cap = PENALTY
    total -= max(0, min(int(verdict.get(penalty_name, 0) or 0), penalty_cap))
    return max(0, total)


def parse_answer(text, size):
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, list) and len(parsed) == size else None


def score_batch(client, taste, batch, attempt=0):
    payload = "\n".join(describe(index + 1, item) for index, item in enumerate(batch))
    try:
        # У Sonnet 5 рассуждение включено по умолчанию и расходует тот же
        # лимит вывода, что и ответ: при тесном max_tokens JSON обрывается на
        # середине и не разбирается. Для оценки по готовой рубрике глубокое
        # рассуждение не нужно — ставим низкое усилие и просторный лимит.
        response = client.messages.create(
            model=MODEL,
            max_tokens=16000,
            output_config={"effort": "low"},
            system=[{"type": "text", "text": SYSTEM % taste, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": payload}],
        )
    except anthropic.APIError as error:
        print("   ! пачка не оценена (%s)" % type(error).__name__)
        return None

    text = "".join(block.text for block in response.content if block.type == "text")
    verdicts = parse_answer(text, len(batch))
    if verdicts is None and attempt == 0:
        return score_batch(client, taste, batch, attempt + 1)
    if verdicts is None:
        print("   ! ответ не разобран (stop_reason=%s, вывод %d токенов)"
              % (response.stop_reason, response.usage.output_tokens))
        if os.environ.get("SCORE_DEBUG"):
            print("   --- начало ответа ---")
            print(text[:1500] or "(пусто)")
            print("   --- конец ---")
        return None
    return verdicts, response.usage


def popularity_percentiles(items):
    """Процентиль популярности внутри своего типа материала.

    Процентиль, а не абсолют: 3,6 миллиона просмотров у ролика про запуск
    модели не должны прижимать к нулю все остальное. Скорость набора
    (просмотры в сутки) сравнивает свежее со свежим.
    """
    now = datetime.now(timezone.utc)

    def speed(item):
        published = item.get("published_at")
        if not published:
            return 0.0
        try:
            age_days = max((now - datetime.fromisoformat(published)).total_seconds() / 86400, 0.5)
        except ValueError:
            return 0.0
        if item["kind"] == "video":
            return item.get("view_count", 0) / age_days
        return (item.get("points", 0) or 0) / age_days

    for kind in ("video", "web"):
        group = [i for i in items if i["kind"] == kind]
        values = sorted(speed(i) for i in group)
        for item in group:
            own = speed(item)
            if not values or max(values) == 0:
                item["популярность"] = 50.0
                continue
            rank = sum(1 for value in values if value < own)
            item["популярность"] = round(rank / len(values) * 100, 1)


def run(client, taste, items):
    tokens_in = tokens_out = 0
    scored = []

    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        print("   пачка %d-%d из %d" % (start + 1, start + len(batch), len(items)))
        result = score_batch(client, taste, batch)

        if result is None:
            # Не оценили — материал не выбрасываем, но и в финал он не пройдет:
            # ставим нейтральный ноль и явную пометку, чтобы это было видно.
            for item in batch:
                item["оценка"] = {"качество": 0, "заметка": "не оценено, сбой"}
                scored.append(item)
            continue

        verdicts, usage = result
        tokens_in += usage.input_tokens
        tokens_out += usage.output_tokens
        for item, verdict in zip(batch, verdicts):
            item["оценка"] = {
                "подоценки": {name: verdict.get(name, 0) for name, _ in CRITERIA},
                "штраф": verdict.get(PENALTY[0], 0),
                "качество": quality_of(verdict),
                "заметка": verdict.get("заметка", ""),
            }
            scored.append(item)

    popularity_percentiles(scored)
    for item in scored:
        item["итог"] = round(
            QUALITY_WEIGHT * item["оценка"]["качество"]
            + POPULARITY_WEIGHT * item.get("популярность", 50.0), 1)
    return scored, tokens_in, tokens_out


def print_report(items, tokens_in, tokens_out):
    quality = [i["оценка"]["качество"] for i in items if i["оценка"]["качество"] > 0]
    print()
    print("=" * 72)
    print("ЯРУС 3А — ОЦЕНКА ПО РУБРИКЕ")
    print("=" * 72)
    print()
    print("Оценено: %d" % len(items))
    if quality:
        spread = statistics.pstdev(quality)
        print("Качество: медиана %.0f, среднее %.0f, разброс %.1f, от %d до %d"
              % (statistics.median(quality), statistics.mean(quality), spread,
                 min(quality), max(quality)))
        buckets = {"0-39": 0, "40-59": 0, "60-74": 0, "75-84": 0, "85+": 0}
        for value in quality:
            key = ("85+" if value >= 85 else "75-84" if value >= 75
                   else "60-74" if value >= 60 else "40-59" if value >= 40 else "0-39")
            buckets[key] += 1
        print()
        for key in ("0-39", "40-59", "60-74", "75-84", "85+"):
            bar = "#" * math.ceil(buckets[key] / max(1, len(quality)) * 40)
            print("   %-6s %4d  %s" % (key, buckets[key], bar))
        if spread < MIN_SPREAD:
            print()
            print("ВНИМАНИЕ: разброс оценок %.1f — ниже порога %.1f." % (spread, MIN_SPREAD))
            print("Это признак схлопнувшейся рубрики, а не ровной недели. Проверить промт.")

    print()
    print("Лучшие 15 по итогу (качество + популярность):")
    for item in sorted(items, key=lambda x: -x.get("итог", 0))[:15]:
        print("   %5.1f  к%3d п%5.1f  %-16s %s"
              % (item["итог"], item["оценка"]["качество"], item.get("популярность", 0),
                 (item.get("channel_title") or item.get("source") or "")[:16],
                 item["title"][:52]))

    cost = tokens_in / 1_000_000 * 2.0 + tokens_out / 1_000_000 * 10.0
    print()
    print("Токены: %d на входе, %d на выходе. Стоимость: $%.3f" % (tokens_in, tokens_out, cost))
    print()


def main():
    parser = argparse.ArgumentParser(description="Оценка кандидатов по рубрике")
    parser.add_argument("candidates", help="файл, созданный classify.py")
    parser.add_argument("--out", help="каталог для результата")
    parser.add_argument("--limit", type=int, help="обработать только первые N")
    arguments = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Нет ANTHROPIC_API_KEY в окружении.")
        return 1

    with open(arguments.candidates, "r", encoding="utf-8") as handle:
        items = json.load(handle)["items"]
    if arguments.limit:
        items = items[: arguments.limit]

    client = anthropic.Anthropic()
    scored, tokens_in, tokens_out = run(client, load_taste(), items)
    print_report(scored, tokens_in, tokens_out)

    if arguments.out:
        os.makedirs(arguments.out, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        path = os.path.join(arguments.out, "scored-%s.json" % stamp)
        with open(path, "w", encoding="utf-8") as handle:
            json.dump({"items": scored}, handle, ensure_ascii=False, indent=2)
        print("Сохранено: %s (%d)" % (path, len(scored)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
