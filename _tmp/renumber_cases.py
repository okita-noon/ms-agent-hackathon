import re, sys

sys.stdout.reconfigure(encoding="utf-8")

src = open("scripts/line_qc/run.py", encoding="utf-8").read()

# 15→32, 16→33, ..., 40→57（大きい数から置換してダブルヒット防止）
for old_id in range(40, 14, -1):
    new_id = old_id + 17
    src = re.sub(r'("id":\s*)' + str(old_id) + r"(,)", r"\g<1>" + str(new_id) + r"\2", src)

open("scripts/line_qc/run.py", "w", encoding="utf-8").write(src)

ids = [int(m) for m in re.findall(r'"id":\s*(\d+),', src)]
print(f"ケース数: {len(ids)}, ID範囲: {min(ids)}-{max(ids)}")
print(f"全ID: {sorted(ids)}")
