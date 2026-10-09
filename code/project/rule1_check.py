# rule1_check.py —— 标准① 两种写法对比（只读 v3 的 trace，不调模型，约 1 秒）
# 运行：cd D:\ai-agent-learning → python code\project\rule1_check.py
# 新写法 = 只要 vs前4周中位数 < 0（现行）；原写法 = 再加"环比 < 0"
import json, sys, pandas as pd
sys.path.insert(0, "code/project")
from audit import fails, expect                       # 复用 code_review 的同一套 ①②③ 判断

man = pd.read_csv("data/manifest.csv", encoding="utf-8-sig").set_index("场景ID")
rows = []
for line in open("data/eval_promptv3_h2_trace.jsonl", encoding="utf-8"):
    r = json.loads(line)
    ctx = next((json.loads(t["结果"]) for t in r["trace"] if t["工具"] == "候选清单"), None)
    if ctx is None: continue                           # 代码直接判定的题（数据问题 / 节假日 / 0 候选），不受标准①影响
    new_ok = [c for c in ctx["候选"] if not fails(c, ctx)]          # 新写法下通过 ①②③
    flip = [c for c in new_ok if c["环比"] >= 0]                     # 环比在涨 → 原写法会排除的
    old_ok = [c for c in new_ok if c["环比"] < 0]
    pick = lambda ok: expect(min(ok, key=lambda c: min(c["异常分数"], c["中位数异常分数"] or 0)), ctx["提问范围"])[1] if ok else "不行动"
    sid = r["场景ID"]
    rows.append({"场景": sid, "真动作": man.loc[sid, "正确动作"], "通过①②③": len(new_ok), "其中环比≥0": len(flip),
                 "环比≥0的候选": "；".join(f"{c['维度']}={c['分组']}·{c['指标']}(环比{c['环比']:+.1%})" for c in flip),
                 "代码版·新写法": pick(new_ok), "代码版·原写法": pick(old_ok)})
df = pd.DataFrame(rows)
pd.set_option("display.width", 250, "display.max_colwidth", 80)
print(df[df["其中环比≥0"] > 0].to_string(index=False))
c = df["场景"].str.startswith("C")
print(f"\n进入复核的题：{len(df)}（对照周 {c.sum()}）｜有'环比≥0 且通过①②③'候选的题：{(df['其中环比≥0'] > 0).sum()}")
print(f"这类候选总数：异常题 {df.loc[~c, '其中环比≥0'].sum()} 个｜对照周 {df.loc[c, '其中环比≥0'].sum()} 个")
for k in ("代码版·新写法", "代码版·原写法"):
    print(f"{k}：动作对 {(df[k] == df['真动作']).sum()}/{len(df)}｜对照周误报 {(df.loc[c, k] != '不行动').sum()}/{c.sum()}")
