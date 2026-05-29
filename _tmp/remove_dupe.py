src = open("scripts/line_qc/run.py", encoding="utf-8").read()
lines = src.split("\n")

# 行695まで（0-indexed: 0〜694）+ 行999から末尾
kept = lines[:695] + lines[998:]
result = "\n".join(kept)
open("scripts/line_qc/run.py", "w", encoding="utf-8").write(result)

import re

ids = sorted([int(m) for m in re.findall(r'"id":\s*(\d+),', result)])
dupes = [x for x in set(ids) if ids.count(x) > 1]
print(f"ケース数: {len(ids)}")
print(f"重複ID: {dupes}")
print(f"全ID: {ids}")
