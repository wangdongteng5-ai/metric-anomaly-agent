# ask_eval.py —— M8 自由追问评估：执行准确率（模型 SQL 的执行结果 = 标准答案 SQL 的执行结果，才算对）
# 运行：python code\project\ask_eval.py [题集] [版本] [gold]　例：ask_eval.py 追问测试集_v2 v1 gold（只跑标准答案）｜ask_eval.py 追问开发集 v2
# 题集默认 追问测试集、版本默认 v1（= 第一次正式运行）；v1 = ask_v1.py（冻结），v2 = ask.py；开发集可反复跑，其他题集只能跑一次
import importlib, math, sys, duckdb, pandas as pd
from semantic import ROOT, DB

WEEK, CAUSE = "2017-07-24", ("main_store_group", "腰部")      # 固定评测上下文（出题时定，不改）
args = [a for a in sys.argv[1:] if a != "gold"] + [None, None]
SET, VER = args[0] or "追问测试集", args[1] or "v1"
ask = importlib.import_module({"v1": "ask_v1", "v2": "ask"}[VER]).ask
TEST = ROOT / "docs" / f"{SET}.csv"
OUT = ROOT / "data" / (f"ask_eval_{VER}.csv" if SET == "追问测试集" else f"ask_eval_{SET}_{VER}.csv")

def cell(x):                                                   # 数值统一成 float，空值统一成 None，其他转字符串
    if x is None or (isinstance(x, float) and math.isnan(x)): return None
    try: return float(x) if not isinstance(x, str) else x
    except (TypeError, ValueError): return str(x)

def norm(df, ordered):                                         # 结果表 → 行列表；不看列名；不要求顺序时排序后再比
    rows = [tuple(cell(x) for x in r) for r in df.itertuples(index=False)]
    return rows if ordered else sorted(rows, key=lambda r: [f"{x:.2f}" if isinstance(x, float) else str(x) for x in r])

def same(a, b):                                                # 行数、列数相同，数值差 ≤ 0.01（= 保留 2 位小数比对），其余完全相等
    return len(a) == len(b) and all(len(ra) == len(rb) and all(abs(x - y) <= 0.01 if isinstance(x, float) and isinstance(y, float)
           else x == y for x, y in zip(ra, rb)) for ra, rb in zip(a, b))

test, gold = pd.read_csv(TEST, encoding="utf-8-sig"), {}
with duckdb.connect(str(DB), read_only=True) as con:          # 第 1 步：标准答案全部跑通，才开始调模型
    for t in test.itertuples():
        if t.标准SQL != "REFUSE": gold[t.id] = con.execute(t.标准SQL).df()
        print(f"\n{t.id} {t.问题}\n{gold.get(t.id, 'REFUSE')}")
if "gold" in sys.argv: sys.exit()
if OUT.exists() and "开发" not in SET: sys.exit(f"{OUT.name} 已存在：测试集只跑一次。改了系统要换版本号，并先预注册")

rows = []
for t in test.itertuples():                                    # 第 2 步：逐题调 ask（不生成解读，只比 SQL 结果）
    r = ask(t.问题, WEEK, CAUSE, explain=False)
    if t.id not in gold: ok, why = r["拒答"], "" if r["拒答"] else "没拒答"
    elif r["拒答"] or "报错" in r: ok, why = False, "误拒答" if r["拒答"] else "3 次都报错"
    else: ok = same(norm(r["结果"], t.看顺序 == "是"), norm(gold[t.id], t.看顺序 == "是")); why = "" if ok else "结果不同"
    rows.append({"id": t.id, "难度": t.难度, "考点": t.考点, "对": ok, "原因": why, "尝试": r["尝试"], "模型SQL": r.get("sql", ""),
                 "报错": r.get("报错", ""), "模型结果前5行": r["结果"].head(5).to_string() if "结果" in r else ""})
    print(t.id, "✓" if ok else "✗", why, "｜", r.get("sql"))
df = pd.DataFrame(rows); df.to_csv(OUT, index=False, encoding="utf-8-sig")
print(f"\n执行准确率 {df.对.sum()}/{len(df)}｜按难度：\n{df.groupby('难度').对.agg(['sum', 'count'])}\n明细：{OUT}")
