# baseline_test.py —— M7 第 4 步（10-08）：用冻结的规则基线跑测试集 → data\baseline_test.csv
# 算法 = baseline.diagnose（冻结文件，一行不改）；这里只换输入（manifest_test.csv）和金额置 0 题的交易表（tx_场景ID）
# 运行：python code\project\baseline_test.py（先跑 inject.py test；不调模型，约 1～3 分钟）
import sys, pandas as pd, semantic as s
from freeze import check
if bad := check(): sys.exit(f"❌ 系统冻结后被改过：{bad}，不能跑测试集")
import baseline as b
from inject import conditions, SPLIT

MANI = sys.argv[1] if len(sys.argv) > 1 else "manifest_test.csv"     # 自测时可传 manifest.csv，应复现 baseline_result.csv
m = pd.read_csv(s.ROOT / "data" / MANI, dtype=str, encoding="utf-8-sig").fillna("")
res = []
for r in m.itertuples():
    scope = conditions(r)[0] if r.手法 != "无注入" else "TRUE"
    print(f"诊断 {r.场景ID} …", flush=True)
    b.con.execute(f"CREATE OR REPLACE TEMP TABLE v AS SELECT * FROM fact_{r.场景ID} WHERE wk <= DATE '{r.周}'")
    typ, loc, fac, act = b.diagnose("v", r.周, scope, f"tx_{r.场景ID}" if r.手法 == "金额置0" else "transactions")
    truth = {"campaign": "活动触达"}.get(r.维度, {"活跃用户数": "户数"}.get(r.取值, r.取值))
    if r.维度 == "拆解因子": loc = fac                                  # 分层题：定位 = 拆解因子
    res.append({"场景ID": r.场景ID, "题型": r.题型, "真·主因": r.主因类型, "判·主因": typ, "真·定位": truth, "判·定位": loc,
                "真·动作": r.正确动作, "判·动作": act, "主因对": typ == r.主因类型, "动作对": act == r.正确动作,
                "定位对": (loc in SPLIT.split(truth)) if r.维度 not in ("", "dt", "store_id", "全部") else None})
out = pd.DataFrame(res)
name = "baseline_test.csv" if MANI == "manifest_test.csv" else "baseline_selfcheck.csv"
out.to_csv(s.ROOT / "data" / name, index=False, encoding="utf-8-sig")
pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 220)
print(out.to_string(index=False))
for k in ["主因对", "定位对", "动作对"]:
    x = out[k].dropna().astype(bool); print(f"{k}：{x.sum()}/{len(x)} = {x.mean():.0%}")
c = out[out.场景ID.str.startswith("C")]; print(f"对照周误报：{(c.判·动作 != '不行动').sum()}/{len(c)}")
