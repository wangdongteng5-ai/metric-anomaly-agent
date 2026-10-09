# peek.py —— M1：用 SQL 查数据事实（时间、复购、周波动、分层样本量、营销活动）
# 运行：python code\project\peek.py（先跑 data_prep.py；不调模型，不用开 Ollama）
from pathlib import Path
import duckdb, pandas as pd
pd.set_option("display.unicode.east_asian_width", True)
pd.set_option("display.width", 200)

DB = Path(__file__).resolve().parents[2] / "data" / "cj.duckdb"
con = duckdb.connect(str(DB), read_only=True)
q = lambda sql: con.execute(sql).df()                          # SQL 结果直接转 DataFrame

print("① 基本情况"); print(q("""SELECT COUNT(*) 行数, COUNT(DISTINCT household_id) 家庭数,
    COUNT(DISTINCT store_id) 门店数, MIN(dt) 开始, MAX(dt) 结束, MAX(week) 周数 FROM transactions"""))

print("\n② 无效行（数量或金额 ≤ 0）"); print(q("""SELECT
    ROUND(100 * AVG(CASE WHEN is_sale THEN 0 ELSE 1 END), 1) 无效行占比 FROM transactions"""))

print("\n③ 复购：每户购物篮数"); print(q("""WITH h AS (SELECT household_id, COUNT(DISTINCT basket_id) n
    FROM transactions WHERE is_sale GROUP BY 1)
    SELECT ROUND(100 * AVG(CASE WHEN n >= 2 THEN 1 ELSE 0 END), 1) 复购家庭占比, MEDIAN(n) 中位篮数 FROM h"""))

print("\n④ 每周 GMV 与活跃家庭（看首尾周是否完整）"); w = q("""SELECT week, COUNT(DISTINCT dt) 天数,
    COUNT(DISTINCT household_id) 活跃家庭, ROUND(SUM(sales_value)) GMV
    FROM transactions WHERE is_sale GROUP BY 1 ORDER BY 1""")
print(w.head(3)); print("..."); print(w.tail(3))
print("周 GMV |环比| 中位数 / 90 分位：", w["GMV"].pct_change().abs().quantile([.5, .9]).round(3).tolist())

print("\n⑤ 分层样本量：按年龄，每层每周活跃家庭中位数（暂定 ≥ 100）"); print(q("""
    WITH x AS (SELECT t.week, d.age, COUNT(DISTINCT t.household_id) n FROM transactions t
               JOIN demographics d USING (household_id) WHERE t.is_sale GROUP BY 1, 2)
    SELECT age, MEDIAN(n) 每周活跃家庭 FROM x GROUP BY 1 ORDER BY 1"""))

print("\n⑥ 营销活动：类型、触达家庭、核销次数"); print(q("""
    WITH r AS (SELECT campaign_id, COUNT(*) k FROM coupon_redemptions GROUP BY 1),
         c AS (SELECT campaign_id, COUNT(DISTINCT household_id) h FROM campaigns GROUP BY 1)
    SELECT d.campaign_type 类型, COUNT(*) 活动数, SUM(c.h) 触达家庭次, SUM(COALESCE(r.k, 0)) 核销次数
    FROM campaign_descriptions d LEFT JOIN c USING (campaign_id) LEFT JOIN r USING (campaign_id)
    GROUP BY 1 ORDER BY 1"""))
