# m3_aov.py —— 辛普森悖论题用：各用户分组的客单价差多少、订单占比多少（只读查询）
# 运行：python code\project\m3_aov.py
import duckdb, semantic as s

con = duckdb.connect(str(s.DB))
s.build_fact(con)
for by in ["store_group", "age_band", "income_band"]:
    df = con.execute(f"""
      WITH w AS (SELECT wk, {by} AS v, SUM(sales_value) AS g, COUNT(DISTINCT basket_id) AS n
                 FROM fact GROUP BY 1, 2),
           t AS (SELECT wk, SUM(g) AS tg, SUM(n) AS tn FROM w GROUP BY 1)
      SELECT COALESCE(v, '(空)') AS 取值,
             ROUND(MEDIAN(g / n), 1) AS 客单价,                     -- 每周客单价的中位数
             ROUND(MEDIAN(n / tn) * 100, 1) AS 订单占比_pct,
             ROUND(MEDIAN(tg / tn), 1) AS 全体客单价
      FROM w JOIN t USING (wk) GROUP BY 1 ORDER BY 2 DESC""").df()
    print(f"\n== {by}（{s.SEM['dimensions'][by]['name']}）==")
    print(df.to_string(index=False))
