# m3_shares.py —— M3 第 5 步：各维度每个取值占总 GMV 的比例（设计异常幅度用）
# 运行：python code\project\m3_shares.py（只读查询）
import duckdb, semantic as s

con = duckdb.connect(str(s.DB))
s.build_fact(con)
dims = [k for k, d in s.SEM["dimensions"].items() if d["sql"]]      # 有 sql 的维度才能下钻

for by in dims:
    start = s.SEM["dimensions"][by].get("valid_from", s.SEM["time"]["valid_from"])
    df = con.execute(f"""
      WITH w AS (SELECT wk, {by} AS v, SUM(sales_value) AS g, COUNT(DISTINCT household_id) AS hh
                 FROM fact WHERE wk >= DATE '{start}' GROUP BY 1, 2),
           t AS (SELECT wk, SUM(g) AS tg FROM w GROUP BY 1)
      SELECT COALESCE(v, '(空)') AS 取值,
             ROUND(MEDIAN(g / tg) * 100, 1) AS 占总GMV_pct,          -- 每周占比的中位数
             CAST(MEDIAN(hh) AS INT) AS 每周活跃家庭
      FROM w JOIN t USING (wk) GROUP BY 1 ORDER BY 2 DESC""").df()
    print(f"\n== {by}（{s.SEM['dimensions'][by]['name']}）==")
    print(df.head(10).to_string(index=False))                        # 品类只看前 10
