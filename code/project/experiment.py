# experiment.py —— M6 6-4（10-08）design_test：对照组比例 → 能测出多大的效果（MDE）+ 哈希分组写回人群包
# 自然回流率 p 用本周之前 8 周的历史算（同一分组、同一圈人规则、看"下一周"结果），不偷看未来
# 自测：cd D:\ai-agent-learning → python code\project\experiment.py（不需要 Ollama）
import math, hashlib, pandas as pd, tools as tl
from audience import PICK
from playbook import playbook_rule
Z = 1.96 + 0.84                                               # 双侧 α = 0.05、power = 0.8
OK = {"召回流失家庭": "bn > 0", "补券": "bn >= b4 / 4", "提升频次": "bn >= b4 / 4",   # "回来了"的定义（下一周）
      "提升客单价": "bn > 0 and gn / bn >= g4 / b4"}

def base_rate(week, action, dim, group, filter=None):
    """历史 8 周：每周按同样规则圈人，看下一周有多少人自己"回来"（不发券时的自然回流率）"""
    scope = tl._scope(week, filter)[0]
    grp = ("TRUE" if dim == "全部" else tl.CAMP.format(w=week) + " IS NOT NULL" if dim == "camp"
           else tl._scope(week, {"dim": dim, "value": group})[0])
    f = tl.con.execute(f"""
      WITH hw AS (SELECT household_id, wk, COUNT(DISTINCT basket_id) b, SUM(sales_value) g FROM {tl.SRC}
                  WHERE wk BETWEEN DATE '{week}' - 91 AND DATE '{week}' AND {scope} AND {grp} GROUP BY 1, 2),
      x AS (SELECT h.household_id, k.wk, COALESCE(b, 0) b, COALESCE(g, 0) g FROM (SELECT DISTINCT household_id FROM hw) h
            CROSS JOIN (SELECT DISTINCT wk FROM hw) k LEFT JOIN hw USING (household_id, wk))
      SELECT * FROM (SELECT wk, b b1, g g1, SUM(b) OVER w4 b4, SUM(g) OVER w4 g4, LEAD(b) OVER o bn, LEAD(g) OVER o gn
        FROM x WINDOW o AS (PARTITION BY household_id ORDER BY wk), w4 AS (o ROWS BETWEEN 4 PRECEDING AND 1 PRECEDING))
      WHERE wk BETWEEN DATE '{week}' - 56 AND DATE '{week}' - 7""").df()   # 下一周 ≤ 本周，结果已知
    pick = f.query(PICK[action])
    return float(pick.eval(OK[action]).mean()), len(pick) / pick.wk.nunique()

def design_test(aud, ratios=(0.1, 0.2, 0.3, 0.5), salt=None):
    """aud = build_audience 的输出；返回每种对照组比例的 MDE；按 yaml 的 holdout_ratio 哈希分组写回 CSV"""
    hold, salt = playbook_rule(aud["动作"])["holdout_ratio"], salt or f"{aud['动作']}_{aud['主因分组']}"
    p, n_hist = base_rate(aud["周"], aud["动作"], *aud["主因分组"].split("=", 1))
    n, hi = aud["最终人数"], max(aud["核销率区间"])           # 券的效果上限 ≈ 用券的人都是被券拉回来的
    rows = []
    for r in ratios:
        mde = Z * math.sqrt(p * (1 - p) * (1 / (n * (1 - r)) + 1 / (n * r)))
        rows.append({"对照组比例": r, "实验组": round(n * (1 - r)), "对照组": round(n * r), "MDE": round(mde, 3),
                     "测得出上限吗": mde <= hi, "要累计几周(测6.5pp)": math.ceil((mde / 0.065) ** 2)})
    df = pd.read_csv(aud["人群包"])
    df["组"] = ["对照" if int(hashlib.md5(f"{salt}_{h}".encode()).hexdigest(), 16) % 100 < hold * 100 else "实验"
               for h in df.household_id]                     # 同一户 + 同一实验名 → 永远同一组（可跨周累计）
    df.to_csv(aud["人群包"], index=False)
    return {"自然回流率(历史8周)": round(p, 3), "历史每周名单": round(n_hist), "名单": n, "效果上限(核销率)": hi,
            "方案": rows, "对照组比例": hold, "分组": df["组"].value_counts().to_dict(), "实验名": salt,
            "说明": "MDE = 能稳定测出的最小增量（百分点）；MDE > 效果上限 = 单周测不出，需累计多周或接受只做方向判断"}

if __name__ == "__main__":
    from audience import build_audience
    for src, args in [("fact", ("2017-07-24", "召回流失家庭", "main_store_group", "腰部")),
                      ("fact_S03", ("2017-04-03", "提升频次", "main_store_group", "腰部"))]:
        tl.SRC = src; aud = build_audience(*args)
        res = design_test(aud)
        print(src, {k: v for k, v in res.items() if k != "方案"}); print(pd.DataFrame(res["方案"]).to_string(index=False))
