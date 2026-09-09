"""Сводка выпуска для пулл-реквеста.

Печатает в stdout markdown, который воркфлоу кладет в тело пулл-реквеста.
Смысл — чтобы решение принималось по одному экрану, а не по диффу json.

Главное здесь — разделение на «прошло уверенно» и «требует решения».
Оценщик сам помечает позиции, в которых не уверен, и на проверку человеку
приходят только они: три позиции вместо восемнадцати. Без такого разделения
проверка вырождается в «слить не глядя», и смысл ручного подтверждения
теряется.

Запуск:

    python news/summary.py .cache/issue-2026-09-09.json > pr-body.md
"""

import collections
import json
import os
import sys


def load(path):
    with open(path, "r", encoding="utf-8") as handle:
        return json.load(handle)


def confidence(item):
    return (item.get("тексты") or {}).get("уверенность", "высокая")


def line(item):
    where = item.get("channel_title") or item.get("source") or ""
    return "- **%s** — %s  \n  <sub>%s · балл %.0f</sub>\n  %s" % (
        item.get("title", "")[:110],
        item.get("url", ""),
        where,
        item.get("итог", 0),
        (item.get("тексты") or {}).get("анонс", ""),
    )


def main():
    if len(sys.argv) < 2 or not os.path.exists(sys.argv[1]):
        print("Файл выпуска не найден.")
        return 1

    issue = load(sys.argv[1])
    videos = issue.get("videos", [])
    web = issue.get("web", [])
    everything = videos + web
    unsure = [i for i in everything if confidence(i) == "низкая"]
    sure = [i for i in everything if confidence(i) != "низкая"]

    out = []
    out.append("## Выпуск собран: %d видео, %d статей" % (len(videos), len(web)))
    out.append("")

    if unsure:
        out.append("### Требуют решения — %d" % len(unsure))
        out.append("")
        out.append("Оценщик не уверен, что этим материалам место в выпуске. "
                   "Остальное можно не перечитывать.")
        out.append("")
        for item in unsure:
            out.append(line(item))
        out.append("")
    else:
        out.append("### Спорных позиций нет")
        out.append("")
        out.append("Оценщик уверен во всех материалах выпуска.")
        out.append("")

    out.append("<details><summary>Прошло уверенно — %d</summary>" % len(sure))
    out.append("")
    for item in sure:
        out.append(line(item))
    out.append("")
    out.append("</details>")
    out.append("")

    skipped = issue.get("skipped", [])
    if skipped:
        reasons = collections.Counter(entry.get("reason", "") for entry in skipped)
        out.append("<details><summary>Не вошли — %d</summary>" % len(skipped))
        out.append("")
        for reason, count in reasons.most_common():
            out.append("- %s — %d" % (reason, count))
        out.append("")
        out.append("</details>")
        out.append("")

    out.append("---")
    out.append("")
    out.append("Слияние публикует выпуск: пуш в `main` запускает сборку и выкладку на Beget. "
               "Если выпуск не нравится — закрыть пулл-реквест, ничего не произойдет.")

    print("\n".join(out))
    return 0


if __name__ == "__main__":
    sys.exit(main())
