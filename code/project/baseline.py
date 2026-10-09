# baseline.py —— M3 第 7 步：规则基线 = 把映射表写死成固定工作流（不调大模型），作为 Agent 的对照组
# 运行：python code\project\baseline.py（先跑 inject.py、verify.py）→ data\baseline_result.csv
# 规则来源：规格说明书第 8 节映射表 v1.3；只看"环比"（不看前 4 周基准），这是基线的已知短板
import duckdb, pandas as pd, semantic as s
from inject import conditions

con = duckdb.connect(str(s.DB), read_only=True)
df = lambda sql: con.execute(sql).df()
HOLI = {h["wk"] for h in s.SEM["time"]["holidays"]}
USER = ["main_store_group", "age_band", "income_band", "camp"]       # 用户维度（camp = 近 2 周结束的活动触达用户）
ACTION = {"户数": "召回流失家庭", "频次": "提升频次", "客单价": "提升客单价"}

def scores(v, w, scope, dim):
    """某维度每个取值：本周各指标环比 ÷ 该取值历史 |环比| 的 90 分位 → 分数 < -1 即超出正常范围"""
    camp = f"""household_id IN (SELECT household_id FROM campaigns JOIN campaign_descriptions USING (campaign_id)
               WHERE end_date BETWEEN DATE '{w}' - 14 AND DATE '{w}' - 1)"""
    col = {"camp": f"IF({camp}, '活动触达', NULL)", "全部": "'全部'"}.get(dim, dim)
    d = df(f"""SELECT wk, {col} grp, SUM(sales_value) GMV, COUNT(DISTINCT household_id) 户数, COUNT(DISTINCT basket_id) od
               FROM {v} WHERE {scope} AND wk <= DATE '{w}' GROUP BY 1, 2 HAVING grp IS NOT NULL ORDER BY 1""")
    d["频次"], d["客单价"] = d.od / d.户数, d.GMV / d.od
    out = []
    for grp, x in d.groupby("grp"):
        x = x.set_index("wk")
        mets = ["GMV"] if dim in ("department", "product_category") else ["户数", "频次", "客单价"]
        for m in mets:
            c = x[m].pct_change()
            if pd.Timestamp(w) not in c.index: continue
            q90 = c.drop(pd.Timestamp(w)).abs().quantile(.9)
            out.append((c[pd.Timestamp(w)] / q90, dim, grp, m))
    return out

def diagnose(v, w, scope, tx="transactions"):
    """固定工作流：节假日 → 数据质量 → 找最异常的 (维度, 取值, 指标) → 查映射表"""
    if w in HOLI: return "正常波动", "—", "—", "不行动"            # 映射表：节假日表内 → 不行动（先判）
    bad = con.execute(f"SELECT AVG(IF(is_sale, 0, 1)) FROM {tx} WHERE DATE_TRUNC('week', dt) = DATE '{w}'").fetchone()[0]
    day = df(f"""SELECT ISODOW(dt) d, SUM(IF(wk = DATE '{w}', sales_value, 0)) / SUM(IF(wk = DATE '{w}' - 7, sales_value, 0)) - 1 c
                 FROM {v} WHERE {scope} AND wk IN (DATE '{w}', DATE '{w}' - 7) GROUP BY 1 ORDER BY 1""").c
    st = con.execute(f"""SELECT SUM(IF(n = 0, l, 0)) / SUM(l) FROM (SELECT store_id, SUM(IF(wk = DATE '{w}', 1, 0)) n,
                 SUM(IF(wk = DATE '{w}' - 7, sales_value, 0)) l FROM {v} WHERE wk IN (DATE '{w}', DATE '{w}' - 7) GROUP BY 1)""").fetchone()[0]
    drop = (day.sort_index() < -.3).tolist()                         # "某几天集中下跌" = 连续 ≥ 2 天跌超 30%
    if bad > .02 or any(a and b for a, b in zip(drop, drop[1:])) or st > .05:
        return "数据问题", "—", "—", "修数据"
    dims = USER + ["department"] + (["product_category"] if "department" in scope else [])
    cand = [x for dim in dims + ["全部"] for x in scores(v, w, scope, dim)]
    sc, dim, grp, m = min(cand)
    if sc > -1: return "正常波动", "—", "—", "不行动"                    # 所有分组 × 指标都在自身 90 分位内
    if dim in ("department", "product_category"): return "商品侧", grp, m, "排查商品"
    return "用户侧", grp if dim != "全部" else "全部", m, "补券" if dim == "camp" else ACTION[m]

if __name__ == "__main__":
    m = pd.read_csv(s.ROOT / "data" / "manifest.csv", dtype=str, encoding="utf-8-sig").fillna("")
    res = []
    for r in m.itertuples():
        scope = conditions(r)[0] if r.手法 != "无注入" else "TRUE"
        print(f"诊断 {r.场景ID} …", flush=True)                       # 进度提示
        con.execute(f"CREATE OR REPLACE TEMP TABLE v AS SELECT * FROM fact_{r.场景ID} WHERE wk <= DATE '{r.周}'")  # 物化一次，提速
        typ, loc, fac, act = diagnose("v", r.周, scope, "tx_S12" if r.场景ID == "S12" else "transactions")
        truth_loc = {"campaign": "活动触达"}.get(r.维度, {"活跃用户数": "户数"}.get(r.取值, r.取值))
        if r.维度 == "拆解因子": loc = fac                          # 分层题：定位 = 拆解因子
        res.append({"场景ID": r.场景ID, "题型": r.题型, "真·主因": r.主因类型, "判·主因": typ, "真·定位": truth_loc, "判·定位": loc,
                    "真·动作": r.正确动作, "判·动作": act, "主因对": typ == r.主因类型, "动作对": act == r.正确动作,
                    "定位对": (loc in truth_loc.split("+")) if r.维度 not in ("", "dt", "store_id", "全部") else None})
    out = pd.DataFrame(res)
    out.to_csv(s.ROOT / "data" / "baseline_result.csv", index=False, encoding="utf-8-sig")
    pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 220)
    print(out.to_string(index=False))
    for k in ["主因对", "定位对", "动作对"]:
        x = out[k].dropna().astype(bool); print(f"{k}：{x.sum()}/{len(x)} = {x.mean():.0%}")
