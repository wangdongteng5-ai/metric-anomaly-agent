# m3_holidays.py —— M3 第 2 步：看每周 GMV 环比 + 美国节日，决定节假日表范围
# 运行：python code\project\m3_holidays.py（只读查询，不改数据库里的表）
import duckdb, semantic as s

HOLIDAYS = {  # 2017 年美国主要节日 → 所在自然周（周一日期）
    "2017-01-02": "元旦（补休 1-2）",       "2017-01-16": "马丁·路德·金日",
    "2017-01-30": "超级碗（2-5 周日）",     "2017-02-13": "情人节（2-14）",
    "2017-02-20": "总统日",                 "2017-04-10": "复活节（4-16 周日）",
    "2017-05-08": "母亲节（5-14 周日）",     "2017-05-29": "阵亡将士纪念日",
    "2017-06-12": "父亲节（6-18 周日）",     "2017-07-03": "独立日（7-4）",
    "2017-09-04": "劳动节",                 "2017-10-30": "万圣节（10-31）",
    "2017-11-20": "感恩节（11-23）",         "2017-12-18": "圣诞前采购周（含 12-24）",
    "2017-12-25": "圣诞周",
}

con = duckdb.connect(str(s.DB))
s.build_fact(con)
df = con.execute("""
SELECT strftime(wk, '%Y-%m-%d') AS wk,
       SUM(sales_value) AS gmv, COUNT(DISTINCT basket_id) AS orders,
       COUNT(DISTINCT household_id) AS hh, COUNT(DISTINCT dt) AS days
FROM fact GROUP BY 1 ORDER BY 1""").df()

df["wow"] = df["gmv"].pct_change() * 100                       # GMV 环比（%）
df["holiday"] = df["wk"].map(HOLIDAYS).fillna("")
df["big"] = df["wow"].abs().gt(15.6).map({True: "★", False: ""})  # |环比| > 90 分位

print(df.round({"gmv": 0, "wow": 1}).to_string(index=False))
big = df["big"] == "★"
print(f"\n|环比| > 15.6% 的周：{big.sum()} 个，其中落在节日周：{(big & (df['holiday'] != '')).sum()} 个")
