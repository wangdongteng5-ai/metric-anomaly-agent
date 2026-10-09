# ⚠️ v1.8（10-08 M7 开场，Morgan）：审批移出项目范围，本文件保留不用、不参与评估
# approve.py —— M6 6-5（10-08）人工审批 = 第 ④ 层评估：按固定核对清单逐条判断，全部通过才算"可直接执行"
# 运行：cd D:\ai-agent-learning → python code\project\approve.py（M7 测试集生成方案卡后统一审）
# 局限：审批由作者按清单执行，非真实运营（写进 README）
import csv, datetime as dt
from pathlib import Path
DIR = Path(__file__).resolve().parents[2] / "data" / "plans"
LOG = DIR / "approvals.csv"
CHECK = ["名单人数和 SQL 抽查一致", "写清了实验组和对照组人数", "成本在每户上限内",
         "方案说明和诊断结论一致", "风险提示引用了策略手册"]        # 核对清单（10-08 草稿，M7 前可改，改后冻结）

todo = [p for p in sorted(DIR.glob("*.md")) if "状态：待人工确认" in p.read_text(encoding="utf-8")]
if not todo: print("没有待确认的方案卡")
for p in todo:
    text = p.read_text(encoding="utf-8")
    print("\n" + "=" * 60 + "\n" + text.split("## 材料")[0])                       # 只显示摘要和说明，材料在文件里
    if input("审这张卡？回车开始，输入 s 跳过：").strip().lower() == "s": continue
    fail = [c for c in CHECK if input(f"  {c}？(y/n)：").strip().lower() != "y"]   # 不是 y 就算没通过
    note = input("补充说明（可空）：").strip()
    status = "已通过" if not fail else "已驳回"
    why = "；".join(fail + [note] * bool(note)) or "清单全部通过"
    p.write_text(text.replace("状态：待人工确认", f"状态：{status}（{why}）"), encoding="utf-8")
    new = not LOG.exists()
    with open(LOG, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new: w.writerow(["时间", "方案卡", "决定", "未通过项", "补充"] + CHECK)
        w.writerow([dt.datetime.now().isoformat(timespec="seconds"), p.name, status, "；".join(fail), note]
                   + [int(c not in fail) for c in CHECK])
    print(f"已记录：{status}（{why}）")
