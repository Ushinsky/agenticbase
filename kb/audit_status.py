# -*- coding: utf-8 -*-
"""Состояние журнала сверки: что проверено, что нет, что устарело.

Использование:
    python kb/audit_status.py                          — общая картина
    python kb/audit_status.py lanham                   — план работ по одному источнику
    python kb/audit_status.py mark <узел> <источник>   — записать состоявшуюся сверку
    python kb/audit_status.py cover <источник> 201-255 — записать прочитанные страницы

Большой источник разбирают этапами, но ни одна его часть не остается
без разбора: команда cover показывает, что еще не читалось.
"""
import io
import json
import os
import sys

BASE = os.path.dirname(os.path.abspath(__file__))
MANIFEST = os.path.join(BASE, "manifest.json")


def load():
    with io.open(MANIFEST, encoding="utf-8") as fh:
        return json.load(fh)


def published(manifest):
    return [n for n in manifest["nodes"] if n.get("status") == "published"]


def report_all(manifest):
    nodes = published(manifest)
    checked_at = {s["id"]: s.get("checked_at", "") for s in manifest["sources"]}

    never = [n for n in nodes if not n.get("audited")]
    declared = []
    stale = []
    for node in nodes:
        audited = node.get("audited", {})
        for source in node.get("sources", []):
            if source not in audited:
                declared.append((node["id"], source))
            elif checked_at.get(source, "") > audited[source]:
                stale.append((node["id"], source, audited[source], checked_at[source]))

    print("Опубликовано материалов: %d" % len(nodes))
    print("Ни разу не сверялись ни с одним источником: %d" % len(never))
    print("Заявленных, но не подтвержденных пар узел-источник: %d" % len(declared))
    print("Устаревших сверок (источник обновился позже): %d" % len(stale))

    if never:
        print("\nНи разу не сверялись:")
        for node in never:
            print("  %-28s источники: %s" % (node["id"], ", ".join(node.get("sources", [])) or "нет"))

    if declared:
        print("\nЗаявлено, но не подтверждено:")
        for node_id, source in declared:
            print("  %-28s %s" % (node_id, source))

    if stale:
        print("\nУстарело после обновления источника:")
        for node_id, source, was, now in stale:
            print("  %-28s %-8s сверялось %s, источник от %s" % (node_id, source, was, now))


OUTLINE_DIR = os.path.join(os.path.dirname(BASE), "sources", "outline")


def source_pages(source_id):
    """Сколько всего страниц в источнике — из оглавления, если оно построено."""
    path = os.path.join(OUTLINE_DIR, "%s.json" % source_id)
    if not os.path.exists(path):
        return None
    with io.open(path, encoding="utf-8") as fh:
        return json.load(fh).get("pages")


def parse_ranges(items):
    """Строки вида "201-255" и "42" в список пар (от, до)."""
    out = []
    for item in items:
        piece = str(item).strip()
        if "-" in piece:
            a, b = piece.split("-", 1)
        else:
            a = b = piece
        out.append((int(a), int(b)))
    return sorted(out)


def merge_ranges(ranges):
    merged = []
    for a, b in sorted(ranges):
        if merged and a <= merged[-1][1] + 1:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    return [(a, b) for a, b in merged]


def gaps(covered, total):
    """Непрочитанные куски источника — то, что правило запрещает игнорировать."""
    out = []
    cursor = 1
    for a, b in merge_ranges(covered):
        if a > cursor:
            out.append((cursor, a - 1))
        cursor = max(cursor, b + 1)
    if cursor <= total:
        out.append((cursor, total))
    return out


def show(ranges):
    return ", ".join("%d-%d" % (a, b) if a != b else str(a) for a, b in ranges)


def report_units(source):
    """Прочитанное у источника, состоящего из именованных частей.

    У репозитория или подборки статей страниц нет, но части есть, и правило
    то же: разбирать можно этапами, пропускать части нельзя. Полный состав
    хранится в units, разобранное - в covered.
    """
    units = source.get("units")
    if not units:
        print("\nСостав источника не описан — полноту разбора проверить нечем.")
        print("Заполните units в kb/manifest.json, иначе пропуск части не виден.")
        return
    done = [u for u in units if u in set(source.get("covered", []))]
    left = [u for u in units if u not in set(source.get("covered", []))]
    print("\nРазобрано частей: %d из %d" % (len(done), len(units)))
    if left:
        print("Не читалось — следующие этапы:")
        for u in left:
            print("  - %s" % u)
    else:
        print("Источник разобран целиком.")


def report_coverage(source):
    """Прочитанное и непрочитанное по страницам. Большой источник берут этапами,
    но ни одна часть не остается без разбора."""
    total = source_pages(source["id"])
    if not total:
        report_units(source)
        return
    covered = parse_ranges(source.get("covered", []))
    print("\nПрочитано: %s из %d страниц" % (show(merge_ranges(covered)) or "ничего", total))
    left = gaps(covered, total)
    if left:
        print("Не читалось — следующие этапы: %s" % show(left))
    else:
        print("Источник разобран целиком.")


def cover(source_id, ranges):
    """Записать прочитанные страницы."""
    manifest = load()
    source = next((s for s in manifest["sources"] if s["id"] == source_id), None)
    if source is None:
        raise SystemExit("нет такого источника: %s" % source_id)
    if source.get("units") is not None:
        known = set(source["units"])
        unknown = [r for r in ranges if r not in known]
        if unknown:
            raise SystemExit(
                "нет таких частей у %s: %s. Состав перечислен в units."
                % (source_id, ", ".join(unknown))
            )
        have = set(source.get("covered", []))
        source["covered"] = [u for u in source["units"] if u in have or u in set(ranges)]
    else:
        existing = parse_ranges(source.get("covered", []))
        source["covered"] = [
            "%d-%d" % (a, b) if a != b else str(a)
            for a, b in merge_ranges(existing + parse_ranges(ranges))
        ]
    with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")
    print("Записано прочитанное у %s: %s" % (source_id, ", ".join(source["covered"])))
    report_coverage(source)


def report_source(manifest, source_id):
    known = {s["id"] for s in manifest["sources"]}
    if source_id not in known:
        raise SystemExit("нет такого источника: %s (есть: %s)" % (source_id, ", ".join(sorted(known))))

    source = next(s for s in manifest["sources"] if s["id"] == source_id)
    nodes = published(manifest)
    done = [n for n in nodes if source_id in n.get("audited", {})]
    todo = [n for n in nodes if source_id not in n.get("audited", {})]

    print("Источник: %s" % source["title"])
    print("Состояние источника: %s" % source.get("checked_at", "не указано"))
    print("Сильные стороны: %s" % ", ".join(source.get("strengths", [])))
    print("\nСверено: %d из %d опубликованных материалов" % (len(done), len(nodes)))
    report_coverage(source)

    if done:
        print("\nУже сверено:")
        for node in done:
            print("  %-28s %s" % (node["id"], node["audited"][source_id]))

    print("\nНе сверялось (%d) — план работ:" % len(todo))
    for node in todo:
        mark = "*" if source_id in node.get("sources", []) else " "
        print("  %s %-28s %s" % (mark, node["id"], node.get("module", "")))
    print("\n* — источник заявлен у материала, но сверка не подтверждена: это первая очередь.")


def mark(node_id, source_id, date):
    """Записать состоявшуюся сверку. Дата ставится только по факту проверки."""
    manifest = load()

    node = next((n for n in manifest["nodes"] if n["id"] == node_id), None)
    if node is None:
        raise SystemExit("нет такого узла: %s" % node_id)
    if source_id not in {s["id"] for s in manifest["sources"]}:
        raise SystemExit("нет такого источника: %s" % source_id)

    node.setdefault("audited", {})[source_id] = date

    with io.open(MANIFEST, "w", encoding="utf-8", newline="\n") as fh:
        json.dump(manifest, fh, ensure_ascii=False, indent=2)
        fh.write("\n")

    declared = " (заявлен у материала)" if source_id in node.get("sources", []) else " (не был заявлен)"
    print("Записано: %s x %s = %s%s" % (node_id, source_id, date, declared))


def main():
    args = sys.argv[1:]
    if args and args[0] == "cover":
        if len(args) < 3:
            raise SystemExit("нужно: cover <источник> <страницы> [страницы ...]")
        cover(args[1], args[2:])
        return

    if args and args[0] == "mark":
        if len(args) < 3:
            raise SystemExit("нужно: mark <узел> <источник> [дата]")
        import datetime
        date = args[3] if len(args) > 3 else datetime.date.today().isoformat()
        mark(args[1], args[2], date)
        return

    manifest = load()
    if args:
        report_source(manifest, args[0])
    else:
        report_all(manifest)


if __name__ == "__main__":
    main()
