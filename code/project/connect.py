# connect.py —— M8（10-09）接入新数据集：执行 adapter.sql → 检查数据契约 → 建 fact 视图
# 运行：cd D:\ai-agent-learning → python code\project\connect.py cj_ecom（不调模型）；之后 .env 里加一行 DATASET=cj_ecom 即切换
# 每个数据集一个文件夹 datasets\<名字>\：adapter.sql（列名映射）+ metrics.yaml（时间范围、节假日、维度、质量阈值）
import os, sys
os.environ["DATASET"] = sys.argv[1]                     # 必须在 import semantic 之前设好
import duckdb, semantic as s
NUM = ("DOUBLE", "FLOAT", "DECIMAL", "INTEGER", "BIGINT", "HUGEINT")
CONTRACT = {                                           # 数据契约：表 → {列: 类型要求}；"" = 任意类型
    "transactions": {"dt": "DATE", "household_id": "", "basket_id": "", "store_id": "", "product_id": "",
                     "sales_value": "数值", "is_sale": "BOOLEAN"},
    "products": {"product_id": "", "department": "", "product_category": ""},
    "demographics": {"household_id": "", "age": "", "income": ""},           # 以下 4 张可以为空
    "campaigns": {"campaign_id": "", "household_id": ""},
    "campaign_descriptions": {"campaign_id": "", "start_date": "DATE", "end_date": "DATE"},
    "coupon_redemptions": {"household_id": "", "campaign_id": "", "redemption_date": "DATE"}}
EMPTY_OK = {"demographics": "年龄 / 收入维度（metrics.yaml 里把 age_band、income_band 的 sql 设为 null）", "campaigns": "活动维度、疲劳 / 频控排除、补券",
            "campaign_descriptions": "同上", "coupon_redemptions": "疲劳排除、补券核销率"}

os.chdir(s.ROOT)                                       # adapter.sql 里的相对路径以项目根目录为准
con = duckdb.connect(str(s.DB))
con.execute((s.HERE / "adapter.sql").read_text(encoding="utf-8"))
err, warn = [], []
for t, cols in CONTRACT.items():                       # ① 结构：表、列、类型
    have = dict(con.execute(f"SELECT column_name, data_type FROM information_schema.columns WHERE table_name = '{t}'").fetchall())
    if not have: err.append(f"缺表 {t}"); continue
    for c, ty in cols.items():
        if c not in have: err.append(f"{t} 缺列 {c}")
        elif ty and not (have[c].startswith(NUM) if ty == "数值" else have[c] == ty): err.append(f"{t}.{c} 是 {have[c]}，要求 {ty}")
    n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
    if not n: (warn if t in EMPTY_OK else err).append(f"{t} 为空" + (f" → 关闭：{EMPTY_OK[t]}" if t in EMPTY_OK else ""))
if not err:                                            # ② 内容：粒度、订单一致性、历史长度
    T = s.SEM["time"]
    rows, uniq, bad, weeks = con.execute(f"""SELECT COUNT(*), COUNT(DISTINCT (basket_id, product_id)),
        (SELECT COUNT(*) FROM (SELECT basket_id FROM transactions GROUP BY 1 HAVING COUNT(DISTINCT household_id) > 1
                                OR COUNT(DISTINCT store_id) > 1 OR COUNT(DISTINCT dt) > 1)),
        COUNT(DISTINCT DATE_TRUNC('week', dt)) FILTER (WHERE is_sale AND dt BETWEEN DATE '{T['valid_from']}' AND DATE '{T['valid_to']}' + 6)
        FROM transactions""").fetchone()
    if rows > uniq: warn.append(f"(订单, 商品) 重复 {rows - uniq:,} 行：确认不是 JOIN 放大")
    if bad: err.append(f"{bad:,} 个订单对应多个用户 / 门店 / 日期：订单头映射有误")
    if weeks < 5: err.append(f"有效周只有 {weeks} 周：异常分数至少要 5 周历史")
    elif weeks < 20: warn.append(f"有效周 {weeks} 周（< 20），异常分数的 90 分位不稳")
for x in warn: print("⚠️", x)
for x in err: print("❌", x)
if err: sys.exit("数据契约未通过：改 adapter.sql 后重跑")
s.build_fact(con)
print(f"✅ {s.DATASET} 接入完成：{rows:,} 行、{weeks} 个有效周 → {s.DB}；.env 加 DATASET={s.DATASET} 后即可诊断")
