"""Нужно ли собирать выпуск прямо сейчас.

Существует ради догоняющего запуска. Cron в GitHub Actions — обещание
«по возможности»: при нагрузке запуск задерживается, а иногда пропадает
совсем. Поэтому воркфлоу заведен на субботу и на воскресенье, а этот скрипт
решает, не сделана ли работа уже.

Логика простая: если текущий выпуск в news/digest.json собран меньше
FRESH_HOURS назад, значит субботний прогон прошел и воскресный не нужен.
Иначе — собираем.

Печатает в stdout "yes" или "no" и пишет причину в stderr, чтобы она попала
в журнал прогона, но не в подстановку.

Запуск:

    python news/should_run.py
"""

import json
import os
import sys
from datetime import datetime, timedelta, timezone

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIGEST_PATH = os.path.join(BASE, "news", "digest.json")

# Сутки с запасом: субботний и воскресный запуски разведены на 24 часа.
FRESH_HOURS = 30


def main():
    if not os.path.exists(DIGEST_PATH):
        print("yes")
        print("digest.json еще нет — это первый выпуск", file=sys.stderr)
        return 0

    with open(DIGEST_PATH, "r", encoding="utf-8") as handle:
        digest = json.load(handle)

    generated = digest.get("generated_at")
    if not generated:
        print("yes")
        print("в digest.json нет отметки времени — собираем", file=sys.stderr)
        return 0

    try:
        when = datetime.fromisoformat(generated)
    except ValueError:
        print("yes")
        print("отметку времени не разобрать (%s) — собираем" % generated, file=sys.stderr)
        return 0

    age = datetime.now(timezone.utc) - when
    if age < timedelta(hours=FRESH_HOURS):
        print("no")
        print("выпуск «%s» собран %d часов назад — пропускаем"
              % (digest.get("current", {}).get("period_label", "?"),
                 age.total_seconds() // 3600), file=sys.stderr)
        return 0

    print("yes")
    print("последний выпуск собран %d часов назад — пора" % (age.total_seconds() // 3600),
          file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
