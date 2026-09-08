"""Быстрая классификация — второй ярус конвейера Ленты.

Отвечает на вопросы, у которых нет однозначного ответа в структурных данных
и которые поэтому нельзя решать поиском подстроки:

    про агентов ли это вообще?
    это подкаст, доклад с гостем или самостоятельный материал?
    реклама здесь структурная или проходная?
    это новостная нарезка или содержательный разбор?

Почему не регулярками. Шаблон /podcast|интервью/ убивает туториал «как
собрать агента, расшифровывающего подкасты», и при этом пропускает
«Zero Day Close: The End of Accounting» — маркетинговый ролик без единого
запрещенного слова, который в прошлом выпуске получил оценку 92.

Правила отбора живут не здесь, а в news/taste.md — обычном текстовом файле,
который правит человек без участия агента. Этот скрипт только подставляет
его в промт.

Три страховки от того, чтобы фильтр сам не стал поломкой:

1. Ярус может только отклонять. Воскресить отсеянное первым ярусом он не может.
2. Сбой трактуется как пропуск, а не как отказ. Не разобрался ответ, упал API,
   кончился лимит — кандидат идет дальше. Фильтр, который при поломке молча
   все отсеивает, — это ровно тот сценарий, который дал три материала в выпуске.
3. Если отбраковано больше порога — прогон останавливается. Это признак
   сломавшегося промта, а не плохой недели.

Запуск:

    python news/classify.py news/.cache/filtered-2026-09-08.json --out news/.cache
    python news/classify.py <файл> --limit 40      # проба на части материала
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone

import anthropic

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
TASTE_PATH = os.path.join(BASE, "news", "taste.md")

MODEL = "claude-haiku-4-5"
BATCH_SIZE = 20
MAX_REJECT_SHARE = 0.85     # выше — считаем, что сломался промт, а не неделя

SYSTEM = """Ты отбираешь материалы для ленты сайта agenticbase.ru про запуск ИИ-агентов в продакшене.

Твоя задача на этом шаге — не оценивать качество, а отсекать заведомо неподходящее по формату и намерению. Оценка баллами будет отдельным шагом дальше, не подменяй его.

Ниже — файл вкуса, его писал владелец сайта. Он важнее любых твоих представлений о том, что интересно.

<вкус>
%s
</вкус>

По каждому материалу верни решение. Отклоняй только при уверенности: если сомневаешься — пропускай дальше, следующий ярус разберется. Ошибочно пропущенный материал стоит дешево, ошибочно выброшенный теряется навсегда.

Отклоняй, если выполнено хотя бы одно:
- материал не про ИИ-агентов и не про то, что рядом с ними (модели без агентной части, общие новости ИИ-отрасли, реклама железа);
- это подкаст, интервью, беседа или запись доклада с гостем, а не самостоятельный материал;
- это новостная нарезка, обзор недели или подборка «топ-N» без собственного содержания;
- реклама структурная: материал существует ради продажи курса, сообщества, консультации или подписки.

Отдельно и обязательно различай два вида рекламы:
- "структурная" — материал сделан ради продажи, обещания курса или сообщества повторяются, польза служит приманкой. Это отказ.
- "проходная" — автор один раз упомянул свой блог, продукт или проект. Это НЕ повод отклонять.
- "нет" — рекламы нет.

Учитывай, что у материала могут стоять маркеры, проставленные механически по словам в заголовке. Это подсказка «посмотри внимательнее», а не решение: слово "podcast" в туториале про расшифровку подкастов не делает материал подкастом.

Ответ — только JSON-массив, без пояснений до и после. По одному объекту на каждый материал, в том же порядке, что и на входе:

[{"n": 1, "про_агентов": true, "формат": "статья|туториал|подкаст|доклад|новости|подборка|маркетинг|другое", "реклама": "нет|проходная|структурная", "решение": "пропустить|отклонить", "причина": "до 12 слов"}]

Причина обязательна всегда, и для пропущенных тоже — одной фразой, чем материал полезен."""


def load_taste():
    if not os.path.exists(TASTE_PATH):
        return "(файл вкуса не найден — работай по общим правилам ниже)"
    with open(TASTE_PATH, "r", encoding="utf-8") as handle:
        return handle.read()


def describe(index, item):
    """Готовит компактное описание материала для модели.

    Описание режем: для решения о формате и намерении хватает начала, а
    каждый лишний символ умножается на число кандидатов.
    """
    lines = ["%d. %s" % (index, item.get("title", ""))]
    if item["kind"] == "video":
        lines.append("   канал: %s | %d мин | %d просмотров | язык: %s"
                     % (item.get("channel_title", "?"),
                        (item.get("duration_sec") or 0) // 60,
                        item.get("view_count", 0),
                        item.get("language") or "не указан"))
    else:
        lines.append("   источник: %s" % item.get("source", "?"))
    description = (item.get("description") or "").strip().replace("\n", " ")
    if description:
        lines.append("   описание: %s" % description[:400])
    if item.get("маркеры"):
        lines.append("   механические маркеры: %s" % ", ".join(item["маркеры"]))
    return "\n".join(lines)


def parse_answer(text, size):
    """Достает JSON-массив из ответа. None, если разобрать не удалось."""
    match = re.search(r"\[.*\]", text, re.S)
    if not match:
        return None
    try:
        parsed = json.loads(match.group(0))
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, list) or len(parsed) != size:
        return None
    return parsed


def classify_batch(client, taste, batch, attempt=0):
    """Классифицирует пачку. При неудаче возвращает None — это «пропустить всех»."""
    payload = "\n".join(describe(index + 1, item) for index, item in enumerate(batch))
    try:
        response = client.messages.create(
            model=MODEL,
            max_tokens=4000,
            system=[{"type": "text", "text": SYSTEM % taste, "cache_control": {"type": "ephemeral"}}],
            messages=[{"role": "user", "content": payload}],
        )
    except anthropic.APIError as error:
        print("   ! пачка не обработана (%s), материалы пропущены дальше" % type(error).__name__)
        return None

    text = "".join(block.text for block in response.content if block.type == "text")
    verdicts = parse_answer(text, len(batch))
    if verdicts is None and attempt == 0:
        return classify_batch(client, taste, batch, attempt + 1)
    if verdicts is None:
        print("   ! ответ не разобран, материалы пропущены дальше")
        return None
    return verdicts, response.usage


def run(client, taste, items):
    kept, dropped = [], []
    total_in = total_out = 0

    for start in range(0, len(items), BATCH_SIZE):
        batch = items[start:start + BATCH_SIZE]
        print("   пачка %d-%d из %d" % (start + 1, start + len(batch), len(items)))
        result = classify_batch(client, taste, batch)

        if result is None:
            # Сбой — пропускаем всех дальше. Молчаливый отсев при поломке
            # хуже лишнего материала в следующем ярусе.
            for item in batch:
                item["ярус2"] = {"решение": "пропустить", "причина": "сбой классификации, пропущено по умолчанию"}
                kept.append(item)
            continue

        verdicts, usage = result
        total_in += usage.input_tokens
        total_out += usage.output_tokens

        for item, verdict in zip(batch, verdicts):
            item["ярус2"] = verdict
            if verdict.get("решение") == "отклонить":
                dropped.append({
                    "title": item.get("title", "")[:120],
                    "url": item.get("url"),
                    "source": item.get("source"),
                    "формат": verdict.get("формат"),
                    "реклама": verdict.get("реклама"),
                    "причина": verdict.get("причина"),
                })
            else:
                kept.append(item)

    return kept, dropped, total_in, total_out


def print_report(kept, dropped, total, tokens_in, tokens_out):
    print()
    print("=" * 68)
    print("ЯРУС 2 — КЛАССИФИКАЦИЯ МОДЕЛЬЮ")
    print("=" * 68)
    print()
    print("На входе:  %4d" % total)
    print("Отклонено: %4d" % len(dropped))
    print("Прошло:    %4d" % len(kept))
    print("   видео:  %4d" % sum(1 for i in kept if i["kind"] == "video"))
    print("   веб:    %4d" % sum(1 for i in kept if i["kind"] == "web"))

    by_reason = {}
    for entry in dropped:
        key = "%s / реклама: %s" % (entry.get("формат") or "?", entry.get("реклама") or "?")
        by_reason[key] = by_reason.get(key, 0) + 1
    if by_reason:
        print()
        print("Отклонено по формату и намерению:")
        for key, count in sorted(by_reason.items(), key=lambda pair: -pair[1])[:12]:
            print("   %-44s %4d" % (key, count))

    # Haiku 4.5: 1 доллар за миллион входных, 5 за миллион выходных.
    cost = tokens_in / 1_000_000 * 1.0 + tokens_out / 1_000_000 * 5.0
    print()
    print("Токены: %d на входе, %d на выходе. Стоимость прогона: $%.3f"
          % (tokens_in, tokens_out, cost))
    print()


def main():
    parser = argparse.ArgumentParser(description="Классификация кандидатов моделью")
    parser.add_argument("candidates", help="файл, созданный filter.py")
    parser.add_argument("--out", help="каталог для результата и журнала отклонений")
    parser.add_argument("--limit", type=int, help="обработать только первые N (проба)")
    arguments = parser.parse_args()

    if not os.environ.get("ANTHROPIC_API_KEY"):
        print("Нет ANTHROPIC_API_KEY в окружении.")
        return 1

    with open(arguments.candidates, "r", encoding="utf-8") as handle:
        items = json.load(handle)["items"]
    if arguments.limit:
        items = items[: arguments.limit]

    client = anthropic.Anthropic()
    kept, dropped, tokens_in, tokens_out = run(client, load_taste(), items)
    print_report(kept, dropped, len(items), tokens_in, tokens_out)

    share = len(dropped) / len(items) if items else 0
    if share > MAX_REJECT_SHARE:
        print("ОСТАНОВКА: отклонено %.0f%% пула. Это признак сломавшегося промта,"
              " а не плохой недели. Результат не сохранен." % (share * 100))
        return 2

    if arguments.out:
        os.makedirs(arguments.out, exist_ok=True)
        stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        with open(os.path.join(arguments.out, "classified-%s.json" % stamp), "w", encoding="utf-8") as handle:
            json.dump({"items": kept}, handle, ensure_ascii=False, indent=2)
        with open(os.path.join(arguments.out, "dropped-tier2-%s.json" % stamp), "w", encoding="utf-8") as handle:
            json.dump({"dropped": dropped}, handle, ensure_ascii=False, indent=2)
        print("Сохранено: classified-%s.json (%d) и dropped-tier2-%s.json (%d)"
              % (stamp, len(kept), stamp, len(dropped)))
    return 0


if __name__ == "__main__":
    sys.exit(main())
