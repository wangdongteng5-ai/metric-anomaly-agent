# tools.py —— M4 诊断工具：只算"证据"，不下结论（判断留给 M5 的 Agent）
# 4-1（10-07）query_metric：某指标某周的值 + 环比 + vs 前 4 周中位数 + 异常分数 + 日历标记
# 4-2（10-07）decompose：GMV = 户数 × 频次 × 客单价，对数拆分出各因子贡献额；抽出 _series / _evidence 两个函数共用
# 4-3（10-07）drill_down：按维度下钻，各分组 GMV 贡献额 + 客单价拆成结构贡献 / 比率贡献；自测改为下钻 3 个场景
# 4-4（10-07）check_data：数据质量 3 项检查（从 baseline.py 第 35～42 行搬，阈值 M3 冻结）；自测改为 5 个周
# 5-3（10-08）_scope 校验分组取值是否存在：模型编了「食品」「头部前20家」，原来只报 KeyError: Timestamp，模型看不懂、反复重试
# v3-1（10-08）scan 加活动维度 camp + 第二基准（vs 前 4 周中位数分数）
# v3-1（10-08）scan：召回 = 所有维度 × 分组 × 指标扫一遍，返回分数 < -1 的候选（逻辑同 baseline.py scores()）；日历抽成 _calendar 共用
# 防作弊：不读 manifest、不 import inject；维度和取值全部来自参数，代码里不写任何具体分组
# 自测：cd D:\ai-agent-learning → python code\project\tools.py
import datetime as dt, math, duckdb, pandas as pd, semantic as s

con = duckdb.connect(str(s.DB), read_only=True)
SRC = "fact"                       # 评估时由 eval 换成 fact_S03 等；不写进工具说明书，模型看不到也选不了
TX = "transactions"                # 原始交易表（含无效行）；评估 S12 时换成 tx_S12，同上
T, WEEK = s.SEM["time"], pd.Timedelta(days=7)
HOLI = {h["wk"]: h["name"] for h in T["holidays"]}
has_1st = lambda d: (d + pd.Timedelta(days=6)).day <= 7      # 这一周（周一～周日）含每月 1 号
r = lambda v, n=4: round(float(v), n)                        # 转成普通小数，模型读 JSON 更干净

def _scope(week, filter):
    """校验周 + 分层提问：{"dim": "department", "value": "MEAT"} → SQL 条件；维度必须是语义层里有的"""
    if dt.date.fromisoformat(week).weekday() != 0 or not T["valid_from"] < week <= T["valid_to"]:
        raise ValueError(f"week 必须是 {T['valid_from']} 之后、{T['valid_to']} 及之前的周一，收到 {week}")
    if not filter: return "TRUE", "全部"
    d, v = filter["dim"], str(filter["value"])
    if not (s.SEM["dimensions"].get(d) or {}).get("sql"):
        raise ValueError(f"不支持的维度：{d}，可选：{[k for k, x in s.SEM['dimensions'].items() if x['sql']]}")
    if v not in (vals := _values(d)):                            # 5-3：拦住编出来的分组名，并告诉模型怎么改
        raise ValueError(f"{d} 没有取值「{v}」，取值必须照抄 drill_down 返回的「分组」；可选（共 {len(vals)} 个）：{vals[:30]}")
    return f"{d} = '{v.replace(chr(39), chr(39) * 2)}'", f"{d}={v}"

_VALS = {}
def _values(d):
    """维度的全部取值：查 fact 一次后缓存（注入表的取值范围和 fact 相同）"""
    if d not in _VALS:
        _VALS[d] = [str(x[0]) for x in con.execute(f"SELECT DISTINCT {d} FROM fact WHERE {d} IS NOT NULL ORDER BY 1").fetchall()]
    return _VALS[d]

def _series(cols, week, cond):
    """按周汇总（截至 week），缺的周补成空，不跳着比"""
    return con.execute(f"SELECT wk, {cols} FROM {SRC} WHERE wk <= DATE '{week}' AND {cond} GROUP BY 1 ORDER BY 1"
                       ).df().set_index("wk").asfreq("7D")

def _evidence(x, t, n=2):
    """一条周序列 → 本周 / 上周 / 环比 / vs 前 4 周中位数 / 异常分数（4-1 的同一套证据）"""
    c = x / x.shift(1) - 1                                       # 每周 vs 上一周
    if pd.isna(c.get(t)): raise ValueError(f"{t.date()} 或上一周没有数据")
    hist = c.drop(t).abs().dropna()                              # 历史环比幅度（不含本周，避免自己给自己打分）
    q90, med4 = hist.quantile(.9), x[t - 4 * WEEK: t - WEEK].median()
    return {"本周": r(x[t], n), "上周": r(x[t - WEEK], n), "环比": r(c[t]), "前4周中位数": r(med4, n),
            "vs前4周中位数": r(x[t] / med4 - 1), "历史环比90分位": r(q90),
            "异常分数": r(c[t] / q90, 2), "历史周数": len(hist)}  # 异常分数 < -1：跌幅超出自身 9 成周

def query_metric(metric, week, filter=None):
    """指标在第 week 周的值，以及两个基准：环比（vs 上周）、vs 前 4 周中位数"""
    m = s.SEM["metrics"].get(metric)
    if not m or not m["sql"]:
        raise ValueError(f"不支持的指标：{metric}，可选：{[k for k, x in s.SEM['metrics'].items() if x['sql']]}")
    cond, name = _scope(week, filter)
    t = pd.Timestamp(week)
    return {"指标": m["name"], "单位": m["unit"], "口径": m["desc"], "范围": name, "周": week,
            **_evidence(_series(f"{m['sql']} v", week, cond).v, t), "日历": _calendar(week)}

def _calendar(week):
    """节假日 + 月初标记（月初所在周常 +9%，下一周常回落 -9%～-11%，见 M3）"""
    t = pd.Timestamp(week)
    cal = ([HOLI[week]] if week in HOLI else []) + ["本周含月初"] * has_1st(t) + ["上周含月初"] * has_1st(t - WEEK)
    return cal or ["无"]

def decompose(week, filter=None):
    """GMV = 户数 × 频次 × 客单价：各因子贡献额（对数拆分，三者相加 = GMV 变化额）+ 各因子自己的证据"""
    cond, name = _scope(week, filter)
    d = _series("SUM(sales_value) g, COUNT(DISTINCT household_id) h, COUNT(DISTINCT basket_id) o", week, cond)
    t, l = pd.Timestamp(week), pd.Timestamp(week) - WEEK
    f = {"户数": d.h, "频次": d.o / d.h, "客单价": d.g / d.o}
    dg, lg = d.g[t] - d.g[l], math.log(d.g[t] / d.g[l])
    w = dg / lg if lg else d.g[l]                                # 对数平均：把"相乘"变成"相加"的权重
    rows = [{"因子": k, "贡献额": r(w * math.log(x[t] / x[l]), 2), **_evidence(x, t)} for k, x in f.items()]
    return {"范围": name, "周": week, "GMV": _evidence(d.g, t, 2), "GMV变化额": r(dg, 2),
            "拆解": rows, "说明": "贡献额单位为美元，三个因子相加 = GMV变化额；看哪个因子贡献最负、且自身证据异常"}

def drill_down(week, dim, filter=None, top=5):
    """按维度下钻：各分组 GMV 贡献额（相加 = 总变化）+ 客单价变化拆成 结构贡献 / 比率贡献"""
    cond, name = _scope(week, filter)                            # 分层提问：在 filter 范围内下钻
    if not (s.SEM["dimensions"].get(dim) or {}).get("sql"):
        raise ValueError(f"不支持的维度：{dim}，可选：{[k for k, x in s.SEM['dimensions'].items() if x['sql']]}")
    t, l = pd.Timestamp(week), pd.Timestamp(week) - WEEK
    d = con.execute(f"""SELECT {dim} grp, wk, SUM(sales_value) g, COUNT(DISTINCT basket_id) o FROM {SRC}
        WHERE wk IN (DATE '{l.date()}', DATE '{week}') AND {cond} AND {dim} IS NOT NULL GROUP BY 1, 2"""
                    ).df().pivot(index="grp", columns="wk").fillna(0)
    g0, g1, o0, o1 = d["g"][l], d["g"][t], d["o"][l], d["o"][t]
    s0, s1 = o0 / o0.sum(), o1 / o1.sum()                        # 订单占比 = 结构
    a0, a1 = g0 / o0, g1 / o1                                    # 各组客单价 = 比率
    a0, a1 = a0.fillna(a1), a1.fillna(a0)                        # 某组某周没单：当成只有结构变化
    A0, A1 = g0.sum() / o0.sum(), g1.sum() / o1.sum()            # 范围内整体客单价（上周 / 本周）
    tab = pd.DataFrame({"GMV本周": g1, "GMV贡献额": g1 - g0, "订单本周": o1, "订单占比变化": s1 - s0,
                        "客单价上周": a0, "客单价本周": a1,
                        "结构贡献": (s1 - s0) * (a0 - A0),        # 占比变了 × 这组比平均贵多少
                        "比率贡献": s1 * (a1 - a0)}               # 这组自己的客单价变了 × 本周占比
                       ).sort_values("GMV贡献额")                 # 贡献最负的排最前
    rows = []
    for k, x in tab.head(top).iterrows():                        # 只给前 top 组附自身证据，其余合并
        v = str(k).replace("'", "''")                            # 品类名里可能有单引号
        try: ev = _evidence(_series("SUM(sales_value) v", week, f"{cond} AND {dim} = '{v}'").v, t)
        except ValueError: ev = None                             # 该组上周没数据，算不了环比
        rows.append({"分组": k, **{c: r(y, 4 if c == "订单占比变化" else 2) for c, y in x.items()}, "GMV证据": ev})
    return {"范围": name, "维度": dim, "周": week, "分组数": len(tab),
            "GMV变化额": r(tab["GMV贡献额"].sum(), 2), "其他分组GMV贡献合计": r(tab["GMV贡献额"].iloc[top:].sum(), 2),
            "客单价": {"上周": r(A0, 2), "本周": r(A1, 2), "变化": r(A1 - A0, 2),
                     "结构合计": r(tab["结构贡献"].sum(), 2), "比率合计": r(tab["比率贡献"].sum(), 2)},
            "分组": rows, "说明": "GMV贡献额相加 = GMV变化额；客单价变化 = 结构合计 + 比率合计。"
                                  "结构为主 = 各组自己没变、只是订单占比变了（辛普森悖论）"}

LIM = s.SEM["quality"]             # 数据质量 3 个阈值：M3 在 CJ 上校准，M8（10-09）移进 metrics.yaml，换数据集要重新校准
DAY = dict(zip(range(1, 8), "一二三四五六日"))

def check_data(week, filter=None):
    """数据质量 3 项检查：只报数值 + 阈值 + 是否超线，不下"数据问题"结论（留给 M5 的 Agent）"""
    cond, name = _scope(week, filter)                            # v4（h3）：3 项检查都看全平台，filter 只用于校验参数和显示范围
    bad = con.execute(f"SELECT AVG(IF(is_sale, 0, 1)) FROM {TX} WHERE DATE_TRUNC('week', dt) = DATE '{week}'").fetchone()[0]
    day = con.execute(f"""SELECT ISODOW(dt) d, SUM(IF(wk = DATE '{week}', sales_value, 0))
        / NULLIF(SUM(IF(wk = DATE '{week}' - 7, sales_value, 0)), 0) - 1 c
        FROM {SRC} WHERE wk IN (DATE '{week}', DATE '{week}' - 7) GROUP BY 1 ORDER BY 1""").df()   # v4：去掉 AND {cond}（S34：小范围按天噪声大，误判数据问题）
    st, n0 = con.execute(f"""SELECT SUM(IF(n = 0, l, 0)) / SUM(l), COUNT(*) FILTER (WHERE n = 0) FROM (
        SELECT store_id, SUM(IF(wk = DATE '{week}', 1, 0)) n, SUM(IF(wk = DATE '{week}' - 7, sales_value, 0)) l
        FROM {SRC} WHERE wk IN (DATE '{week}', DATE '{week}' - 7) GROUP BY 1)""").fetchone()
    run = best = 0
    for c in day.c:                                              # 按天环比 < -30% 的最长连续天数
        run = run + 1 if c < -.3 else 0
        best = max(best, run)
    val = {"无效行占比": bad, "连续大跌天数": best, "门店变0占上周GMV": st}
    note = {"无效行占比": "全平台，正常约 0.8%；金额被置 0 的行会从 fact 里消失，只能在原始表看到",
            "连续大跌天数": "全平台按天和上周同一天比（数据问题通常是全平台的）", "门店变0占上周GMV": f"全平台，本周 0 交易的门店 {n0} 家"}
    return {"范围": name, "周": week, "日历": [HOLI[week]] if week in HOLI else ["无"],
            "检查": [{"项目": k, "值": r(v), "阈值": LIM[k],
                     "超线": bool(v >= LIM[k] if k == "连续大跌天数" else v > LIM[k]), "说明": note[k]} for k, v in val.items()],
            "按天环比": {f"周{DAY[d]}": r(c) for d, c in zip(day.d, day.c)},
            "说明": "超线只说明数据可能有问题；节假日周按天大跌可能是自然的（如感恩节），要结合日历判断"}

SCAN_USER = [d for d in ("main_store_group", "age_band", "income_band") if s.SEM["dimensions"][d]["sql"]] + ["camp"]   # 用户维度（同 baseline）
# M8（10-09）：metrics.yaml 里 sql 为 null 的维度不扫（新数据集没有画像表时）；CJ 三个都有，结果不变
PRODUCT = ("department", "product_category")
CAMP = """IF(household_id IN (SELECT household_id FROM campaigns JOIN campaign_descriptions USING (campaign_id)
          WHERE end_date BETWEEN DATE '{w}' - 14 AND DATE '{w}' - 1), '活动触达', NULL)"""   # 近 2 周结束的活动触达的家庭（同 baseline）

def _med_score(x, t):
    """第二基准的异常分数：本周 vs 前 4 周中位数的偏离 ÷ 历史偏离幅度的 90 分位（算法同 _evidence，只换基准）"""
    dev = x / x.shift(1).rolling(4).median() - 1
    if pd.isna(dev.get(t)): return None
    return r(dev[t] / dev.drop(t).abs().dropna().quantile(.9), 2)

def scan(week, filter=None, top=8):
    """召回：用户维度看 户数/频次/客单价，商品维度看 GMV，"全部"看提问范围整体；
    两个基准（环比 / vs 前 4 周中位数）任一分数 < -1 就进候选，最负在前"""
    cond, name = _scope(week, filter)
    dims = SCAN_USER + ["department"] + (["product_category"] if filter and filter["dim"] == "department" else [])
    t, out = pd.Timestamp(week), []
    for dim in dims + ["全部"]:
        col = {"全部": "'全部'", "camp": CAMP.format(w=week)}.get(dim, dim)
        d = con.execute(f"""SELECT wk, {col} grp, SUM(sales_value) g, COUNT(DISTINCT household_id) h, COUNT(DISTINCT basket_id) o
            FROM {SRC} WHERE wk <= DATE '{week}' AND {cond} AND {col} IS NOT NULL GROUP BY 1, 2""").df()
        for grp, x in d.groupby("grp"):
            x = x.set_index("wk").sort_index().asfreq("7D")
            mets = {"GMV": x.g} if dim in PRODUCT else {"户数": x.h, "频次": x.o / x.h, "客单价": x.g / x.o}
            for k, v in mets.items():
                try: ev, ms = _evidence(v, t), _med_score(v, t)
                except (ValueError, KeyError): continue                # 该组本周或上周没数据
                hit = [n for n, sc in [("环比", ev["异常分数"]), ("vs中位数", ms)] if sc is not None and sc < -1]
                if hit:
                    out.append({"维度": dim, "分组": str(grp), "指标": k, "触发": "+".join(hit), "异常分数": ev["异常分数"],
                                "中位数异常分数": ms, "环比": ev["环比"], "vs前4周中位数": ev["vs前4周中位数"],
                                "本周": ev["本周"], "上周": ev["上周"]})
    out.sort(key=lambda c: min(c["异常分数"], c["中位数异常分数"] if c["中位数异常分数"] is not None else 0))
    return {"范围": name, "周": week, "日历": _calendar(week), "候选数": len(out), "候选": out[:top],
            "说明": "候选 = 任一基准分数 < -1 的 (维度, 分组, 指标)，只是召回，可能含误报（多重比较）；"
                    "全部 = 提问范围整体；camp = 近 2 周结束的营销活动触达的家庭"}

if __name__ == "__main__":
    pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 250)
    for SRC, TX, wk in [("fact_S10", "transactions", "2017-08-21"), ("fact_S11", "transactions", "2017-11-13"),
                        ("fact_S12", "tx_S12", "2017-09-18"), ("fact", "transactions", "2017-11-20"),
                        ("fact_C04", "transactions", "2017-10-16")]:
        res = check_data(wk)
        print(f"\n{SRC} {wk}｜日历 {res['日历']}｜按天环比 {res['按天环比']}")
        print(pd.DataFrame(res["检查"]).to_string(index=False))
