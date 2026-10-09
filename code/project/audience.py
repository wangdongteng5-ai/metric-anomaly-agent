# audience.py —— M6 6-3（10-08）build_audience：主因分组 + 动作 → 人群包 CSV + 规则校验 + 预期影响（全部由代码算）
# 圈人规则、排除规则、核销率、面额全部来自 playbook.yaml（playbook_rule），这里不写任何数字
# 自测：cd D:\ai-agent-learning → python code\project\audience.py（不需要 Ollama）
import pandas as pd, tools as tl
from pathlib import Path
from playbook import playbook_rule
OUT = Path(tl.s.DB).parent / "audience"                       # data\audience\
PICK = {"召回流失家庭": "b4 > 0 and b1 == 0",                  # A（10-08 Morgan）：前 28 天买过、本周 0 单；浪费由对照组量化
        "提升频次": "b1 > 0 and b1 < b4 / 4",                 # 本周单数 < 自己前 4 周周均
        "补券": "b1 > 0 and b1 < b4 / 4",
        "提升客单价": "b1 > 0 and b4 > 0 and g1 / b1 < g4 / b4"}  # 本周客单价 < 自己前 4 周客单价

def build_audience(week, action, dim, group, filter=None):
    if action not in PICK: return {"动作": action, "说明": "该动作不圈人（见策略手册）"}
    p, (scope, name) = playbook_rule(action), tl._scope(week, filter)
    grp = ("TRUE" if dim == "全部" else tl.CAMP.format(w=week) + " IS NOT NULL" if dim == "camp"
           else tl._scope(week, {"dim": dim, "value": group})[0])            # 复用 _scope：校验分组名是否存在
    w = f"DATE '{week}'"
    df = tl.con.execute(f"""
      WITH h AS (SELECT household_id,
          COUNT(DISTINCT basket_id) FILTER (WHERE wk = {w}) b1, SUM(sales_value) FILTER (WHERE wk = {w}) g1,
          COUNT(DISTINCT basket_id) FILTER (WHERE wk < {w}) b4, SUM(sales_value) FILTER (WHERE wk < {w}) g4
        FROM {tl.SRC} WHERE wk BETWEEN {w} - 28 AND {w} AND {scope} AND {grp} GROUP BY 1),
      fat AS (SELECT household_id FROM campaigns JOIN campaign_descriptions USING (campaign_id)
        WHERE CAST(start_date AS DATE) < {w} GROUP BY 1 HAVING COUNT(DISTINCT campaign_id) >= {p['fatigue_min_campaigns']}
          AND household_id NOT IN (SELECT household_id FROM coupon_redemptions WHERE CAST(redemption_date AS DATE) < {w})),
      cap AS (SELECT household_id FROM campaigns JOIN campaign_descriptions USING (campaign_id)
        WHERE CAST(start_date AS DATE) <= LAST_DAY({w}) AND CAST(end_date AS DATE) >= DATE_TRUNC('month', {w})
        GROUP BY 1 HAVING COUNT(DISTINCT campaign_id) >= {p['freq_cap_per_month']})
      SELECT h.*, household_id IN (SELECT * FROM fat) 疲劳, household_id IN (SELECT * FROM cap) 频控满
      FROM h""").df()
    if df.empty: return {"动作": action, "主因分组": f"{dim}={group}", "错误": "该分组在这几周没有交易（camp：近 2 周没有结束的活动）"}
    aov = float(df.g4.sum() / df.b4.sum())                                         # 该组前 4 周客单价
    pick = df.query(PICK[action])                                            # 按动作的圈人规则筛
    keep = pick[~pick.疲劳 & ~pick.频控满]
    rate = p["核销率区间"] if "核销率区间" in p else _camp_rate(week) or [0.065, 0.166]
    OUT.mkdir(exist_ok=True); f = OUT / f"{tl.SRC}_{week}_{action}.csv"
    keep[["household_id"]].to_csv(f, index=False)
    users = [round(len(keep) * x, 1) for x in rate]
    per_hh = p["coupons_per_hh"] * p["coupon_face"]
    return {"动作": action, "周": week, "范围": name, "主因分组": f"{dim}={group}", "圈人": len(pick),
            "排除疲劳": int(pick.疲劳.sum()), "排除频控": int((~pick.疲劳 & pick.频控满).sum()), "最终人数": len(keep),
            "权益": p["benefit"], "核销率区间": rate, "预期用券户": users,
            "成本区间": [round(u * per_hh, 2) for u in users], "用券户GMV区间（非增量）": [round(u * aov, 2) for u in users],
            "该组前4周客单价": round(aov, 2), "提示": "用券户里有一部分本来就会回来，增量需实验验证（design_test）",
            "规则校验": {"单户成本≤上限": per_hh <= p["max_cost_per_hh"], "名单不含疲劳户": not keep.疲劳.any(),
                       "名单不含频控满": not keep.频控满.any()}, "人群包": str(f), "状态": "待人工确认"}

def _camp_rate(week):
    """补券：近 2 周结束的活动，自己的户级核销率（核销户 ÷ 触达户）"""
    x = tl.con.execute(f"""SELECT COUNT(DISTINCT r.household_id) * 1.0 / COUNT(DISTINCT c.household_id)
        FROM campaigns c JOIN campaign_descriptions d USING (campaign_id)
        LEFT JOIN coupon_redemptions r ON r.campaign_id = c.campaign_id AND r.household_id = c.household_id
        WHERE CAST(d.end_date AS DATE) BETWEEN DATE '{week}' - 14 AND DATE '{week}' - 1""").fetchone()[0]
    return [round(x, 3)] * 2 if x == x and x else None            # x == x：排除 NULL / NaN

if __name__ == "__main__":                                   # 同一周：注入版 vs 原始版，差值 ≈ 被删掉的家庭
    for src in ["fact_S01", "fact"]:
        tl.SRC = src
        print(src, build_audience("2017-07-24", "召回流失家庭", "main_store_group", "腰部"))
    tl.SRC = "fact_S03"; print(build_audience("2017-04-03", "提升频次", "main_store_group", "腰部"))
    print(build_audience("2017-04-03", "排查商品", "department", "MEAT"))
