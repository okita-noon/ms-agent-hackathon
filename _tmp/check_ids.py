import re

src = open("scripts/line_qc/run.py", encoding="utf-8").read()
ids = [int(m) for m in re.findall(r'"id":\s*(\d+),', src)]
dupes = [x for x in set(ids) if ids.count(x) > 1]
print("ケース数:", len(ids))
print("重複ID:", sorted(dupes))
print("全ID:", sorted(ids))
