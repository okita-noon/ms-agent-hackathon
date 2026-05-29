import re

src = open("scripts/line_qc/run.py", encoding="utf-8").read()
ids = sorted([int(m) for m in re.findall(r'"id":\s*(\d+),', src)])
print(f"ケース数: {len(ids)}")
print(f"全ID: {ids}")
