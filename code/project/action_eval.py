# action_eval.py —— M7 第 5 步（10-08）：测试集方案卡的 3 个自动指标（不需要人工审）
# 输入 = eval test 那一次运行的 trace（不重新诊断）→ 冻结的 plan.make_plan 出方案卡 → 打分
#   ① 人群包一致率：代码名单 vs 按策略手册定义用 pandas 独立重算的名单（Jaccard，≥ 0.9）
#   ② 规则合规：名单里的疲劳户 / 频控满户（独立重算）+ 每户成本超限（0 条）
#   ③ 数字溯源率：诊断证据 + 方案说明里的数字，能否在工具结果 / 材料里找到（≥ 99%）
# 运行：python code\project\action_eval.py（需要 Ollama + OpenRouter；约 21 张卡、10～15 分钟）→ data\action_eval_test.csv
import json, re, sys, pandas as pd, yaml
from freeze import check
if bad := check(): sys.exit(f"❌ 系统冻结后被改过：{bad}")
import tools as tl
from plan import make_plan
from audit import nums, traced
from prompt import SYSTEM
ROOT = tl.s.ROOT
Y = yaml.safe_load(open(ROOT / "code/project/playbook.yaml", encoding="utf-8"))
G, CARD = Y["global"], ("召回流失家庭", "提升频次", "提升客单价", "补券", "排查商品")
H = tl.con.execute("SELECT household_id::VARCHAR h, campaign_id, CAST(start_date AS DATE) s, CAST(end_date AS DATE) e FROM campaigns JOIN campaign_descriptions USING (campaign_id)").df()
R = tl.con.execute("SELECT household_id::VARCHAR h, CAST(redemption_date AS DATE) r FROM coupon_redemptions").df()
num = lambda text: [abs(float(x.replace(",", ""))) for x in nums(text)]

def blocked(week):
    """疲劳户 = 本周前被 ≥ 5 个活动触达且从未核销；频控满 = 本月已被 ≥ 2 个活动触达（策略手册 D2 / D3）"""
    w = pd.Timestamp(week); m0, m1 = w.replace(day=1), w + pd.offsets.MonthEnd(0)
    n = H[H.s < w].groupby("h").campaign_id.nunique(); k = H[(H.s <= m1) & (H.e >= m0)].groupby("h").campaign_id.nunique()
    return set(n[n >= G["fatigue_min_campaigns"]].index) - set(R[R.r < w].h), set(k[k >= G["freq_cap_per_month"]].index)

def my_list(week, act, dim, grp, scope):
    """按策略手册的文字定义独立圈人（不调用 audience.py）：前 4 周 vs 本周的单数 / 客单价"""
    w, cond = pd.Timestamp(week), "" if scope == "全部" else " AND {} = '{}'".format(*scope.split("=", 1))
    if dim not in ("全部", "camp"): cond += f" AND {dim} = '{grp}'"
    f = tl.con.execute(f"SELECT household_id::VARCHAR h, wk, basket_id, sales_value g FROM {tl.SRC} WHERE wk BETWEEN DATE '{week}' - 28 AND DATE '{week}'{cond}").df()
    if dim == "camp": f = f[f.h.isin(H[(H.e >= w - pd.Timedelta(days=14)) & (H.e < w)].h)]
    now = f.wk == w
    x = pd.DataFrame({"b1": f[now].groupby("h").basket_id.nunique(), "g1": f[now].groupby("h").g.sum(),
                      "b4": f[~now].groupby("h").basket_id.nunique(), "g4": f[~now].groupby("h").g.sum()}).fillna(0)
    rule = {"召回流失家庭": (x.b4 > 0) & (x.b1 == 0), "提升客单价": (x.b1 > 0) & (x.b4 > 0) & (x.g1 / x.b1.clip(1) < x.g4 / x.b4.clip(1))}
    pick = set(x[rule.get(act, (x.b1 > 0) & (x.b1 < x.b4 / 4))].index)          # 提升频次 / 补券：本周单数 < 前 4 周周均
    fat, cap = blocked(week)
    return pick - fat - cap

if __name__ == "__main__":
    man, rows = pd.read_csv(ROOT / "data/manifest_test.csv", dtype=str, encoding="utf-8-sig").set_index("场景ID"), []
    for line in open(ROOT / "data/eval_test_promptv3_h2_trace.jsonl", encoding="utf-8"):
        d = json.loads(line); a, r = d.get("回答") or {}, man.loc[d["场景ID"]]
        pool, ev = [v for t in d["trace"] for v in num(t["结果"])] + num(SYSTEM), [x for e in a.get("证据", []) for x in nums(e)]
        row = {"场景ID": d["场景ID"], "动作": a.get("动作"), "证据数字": len(ev), "证据可溯源": sum(traced(x, pool) for x in ev)}
        if a.get("动作") in CARD:
            tl.SRC, tl.TX = f"fact_{d['场景ID']}", "transactions"
            try: card = make_plan(d, r.周, r.提问范围).read_text(encoding="utf-8")
            except Exception as e: rows.append({**row, "报错": str(e)}); print(f"  ⚠️ {d['场景ID']} {e}"); continue
            mat = json.loads(card.split("```json\n")[1].split("\n```")[0])
            note = re.split(r"\n\n(?:⚠️|## 材料)", card.split("## 方案说明（模型撰写）\n")[1])[0]
            row.update(说明数字=len(nums(note)), 说明可溯源=sum(traced(x, num(json.dumps(mat, ensure_ascii=False))) for x in nums(note)))
            aud = mat.get("名单", {})
            if "人群包" in aud:
                got, (dim, grp) = set(pd.read_csv(aud["人群包"], dtype=str).household_id), aud["主因分组"].split("=", 1)
                mine, (fat, cap) = my_list(r.周, a["动作"], dim, grp, r.提问范围), blocked(r.周)
                p = Y["actions"][a["动作"]]
                row.update(名单=len(got), 独立重算=len(mine), Jaccard=round(len(got & mine) / max(len(got | mine), 1), 3),
                           违规户=len(got & (fat | cap)), 成本超限=int(p["coupons_per_hh"] * G["coupon_face"] > G["max_cost_per_hh"]))
        rows.append(row); print(row)
    out = pd.DataFrame(rows); out.to_csv(ROOT / "data/action_eval_test.csv", index=False, encoding="utf-8-sig")
    n, t = out[["证据数字", "说明数字"]].sum().sum(), out[["证据可溯源", "说明可溯源"]].sum().sum()
    print(f"\n① 人群包一致率 {out.Jaccard.mean():.3f}（{out.Jaccard.count()} 个名单，最低 {out.Jaccard.min()}）")
    print(f"② 规则违规 {int(out.违规户.sum() + out.成本超限.sum())} 条（违规户 {int(out.违规户.sum())}、成本超限 {int(out.成本超限.sum())}）")
    print(f"③ 数字溯源率 {t:.0f}/{n:.0f} = {t / n:.1%}（诊断证据 {out.证据可溯源.sum():.0f}/{out.证据数字.sum():.0f}，方案说明 {out.说明可溯源.sum():.0f}/{out.说明数字.sum():.0f}）")
