# scan_check.py —— v3-1（10-08）：只跑代码、不调大模型，检查 v3 前两步在 22 题上的效果
#   ① 数据质量由代码判（超线 + 非节假日 → 数据问题；节假日 → 正常波动）② scan 召回：真实主因在不在候选里、排第几
# 运行：cd D:\ai-agent-learning → python code\project\scan_check.py（约 1～3 分钟）
import warnings, pandas as pd, semantic as s, tools as T
warnings.filterwarnings("ignore")                                    # 少数小分组历史波动为 0，除法告警不影响结果
m = pd.read_csv(s.ROOT / "data" / "manifest.csv", dtype=str, encoding="utf-8-sig").fillna("")
rows = []
for r in m.itertuples():
    T.SRC, T.TX = f"fact_{r.场景ID}", "tx_S12" if r.场景ID == "S12" else "transactions"
    f = None if r.提问范围 == "全部" else dict(zip(["dim", "value"], r.提问范围.split("=", 1)))
    cd = T.check_data(r.周, f)
    if cd["日历"] != ["无"]: pre = "正常波动（节假日）"
    elif any(x["超线"] for x in cd["检查"]): pre = "数据问题"
    else: pre = "→ 交给模型复核"
    sc = T.scan(r.周, f, top=50) if pre.startswith("→") else {"候选": [], "候选数": 0}
    want = "活动触达" if r.维度 == "campaign" else {"活跃用户数": "户数"}.get(r.取值, r.取值)   # 真实主因：分组名 / 拆解因子
    hit = [i + 1 for i, c in enumerate(sc["候选"]) if c["分组"] in want.split("+")
           or (r.维度 in ("拆解因子", "全部") and c["维度"] == "全部" and c["指标"] in (want, "客单价" if r.维度 == "全部" else want))]
    top3 = "；".join(f"{c['维度']}={c['分组']}·{c['指标']} {c['异常分数']}/{c['中位数异常分数']}" for c in sc["候选"][:3])
    rows.append({"场景ID": r.场景ID, "真·主因": r.主因类型, "真·定位": f"{r.维度}={want}" if r.维度 else "—", "代码预判": pre,
                 "候选数": sc["候选数"], "真主因排名": hit[0] if hit else ("未召回" if r.主因类型 in ("用户侧", "商品侧") else "—"), "前3候选": top3})
out = pd.DataFrame(rows)
pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 250); pd.set_option("display.max_colwidth", 90)
print(out.to_string(index=False))
dq = out[out["真·主因"] == "数据问题"]
print(f"\n数据问题 代码判对 {(dq['代码预判'] == '数据问题').sum()}/{len(dq)}｜非数据题被误判为数据问题 {((out['代码预判'] == '数据问题') & (out['真·主因'] != '数据问题')).sum()} 题")
ab = out[out["真·主因"].isin(["用户侧", "商品侧"])]
print(f"异常题召回 {(ab['真主因排名'].apply(lambda x: isinstance(x, int))).sum()}/{len(ab)}｜排第 1 的 {(ab['真主因排名'] == 1).sum()} 题")
c = out[out["场景ID"].str.startswith("C")]
print(f"对照周：有候选（需要模型排除误报）{(c['候选数'] > 0).sum()}/{len(c)}｜平均候选数 {c['候选数'].mean():.1f}")
print("（v3-1 第一版：召回 7/14、排第 1 的 4 题；对照周有候选 4/5、平均 3.6 个）｜前3候选的两个数 = 环比分数/中位数分数")
