# m2_explore.py —— M2 第 1、2 步：自然周 + 3 个分层规则的数据分布（只读，不改数据库）
# 运行：python code\project\m2_explore.py（先跑过 data_prep.py；不调模型）
from pathlib import Path
import duckdb, pandas as pd
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)

DB = Path(__file__).resolve().parents[2] / "data" / "cj.duckdb"
con = duckdb.connect(str(DB), read_only=True)
q = lambda sql: con.execute(sql).df()
T = "(SELECT *, DATE_TRUNC('week', dt) AS wk FROM transactions WHERE is_sale)"   # wk = 自然周（周一）

print("① 自然周：首尾各 3 周（天数 < 7 的是不完整周）")
w = q(f"SELECT wk, COUNT(DISTINCT dt) 天数, COUNT(DISTINCT household_id) 活跃家庭, ROUND(SUM(sales_value)) GMV FROM {T} GROUP BY 1 ORDER BY 1")
print(w.head(3)); print("..."); print(w.tail(3)); print("自然周总数：", len(w))

print("\n② 门店：GMV 集中度（按 GMV 从高到低累计）")
s = q(f"SELECT store_id, SUM(sales_value) gmv FROM {T} GROUP BY 1 ORDER BY 2 DESC")
s["累计占比"] = s.gmv.cumsum() / s.gmv.sum()
for k in [5, 10, 20, 50, 100]:
    print(f"  前 {k:>3} 家门店占 GMV {s.累计占比.iloc[k-1]:.0%}")
print("  贡献 < 0.1% GMV 的门店数：", (s.gmv / s.gmv.sum() < 0.001).sum(), "/", len(s))

print("\n③ 画像合并方案：每档每周活跃家庭中位数（目标 ≥ 100）")
for col, case in [("age", "CASE WHEN age IN ('19-24','25-34') THEN '34岁及以下' WHEN age IN ('35-44','45-54') THEN '35-54岁' ELSE '55岁及以上' END"),
                  ("income", "CASE WHEN income IN ('Under 15K','15-24K','25-34K') THEN '低(<35K)' WHEN income IN ('35-49K','50-74K') THEN '中(35-74K)' ELSE '高(75K+)' END")]:
    print(q(f"""WITH x AS (SELECT t.wk, {case} 档位, COUNT(DISTINCT t.household_id) n
               FROM {T} t JOIN demographics d USING (household_id) GROUP BY 1, 2)
               SELECT 档位, MEDIAN(n) 每周活跃家庭 FROM x GROUP BY 1 ORDER BY 1"""))

print("\n④ 流失天数 N：同一家庭相邻两次购物的间隔天数分布")
g = q(f"""WITH d AS (SELECT DISTINCT household_id, dt FROM {T}),
          x AS (SELECT dt - LAG(dt) OVER (PARTITION BY household_id ORDER BY dt) gap FROM d)
          SELECT QUANTILE_CONT(gap, [0.5, 0.8, 0.9, 0.95, 0.99]) q FROM x WHERE gap IS NOT NULL""")
print("  间隔天数 50% / 80% / 90% / 95% / 99% 分位：", [round(v) for v in g.q[0]])
