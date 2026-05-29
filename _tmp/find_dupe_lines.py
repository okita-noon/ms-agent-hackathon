import re

src = open("scripts/line_qc/run.py", encoding="utf-8").read()
lines = src.split("\n")
pat = re.compile(r'"id":\s*(\d+),')
for i, line in enumerate(lines, 1):
    m = pat.search(line)
    if m and int(m.group(1)) >= 41:
        print(f"行{i}: {line.strip()}")
