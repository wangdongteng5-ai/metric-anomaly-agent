# pipeline.py —— v3（10-08）：代码先做的固定步骤 = 数据质量判定 → 整体拆解 → 召回扫描 → 给候选补体量
# 能由代码确定的结论（节假日 / 数据问题 / 0 个候选）直接返回，不调模型；其余整理成"候选清单"交给模型复核
import json
import tools as tl
from tool_spec import call
USER_DIMS = ("main_store_group", "age_band", "income_band")      # 能用 drill_down 查体量的用户维度（camp 不能）

def step(trace, name, args, fn=None):
    """执行一步并记进 trace（轮 = 0 表示代码执行，不是模型调用）"""
    res = json.dumps(fn(**args), ensure_ascii=False, default=str) if fn else call(name, args)
    trace.append({"轮": 0, "工具": name, "参数": args, "结果": res})
    return json.loads(res)

def answer(kind, cause, act, ev):
    return {"结论类型": kind, "主因": cause, "动作": act, "证据": ev, "判定": "代码"}

def prepare(week, f):
    """返回 (代码直接给出的答案 或 None, 给模型的候选清单, trace)"""
    trace, a = [], {"week": week, **({"filter": f} if f else {})}
    cd = step(trace, "check_data", a)
    if cd["日历"] != ["无"]:
        return answer("正常波动", "无", "不行动", [f"本周是节假日表内的周：{cd['日历'][0]}"]), None, trace
    if over := [x for x in cd["检查"] if x["超线"]]:
        return answer("数据问题", "数据质量：" + "、".join(x["项目"] for x in over), "修数据",
                      [f"{x['项目']} {x['值']} 超过阈值 {x['阈值']}" for x in over]), None, trace
    dec = step(trace, "decompose", a)
    sc = step(trace, "scan", {**a, "top": 15}, tl.scan)
    if not sc["候选"]:
        return answer("正常波动", "无", "不行动", ["召回扫描 0 个候选：所有维度 × 分组 × 指标的两个分数都不小于 -1"]), None, trace
    total, cands = dec["GMV变化额"], sc["候选"]
    for d in sorted({c["维度"] for c in cands} & set(USER_DIMS)):  # 用户维度：用 drill_down 查各组 GMV 贡献额
        g = {str(x["分组"]): x["GMV贡献额"] for x in step(trace, "drill_down", {**a, "dim": d, "top": 50})["分组"]}
        for c in cands:
            if c["维度"] == d: c["GMV变化额"] = g.get(c["分组"])
    for c in cands:
        if c["维度"] in tl.PRODUCT: c["GMV变化额"] = round(c["本周"] - c["上周"], 2)
        v = c.get("GMV变化额")
        c["体量占比"] = round(abs(v) / abs(total), 3) if v is not None and total else "不适用"
    ctx = {"提问范围": dec["范围"], "周": week, "日历": sc["日历"], "范围GMV变化额": total, "候选数": sc["候选数"],
           "整体拆解": [{k: x[k] for k in ("因子", "贡献额", "异常分数", "vs前4周中位数")} for x in dec["拆解"]], "候选": cands}
    trace.append({"轮": 0, "工具": "候选清单", "参数": {}, "结果": json.dumps(ctx, ensure_ascii=False, default=str)})
    return None, ctx, trace
