# m3_stores.py —— 门店概况：每家门店的全年 GMV、占比、累计占比（只读查询）
# 运行：python code\project\m3_stores.py
import duckdb, semantic as s

con = duckdb.connect(str(s.DB))
s.build_fact(con)
df = con.execute("""
WITH st AS (SELECT store_id, store_group, SUM(sales_value) AS gmv,
                   COUNT(DISTINCT household_id) AS hh, COUNT(DISTINCT basket_id) AS orders
            FROM fact GROUP BY 1, 2)
SELECT ROW_NUMBER() OVER (ORDER BY gmv DESC) AS 排名, store_id, store_group AS 分组,
       ROUND(gmv) AS 全年GMV, hh AS 家庭数, orders AS 订单数,
       ROUND(gmv / SUM(gmv) OVER () * 100, 2) AS 占比_pct,
       ROUND(SUM(gmv) OVER (ORDER BY gmv DESC) / SUM(gmv) OVER () * 100, 1) AS 累计_pct
FROM st ORDER BY gmv DESC""").df()

print(f"门店数：{len(df)}｜全年 GMV 合计：{df['全年GMV'].sum():,.0f} 美元")
print("\n== 前 25 家 ==")
print(df.head(25).to_string(index=False))
print("\n== 按分组汇总 ==")
print(df.groupby("分组").agg(门店数=("store_id", "count"), GMV=("全年GMV", "sum"),
      占比_pct=("占比_pct", "sum"), 单店GMV中位数=("全年GMV", "median")).round(1).to_string())
