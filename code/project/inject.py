# inject.py —— M3 第 6-2 步：读异常场景表 → 每个场景生成一个注入后的视图 fact_S01 … fact_C05
# 运行：python code\project\inject.py（先跑 semantic.py 建好 fact；不调模型）→ 再跑 verify.py
# 防泄露：本文件只给评估用，Agent 代码不 import 它；输出的 data\manifest.csv Agent 也不读
import duckdb, re, sys, pandas as pd, semantic as s
TEST = "test" in sys.argv                                     # M7：python inject.py test → 读测试集场景表、写 manifest_test.csv
PLAN, MANI = ("测试集场景表.csv", "manifest_test.csv") if TEST else ("异常场景表.csv", "manifest.csv")
SPLIT = re.compile(r"\+(?!\))")                               # 多个取值用 + 连接；"高(75K+)" 里的 + 不拆（M7 修）

AMP = {"小": .05, "中": .15, "大": .20}                         # 目标幅度 = 对（范围内）GMV 的影响
KEY = {"删家庭": ["household_id"], "删购物篮": ["basket_id"], "删高价商品": ["basket_id"],
       "删商品行": ["basket_id", "product_id"], "删折扣商品行": ["basket_id", "product_id"],
       "删品类行": ["store_id", "product_id"], "金额置0": ["product_id"]}  # 删品类行 = 某些前置仓的某些商品售罄
AUX = {"删高价商品": "ROW_NUMBER() OVER (PARTITION BY basket_id ORDER BY sales_value / quantity DESC) rk, "
                    "COUNT(*) OVER (PARTITION BY basket_id) n",            # rk 单内价格排名，n 单内商品数
       "删购物篮": "DENSE_RANK() OVER (PARTITION BY household_id, wk ORDER BY basket_id) br"}  # 每户当周第几单

def conditions(r):
    """场景表一行 → (范围条件, 目标组条件, 删除单位, 额外条件)"""
    scope = "TRUE" if r.提问范围 == "全部" else "{} = '{}'".format(*r.提问范围.split("="))
    dim, val = r.维度, str(r.取值)
    if dim in ("拆解因子", "store_id", "全部"): g = "TRUE"     # 分层题删范围内所有人；S11 按门店分片；S06 全体
    elif dim == "campaign": g = f"household_id IN (SELECT household_id FROM campaigns WHERE campaign_id = '{val}')"
    elif dim == "dt": g = "dt BETWEEN DATE '{}' AND DATE '{}'".format(*val.split("~"))
    else: g = f"{dim} IN ({', '.join(repr(v) for v in SPLIT.split(val))})"   # S09：两个品类
    extra = {"删高价商品": " AND rk <= 2 AND n >= 3",           # 3 样以上订单里最贵的前 2 样：订单还在，只降客单价
             "删购物篮": " AND br > 1",                         # 每户当周保留第 1 单：人还在，只降频次（6-3 修正）
             "删折扣商品行": " AND retail_disc > 0"}.get(r.手法, "")
    key = KEY.get(r.手法) or (["store_id"] if dim == "store_id" else ["basket_id"])  # 数据缺失
    return scope, g, key, extra

if __name__ == "__main__":
    con = duckdb.connect(str(s.DB))
    s.build_fact(con)
    plan = pd.read_csv(s.ROOT / "docs" / PLAN, dtype=str, encoding="utf-8-sig")   # utf-8-sig：Excel 打开不乱码
    plan["组内比例"] = 0.0
    for i, r in enumerate(plan.itertuples()):
        if r.手法 == "无注入":                                  # 对照周也建视图，名字不泄露答案
            con.execute(f"CREATE OR REPLACE VIEW fact_{r.场景ID} AS SELECT * FROM fact"); continue
        src = f"(SELECT *, {AUX[r.手法]} FROM fact)" if r.手法 in AUX else "fact"
        drop = "EXCLUDE (rk, n) " if r.手法 == "删高价商品" else "EXCLUDE (br) " if r.手法 == "删购物篮" else ""
        scope, g, key, extra = conditions(r)
        wk = f"wk = DATE '{r.周}' AND {scope}"
        base, elig = con.execute(f"SELECT SUM(sales_value), SUM(sales_value) FILTER (WHERE {g}{extra}) FROM {src} WHERE {wk}").fetchone()
        a = AMP.get(r.目标幅度) or float(r.目标幅度.rstrip("%")) / 100   # 也可直接写 10%
        p, lo, hi, best = min(1.0, a * base / elig), 0.0, 1.0, (9, 0)  # 初始 p = 目标影响 ÷ 合格行占比
        for it in range(15):                                    # 校准：整户 / 整店整品删除有颗粒度 → 二分法找 p
            if it == 14: p = best[1]                            # 最后一轮：用误差最小的 p 重建视图
            hit = f"{wk} AND {g}{extra} AND hash(concat({', '.join(key)}, '|{r.场景ID}')) % 10000 < {int(p * 10000)}"
            con.execute(f"CREATE OR REPLACE VIEW fact_{r.场景ID} AS SELECT * {drop}FROM {src} WHERE NOT COALESCE({hit}, FALSE)")
            real = 1 - con.execute(f"SELECT SUM(sales_value) FROM fact_{r.场景ID} WHERE {wk}").fetchone()[0] / base
            best = min(best, (abs(real - a), p))
            if it == 14 or abs(real - a) < .005 or (p >= 1 and real < a): break   # 误差 < 0.5 个百分点就停
            lo, hi = (p, hi) if real < a else (lo, p)
            p = (lo + hi) / 2
        plan.loc[i, "组内比例"] = p
        if r.手法 == "金额置0":                                 # S12：原始表金额置 0 → is_sale 变 FALSE
            con.execute(f"""CREATE OR REPLACE VIEW tx_{r.场景ID} AS
                SELECT t.* REPLACE (IF(h.k, 0, t.sales_value) AS sales_value, t.is_sale AND h.k IS NULL AS is_sale)
                FROM transactions t LEFT JOIN (SELECT basket_id, product_id, TRUE k FROM fact WHERE {hit})
                h USING (basket_id, product_id)""")
        warn = "  ⚠ 用户侧组内比例 > 50%" if r.主因类型 == "用户侧" and p > .5 else ""
        print(f"{r.场景ID} {r.周} {r.手法:<6} 合格行占比 {elig / base:6.1%}  组内比例 {p:6.1%}  实测影响 {real:6.1%}{warn}")
    plan.to_csv(s.ROOT / "data" / MANI, index=False, encoding="utf-8-sig")   # verify.py 补实测列
    print(f"\n已生成 {len(plan)} 个 fact_ 视图 + 金额置0 题的 tx_ 视图 + data\\{MANI}（设计列 + 组内比例）")
