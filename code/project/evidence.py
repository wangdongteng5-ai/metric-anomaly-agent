# evidence.py —— M8（10-09）演示页的"数据依据"：只读查 fact + 画图（Altair）。只做展示，不参与判断，不 import 冻结文件
# 被 app.py 调用；所有查询都是 read_only，对任何已接入的数据集通用（只依赖数据契约里的标准列）
import json, re, duckdb, pandas as pd, altair as alt
UP, DOWN, MUTED = "#00897B", "#B42318", "#7A8C87"      # 上涨 / 下跌 / 辅助线（配色已过 dataviz 校验脚本）
MET = {"户数": "COUNT(DISTINCT household_id)", "频次": "COUNT(DISTINCT basket_id) * 1.0 / COUNT(DISTINCT household_id)",
       "客单价": "SUM(sales_value) / COUNT(DISTINCT basket_id)", "GMV": "SUM(sales_value)"}
CAMP = """household_id IN (SELECT household_id FROM campaigns JOIN campaign_descriptions USING (campaign_id)
          WHERE end_date BETWEEN DATE '{w}' - 14 AND DATE '{w}' - 1)"""   # 同 tools.CAMP：近 2 周结束的活动触达的家庭

def where(dim, value, week):
    """维度 + 取值 → SQL 条件（全部 / 活动 / 普通维度）"""
    if dim in ("", "全部"): return "TRUE"
    if dim == "camp": return CAMP.format(w=week)
    return f"{dim} = '{str(value).replace(chr(39), chr(39) * 2)}'"

def weekly(db, src, scope, week, metric="GMV", cause=None):
    """周序列：提问范围（+ 主因分组）内某指标每周的值；db 可以是库文件路径，也可以是已打开的连接"""
    d, v = (scope.split("=", 1) if scope != "全部" else ("全部", ""))
    extra = where(cause[0], cause[1], week) if cause else "TRUE"
    sql = f"SELECT wk, {MET[metric]} v FROM {src} WHERE {where(d, v, week)} AND {extra} GROUP BY 1 ORDER BY 1"
    if hasattr(db, "execute"): return db.execute(sql).df()     # 传入的是已打开的连接（live.py：要用其中的临时视图 fact_asof）
    with duckdb.connect(str(db), read_only=True) as c:
        return c.execute(sql).df()

def stats(df, week):
    """本周值、环比、vs 前 4 周中位数（与工具层同一口径）"""
    s = df.set_index("wk").v; t = pd.Timestamp(week); i = s.index.get_loc(t)
    med = s.iloc[max(0, i - 4):i].median()
    return s.iloc[i], s.iloc[i] / s.iloc[i - 1] - 1 if i else None, s.iloc[i] / med - 1 if i else None, med

def trend(df, week, fmt=",.0f", last=None, median=None, height=220):
    """周趋势折线：选中周用红点 + 竖线标出；可选前 4 周中位数虚线"""
    df = df[df.wk <= pd.Timestamp(week)].tail(last) if last else df   # 只看到选中周为止的最近 last 周
    base = alt.Chart(df).encode(x=alt.X("wk:T", title=None, axis=alt.Axis(format="%m-%d", grid=False, labelColor=MUTED)),
                                y=alt.Y("v:Q", title=None, scale=alt.Scale(zero=False), axis=alt.Axis(format=fmt, labelColor=MUTED, gridColor="#E3E9E7")))
    tip = [alt.Tooltip("wk:T", title="周", format="%Y-%m-%d"), alt.Tooltip("v:Q", title="值", format=fmt)]
    layers = [base.mark_line(color=UP, strokeWidth=2), base.mark_point(size=60, opacity=0).encode(tooltip=tip)]
    sel = df[df.wk == pd.Timestamp(week)]
    layers += [alt.Chart(sel).mark_rule(color=DOWN, strokeDash=[2, 3]).encode(x="wk:T"),
               alt.Chart(sel).mark_point(color=DOWN, filled=True, size=90).encode(x="wk:T", y="v:Q", tooltip=tip)]
    if median is not None:
        layers.append(alt.Chart(pd.DataFrame({"m": [median]})).mark_rule(color=MUTED, strokeDash=[5, 4]).encode(y="m:Q"))
    return alt.layer(*layers).properties(height=height)

def bars(df, label, value, fmt=",.0f", height=150):
    """横向条形图：负数红、正数绿；数值并进左侧标签（"户数  -5,986"），不和条形抢位置"""
    df = df.assign(色=df[value].map(lambda v: DOWN if v < 0 else UP),
                   标签=df[label].astype(str) + "  " + df[value].map(lambda v: format(v, fmt.replace("d", ",.0f"))))
    return alt.Chart(df).mark_bar(cornerRadiusEnd=4, height=18).encode(
        y=alt.Y("标签:N", title=None, sort=None, axis=alt.Axis(labelColor="#1F2D2B", labelFontSize=13, ticks=False, domain=False, labelLimit=260)),
        x=alt.X(f"{value}:Q", title=None, axis=alt.Axis(grid=True, gridColor="#E3E9E7", labels=False, ticks=False, domain=False)),
        color=alt.Color("色:N", scale=None), tooltip=[alt.Tooltip(f"{label}:N"), alt.Tooltip(f"{value}:Q", format=fmt)]).properties(height=height)

def cause_of(text):
    """'income_band=中(35-74K) 的 户数' → ('income_band', '中(35-74K)', '户数')；代码直接判定的结论返回 None"""
    m = re.match(r"(\w+)=(.+) 的 (户数|频次|客单价|GMV)$", str(text).strip())
    return m.groups() if m else None

def material(card):
    """方案卡末尾的 JSON 材料 → dict（名单 / 实验 / 策略手册）"""
    m = re.search(r"```json\n(.*?)\n```", card or "", re.S)
    return json.loads(m.group(1)) if m else {}
