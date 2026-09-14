"""Одна строка о выпуске для телеграм-сообщения.

Отдельный скрипт, а не выражение в YAML: считать по данным надо на Python,
а внутри воркфлоу такая логика превращается в нечитаемую однострочную склейку.

Печатает что-то вроде:

    10 видео, 8 статей, 3 требуют решения

Запуск:

    python news/telegram_line.py
"""

import glob
import json
import os
import sys

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def plural(count, one, few, many):
    tail = count % 100
    if 11 <= tail <= 14:
        return many
    tail = count % 10
    if tail == 1:
        return one
    if 2 <= tail <= 4:
        return few
    return many


def main():
    # Берем самый свежий собранный выпуск: имя файла содержит дату прогона,
    # а он может не совпадать с сегодняшним при догоняющем запуске.
    candidates = sorted(glob.glob(os.path.join(BASE, ".cache", "issue-*.json")))
    if not candidates:
        print("подробности в журнале прогона")
        return 0

    with open(candidates[-1], "r", encoding="utf-8") as handle:
        issue = json.load(handle)

    videos = issue.get("videos", [])
    web = issue.get("web", [])
    unsure = sum(
        1 for item in videos + web
        if (item.get("тексты") or {}).get("уверенность") == "низкая"
    )

    parts = [
        "%d %s" % (len(videos), plural(len(videos), "видео", "видео", "видео")),
        "%d %s" % (len(web), plural(len(web), "статья", "статьи", "статей")),
    ]
    if unsure:
        parts.append("%d %s решения"
                     % (unsure, plural(unsure, "требует", "требуют", "требуют")))
    print(", ".join(parts))
    return 0


if __name__ == "__main__":
    sys.exit(main())


