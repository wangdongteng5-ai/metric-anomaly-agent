# verify.py —— M3 第 6-3 步：实测每个注入视图 → 补进 data\manifest.csv，并逐条检查"能不能被诊断出来"
# 运行：python code\project\verify.py（先跑 inject.py；只读查询，不调模型）
import duckdb, pandas as pd, semantic as s
from inject import conditions, SPLIT, TEST, MANI   # M7：verify.py test → 验证测试集
pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 250)

con = duckdb.connect(str(s.DB), read_only=True)
q = lambda sql: con.execute(sql).fetchone()
EXPECT = {"删家庭": "户数", "删购物篮": "频次", "删商品行": "客单价", "删高价商品": "客单价"}  # 手法 → 应该变的拆解因子
m = pd.read_csv(s.ROOT / "data" / MANI, dtype=str, encoding="utf-8-sig").fillna("")   # 对照周的空格子 → ""
m = m.loc[:, :"组内比例"].astype({"组内比例": float})            # 只取设计列，重复运行不会叠加实测列

def factors(v, w, cond):                                        # GMV = 户数 × 频次 × 客单价
    g, hh, od = q(f"SELECT SUM(sales_value), COUNT(DISTINCT household_id), COUNT(DISTINCT basket_id) FROM {v} WHERE wk = DATE '{w}' AND {cond}")
    nan = float("nan")                                          # 整组被删光（S12）时避免除以 0
    return g or 0, {"户数": hh, "频次": od / hh if hh else nan, "客单价": g / od if od else nan}

def top1(v, w, scope, dim):                                     # 下钻：本周 vs 上周，哪个取值的 GMV 跌得最多（绝对额）
    return q(f"""SELECT {dim} FROM {v} WHERE wk IN (DATE '{w}', DATE '{w}' - 7) AND {scope} AND {dim} IS NOT NULL
                 GROUP BY 1 ORDER BY SUM(IF(wk = DATE '{w}', sales_value, -sales_value)) LIMIT 1""")[0]

rows = []
for r in m.itertuples():
    v, w = f"fact_{r.场景ID}", r.周
    scope, g, _, _ = conditions(r) if r.手法 != "无注入" else ("TRUE", "TRUE", 0, 0)
    now, last, raw, raw0 = (q(f"SELECT SUM(sales_value) FROM {t} WHERE wk = DATE '{w}' - {d} AND {scope}")[0]
                            for t, d in [(v, 0), (v, 7), ("fact", 0), ("fact", 7)])
    base4 = q(f"SELECT MEDIAN(g) FROM (SELECT wk, SUM(sales_value) g FROM {v} WHERE wk BETWEEN DATE '{w}' - 28 AND DATE '{w}' - 7 AND {scope} GROUP BY 1)")[0]
    g0, f0 = factors("fact", w, f"{scope} AND {g}"); g1, f1 = factors(v, w, f"{scope} AND {g}")
    chg = {k: f1[k] / f0[k] - 1 for k in f0}
    main = min(chg, key=lambda k: chg[k] if chg[k] == chg[k] else 0) if r.手法 != "无注入" else "—"
    dim = {"campaign": f"({g})::VARCHAR", "dt": "ISODOW(dt)::VARCHAR"}.get(r.维度, r.维度)
    want = (["true"] if r.维度 == "campaign" else SPLIT.split(r.取值) if r.维度 != "dt"     # dt：缺失日期 → 星期几（M7：原写死周二～周四）
            else [str(x.isoweekday()) for x in pd.date_range(*r.取值.split("~"))])
    hit = (top1(v, w, scope, dim) in want) if r.维度 in s.SEM["dimensions"] or r.维度 in ("campaign", "dt") else None
    rows.append({"环比_注入后": now / last - 1, "vs前4周中位数": now / base4 - 1, "环比_原始": raw / raw0 - 1,
                 "注入影响": now / raw - 1, "组内跌幅": g1 / g0 - 1, **{f"Δ{k}": x for k, x in chg.items()},
                 "主拆解因子": main, "因子对": EXPECT.get(r.手法, main) == main, "下钻Top1对": hit})
m = pd.concat([m, pd.DataFrame(rows)], axis=1)
m.to_csv(s.ROOT / "data" / MANI, index=False, encoding="utf-8-sig")
print(m[["场景ID", "题型", "手法", "取值", "组内比例", "环比_原始", "环比_注入后", "vs前4周中位数", "注入影响", "组内跌幅",
         "Δ户数", "Δ频次", "Δ客单价", "主拆解因子", "因子对", "下钻Top1对"]].round(3).to_string(index=False))

print("\n对照周：各主力门店组的环比（均匀 = 差距小）")
for r in m[m.手法 == "无注入"].itertuples():
    d = con.execute(f"""SELECT main_store_group, SUM(IF(wk = DATE '{r.周}', sales_value, 0)) / SUM(IF(wk = DATE '{r.周}' - 7, sales_value, 0)) - 1 c
                        FROM fact WHERE wk IN (DATE '{r.周}', DATE '{r.周}' - 7) GROUP BY 1""").df()
    print(r.场景ID, r.周, dict(zip(d.main_store_group, d.c.round(3))))
W = dict(zip(m.场景ID, m.周))                                    # 场景 → 周（换周后不用改这里）
if not TEST: print("\nS15 牛肉占 MEAT：", round(q(f"SELECT SUM(sales_value) FILTER (WHERE product_category = 'BEEF') / SUM(sales_value) FROM fact WHERE wk = DATE '{W['S15']}' AND department = 'MEAT'")[0], 3))   # 开发集专用
for r in m[m.手法 == "金额置0"].itertuples():                        # M7：原写死 S12
    print(f"{r.场景ID} 无效行占比 原始 / 注入后：", [round(q(f"SELECT 100 * AVG(IF(is_sale, 0, 1)) FROM {t} WHERE DATE_TRUNC('week', dt) = DATE '{r.周}'")[0], 2) for t in ("transactions", f"tx_{r.场景ID}")])
