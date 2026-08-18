"""Собрать весь сайт целиком: базу знаний, новости, хаб, портал.

Порядок важен: портал читает превью из трех остальных, поэтому
собирается последним.

    python build.py
"""

import subprocess
import sys
import os

BASE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable

STEPS = [
    os.path.join("kb", "build_index.py"),
    os.path.join("news", "build_feed.py"),
    os.path.join("hub", "build_hub.py"),
    "build_portal.py",
]

for step in STEPS:
    subprocess.run([PY, os.path.join(BASE, step)], check=True, cwd=BASE)
