# stability.py —— M7 第 6 步（10-08）：稳定性 = 同一题跑 3 次，主因（定位）和动作是否一致（验收线：主因一致 ≥ 90%）
# 抽样规则（先定规则、再跑，不挑题）：交给模型判断的题按 md5(场景ID) 排序取前 10；代码直接判定的题每次结果必然相同，不抽
# 运行：先 python code\project\eval.py test r2 <10 个编号>、eval.py test r3 <同样 10 个>，再 python code\project\stability.py
import hashlib, sys, pandas as pd, semantic as s
D = s.ROOT / "data"
first = pd.read_csv(D / "eval_test_promptv3_h2.csv", encoding="utf-8-sig")
SAMPLE = sorted(sorted(first[first.判定 == "模型"].场景ID, key=lambda x: hashlib.md5(x.encode()).hexdigest())[:10])
if "list" in sys.argv: sys.exit(print(" ".join(SAMPLE)))                       # 只打印抽到的 10 个编号
runs = [first] + [pd.read_csv(D / f"eval_test_promptv3_h2_{r}.csv", encoding="utf-8-sig") for r in ("r2", "r3")]
rows = []
for i in SAMPLE:
    x = [r.set_index("场景ID").loc[i] for r in runs]
    loc, act = [str(r["判·定位"]) for r in x], [str(r["判·动作"]) for r in x]
    rows.append({"场景ID": i, "第1次定位": loc[0], "第2次定位": loc[1], "第3次定位": loc[2], "动作": " / ".join(act),
                 "主因一致": len(set(loc)) == 1, "动作一致": len(set(act)) == 1, "动作对(3次)": sum(bool(r["动作对"]) for r in x)})
out = pd.DataFrame(rows)
pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 250)
print(out.to_string(index=False))
print(f"\n主因一致 {out.主因一致.sum()}/10 = {out.主因一致.mean():.0%}（验收线 ≥ 90%）｜动作一致 {out.动作一致.sum()}/10｜3 次动作对 {out['动作对(3次)'].sum()}/30")
out.to_csv(D / "stability_test.csv", index=False, encoding="utf-8-sig")
