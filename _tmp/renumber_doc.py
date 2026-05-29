import re
import sys

sys.stdout.reconfigure(encoding="utf-8")

src = open("docs/line_QC.md", encoding="utf-8").read()

# ケースID 15→32, 16→33, ..., 40→57（大きい数から置換）
# 対象パターン: 表の行・ケース見出し・まとめのケース番号参照
for old_id in range(40, 14, -1):
    new_id = old_id + 17
    # 表の行: | 15 |
    src = re.sub(r"(\|\s*)" + str(old_id) + r"(\s*\|)", r"\g<1>" + str(new_id) + r"\2", src)
    # ケース見出し: #### ケース15:
    src = re.sub(r"(#### ケース)" + str(old_id) + r":", r"\g<1>" + str(new_id) + ":", src)
    # まとめのケース番号: ケース1・3・15 など
    src = re.sub(r"(ケース)(" + str(old_id) + r")([・、\s])", r"\g<1>" + str(new_id) + r"\3", src)
    # 在庫0の完全欠品（スイカ）のラベル内番号
    src = src.replace(f"（ケース{old_id}）", f"（ケース{new_id}）")

open("docs/line_QC.md", "w", encoding="utf-8").write(src)
print("完了")
