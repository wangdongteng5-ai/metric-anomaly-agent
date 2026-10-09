# eval.py —— M5 5-5（10-08；v3 起改为传 周 + 提问范围）：开发集 22 题批量跑 Agent，按 baseline.py 同一套口径打分，并与规则基线对比
# 运行：python code\project\eval.py（全部，约 15～25 分钟；中断后再运行会跳过已跑完的题）｜加 --new 从头重跑｜加 S03 C04 只（重）跑这几题｜加 r2 存成第 2 次运行
# 输出：data\eval_<版本>.csv（每题一行，跑一题存一次）+ data\eval_<版本>_trace.jsonl（完整调用记录，给 badcase 分析用）
import json, sys, time, pandas as pd, semantic as s
import agent, checks
from audit import code_review
from prompt import VERSION
TEST = "test" in sys.argv                                              # M7：python eval.py test → 测试集（只跑一次）
REP = next((x for x in sys.argv[1:] if x.startswith("r")), "")         # 重复运行编号，如 r2 → 结果存成另一个文件
TAG = ("test_" if TEST else "") + f"prompt{VERSION}_{checks.VERSION}" + (f"_{REP}" if REP else "")   # 例：promptv3_h2、promptv3_h2_r2
OUT, TRACE = s.ROOT / "data" / f"eval_{TAG}.csv", s.ROOT / "data" / f"eval_{TAG}_trace.jsonl"
m = pd.read_csv(s.ROOT / "data" / ("manifest_test.csv" if TEST else "manifest.csv"), dtype=str, encoding="utf-8-sig").fillna("")
new, ids = "--new" in sys.argv, [x for x in sys.argv[1:] if x not in ("--new", "test") and not x.startswith("r")]
if TEST:                                                                # 测试集纪律由代码强制，不靠自觉
    from freeze import check
    if bad := check(): sys.exit(f"❌ 系统冻结后被改过：{bad}，不能跑测试集")
    if new: sys.exit("❌ 测试集只跑一次：不允许 --new 从头重跑")
if new: OUT.unlink(missing_ok=True); TRACE.unlink(missing_ok=True)
rows = pd.read_csv(OUT, encoding="utf-8-sig").to_dict("records") if OUT.exists() else []   # 断点续跑
failed = lambda x: str(x.get("报错", "")) not in ("", "nan")             # 运行报错（断网 / 限流），不是答错
rows = [x for x in rows if x["场景ID"] not in ids or (TEST and not failed(x))]   # 指定的题重跑；测试集只许重跑运行报错的题
for r in m.itertuples():
    if (ids and r.场景ID not in ids) or r.场景ID in {x["场景ID"] for x in rows}: continue
    t0, err = time.time(), ""
    try: res = agent.run(r.周, r.提问范围, f"fact_{r.场景ID}", f"tx_{r.场景ID}" if r.手法 == "金额置0" else "transactions")
    except Exception as e:                                              # 一题失败不影响其他题
        err = str(e)
        res = {"回答": None, "trace": [], "拦截": 0, "丢弃": 0, "退回": 0, "轮数": 0, "校验": [f"运行失败：{e}"]}; print(f"  ⚠️ 运行失败：{e}")
    a, cause = res["回答"] or {}, str((res["回答"] or {}).get("主因", ""))
    truth = {"campaign": "活动触达"}.get(r.维度, {"活跃用户数": "户数"}.get(r.取值, r.取值))   # 与 baseline.py 同口径
    rows.append({"场景ID": r.场景ID, "真·主因": r.主因类型, "判·主因": a.get("结论类型"), "真·定位": truth, "判·定位": cause,
                 "真·动作": r.正确动作, "判·动作": a.get("动作"), "主因对": a.get("结论类型") == r.主因类型,
                 "定位对": any(t in cause for t in truth.split("+")) if r.维度 not in ("", "dt", "store_id", "全部") else None,
                 "动作对": a.get("动作") == r.正确动作, "代码版动作": (cv := code_review(res["trace"]) or a.get("动作")),
                 "代码版对": cv == r.正确动作, "校验通过": res["校验"] == [],
                 "判定": a.get("判定", "模型"), "候选数": next((json.loads(t["结果"])["候选数"] for t in res["trace"] if t["工具"] == "候选清单"), 0),
                 "模型调用": sum(t["轮"] > 0 for t in res["trace"]), **{k: res[k] for k in ("拦截", "丢弃", "退回", "轮数")},
                 "秒": round(time.time() - t0), "报错": err})
    x = rows[-1]; print(f"  → 判 {x['判·主因']} / {x['判·动作']}｜答案 {x['真·主因']} / {x['真·动作']}｜{'✅' if x['动作对'] else '❌'}｜{x['秒']} 秒")
    pd.DataFrame(rows).to_csv(OUT, index=False, encoding="utf-8-sig")  # 跑一题存一次，中途断了不白跑
    with open(TRACE, "a", encoding="utf-8") as f:
        f.write(json.dumps({"场景ID": r.场景ID, **res}, ensure_ascii=False, default=str) + "\n")
out = pd.DataFrame(rows).set_index("场景ID").loc[[i for i in m.场景ID if i in {x['场景ID'] for x in rows}]].reset_index()
base = pd.read_csv(s.ROOT / "data" / ("baseline_test.csv" if TEST else "baseline_result.csv"), encoding="utf-8-sig").set_index("场景ID").loc[out.场景ID]
pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 250)
print("\n" + out.drop(columns=["真·定位"]).to_string(index=False))
print(f"\n{'指标':<8}{'Agent ' + TAG:>22}{'规则基线':>12}{'代码版复核':>12}")
for k in ["主因对", "定位对", "动作对"]:
    x, y = out[k].dropna().astype(bool), base[k].dropna().astype(bool)
    z = f"{out.代码版对.sum()}/{len(out)} = {out.代码版对.mean():.0%}" if k == "动作对" else "—"
    print(f"{k:<8}{f'{x.sum()}/{len(x)} = {x.mean():.0%}':>22}{f'{y.sum()}/{len(y)} = {y.mean():.0%}':>14}{z:>14}")
fa = (out[out.场景ID.str.startswith("C")]["判·主因"] != "正常波动").agg(["sum", "size"])          # 对照周误报
fb = (base[base.index.str.startswith("C")]["判·主因"] != "正常波动").agg(["sum", "size"])
fc = (out[out.场景ID.str.startswith("C")]["代码版动作"] != "不行动").agg(["sum", "size"])
print(f"{'对照周误报':<6}{f'{fa.iloc[0]}/{fa.iloc[1]}':>22}{f'{fb.iloc[0]}/{fb.iloc[1]}':>14}{f'{fc.iloc[0]}/{fc.iloc[1]}':>14}")
print(f"代码直接判定 {(out.判定 == '代码').sum()} 题｜交给模型 {(out.判定 == '模型').sum()} 题｜校验最终不通过 {(~out.校验通过).sum()} 题｜平均 {out.秒.mean():.0f} 秒/题")
