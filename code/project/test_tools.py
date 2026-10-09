# test_tools.py —— M4 4-5：工具层回归测试（只测工具算得对不对；Agent 判断得好不好留给 M6）
# 运行：cd D:\ai-agent-learning → python code\project\test_tools.py；最后一行打印"全部通过"或失败清单
# 改了 tools.py 之后都要跑一遍；数字来源：M3 SQL 抽查 + M4 4-1～4-4 实测（10-07）
import tools as T

ok = lambda a, b, tol=.01: abs(a - b) < tol                  # 小数比较留一点误差（四舍五入）
fails = []
def use(src, tx="transactions"): T.SRC, T.TX = src, tx       # 切换注入视图：和 M6 评估时同一个办法
def check(name, cond):
    print(("✅ " if cond else "❌ ") + name)
    if not cond: fails.append(name)

MEAT = {"dim": "department", "value": "MEAT"}
use("fact_S16"); q = T.query_metric("gmv", "2017-10-23", MEAT)                       # 1 精确值
check("1 S16 MEAT 本周 = 5,119.69", ok(q["本周"], 5119.69))
check("1 S16 MEAT 环比 +4.5%、vs前4周中位数 -8.3%", ok(q["环比"], .045, .001) and ok(q["vs前4周中位数"], -.083, .001))

for src, wk, f in [("fact_S03", "2017-04-03", None), ("fact_C01", "2017-08-07", None),        # 2 对账
                   ("fact_S17", "2017-02-20", {"dim": "income_band", "value": "高(75K+)"})]:
    use(src); d = T.decompose(wk, f)
    check(f"2 {src} 三因子贡献相加 = GMV变化额 {d['GMV变化额']:,.2f}", ok(sum(x["贡献额"] for x in d["拆解"]), d["GMV变化额"], .05))

def drill(src, wk, dim, f=None):                                                       # 5 对账（每次下钻都查）
    use(src); d = T.drill_down(wk, dim, f); a = d["客单价"]
    tot = sum(x["GMV贡献额"] for x in d["分组"]) + d["其他分组GMV贡献合计"]
    check(f"5 {src} 各组贡献 = 变化额，结构 + 比率 = 客单价变化",
          ok(tot, d["GMV变化额"], .05) and ok(a["结构合计"] + a["比率合计"], a["变化"], .02))
    return d["分组"][0]                                                                 # 排第 1 的组
top = drill("fact_S03", "2017-04-03", "main_store_group")                                # 3 排序 + 精确值
check("3 S03 下钻第 1 = 腰部，订单本周 1,832", top["分组"] == "腰部" and top["订单本周"] == 1832)
top = drill("fact_S16", "2017-10-23", "product_category", MEAT)                          # 4 排序 + 精确值
check("4 S16 MEAT 内第 1 = BEEF，GMV本周 2,434.53", top["分组"] == "BEEF" and ok(top["GMV本周"], 2434.53))
drill("fact_C04", "2017-10-16", "main_store_group")

for src, tx, wk, want in [("fact_S10", "transactions", "2017-08-21", "连续大跌天数"),      # 6 每个场景只有对应一项超线
                          ("fact_S11", "transactions", "2017-11-13", "门店变0占上周GMV"),
                          ("fact_S12", "tx_S12", "2017-09-18", "无效行占比"), ("fact_C04", "transactions", "2017-10-16", None)]:
    use(src, tx); hit = [x["项目"] for x in T.check_data(wk)["检查"] if x["超线"]]
    check(f"6 {src} 超线项 = {hit or '无'}", hit == ([want] if want else []))
use("fact")

for name, fn in [("非周一 2017-06-06", lambda: T.query_metric("gmv", "2017-06-06")),            # 7 拦截
                 ("指标 dau", lambda: T.query_metric("dau", "2017-06-05")), ("维度 city", lambda: T.drill_down("2017-04-03", "city"))]:
    try: fn(); check(f"7 拦截 {name}", False)
    except ValueError: check(f"7 拦截 {name}", True)

print("\n8 实验（不断言）：腰部组内 decompose，各因子 (环比, 异常分数)；分数 < -1 才算超线")
for src, wk in [("fact_S03", "2017-04-03"), ("fact_C04", "2017-10-16")]:
    use(src); d = T.decompose(wk, {"dim": "main_store_group", "value": "腰部"})
    print(" ", src, {x["因子"]: (x["环比"], x["异常分数"]) for x in d["拆解"]})
print("\n全部通过" if not fails else f"\n❌ 失败 {len(fails)} 条：{fails}")
