# tool_spec.py —— M5 5-1（10-08）：工具说明书（给模型看的 JSON schema）+ 统一调用入口 call()
# 模型只看得到 TOOLS；SRC / TX / top 不写进说明书，模型看不到也选不了
# 自测：cd D:\ai-agent-learning → python code\project\tool_spec.py
import json
import semantic as s, tools as tl

METRICS = [k for k, x in s.SEM["metrics"].items() if x["sql"]]        # 枚举从语义层读，不写第二份
DIMS = [k for k, x in s.SEM["dimensions"].items() if x["sql"]]
DIM_DESC = "\n".join(f"- {k}（{x['name']}）：{x['desc']}" for k, x in s.SEM["dimensions"].items() if x["sql"])  # 5-3 加 desc
WEEK = {"type": "string", "description": "周一日期 YYYY-MM-DD，范围 2017-01-09 ～ 2017-12-25"}
FILTER = {"type": "object", "description": '可选：只看某个分组，如 {"dim": "age_band", "value": "55岁及以上"}',
          "properties": {"dim": {"type": "string", "enum": DIMS}, "value": {"type": "string"}},
          "required": ["dim", "value"]}

def fn(name, desc, props, req):
    return {"type": "function", "function": {"name": name, "description": desc,
            "parameters": {"type": "object", "properties": props, "required": req}}}

TOOLS = [
    fn("query_metric", "查某指标某周的值、环比、vs前4周中位数、异常分数（< -1 = 跌幅超出自身历史 9 成的周）、日历标记",
       {"metric": {"type": "string", "enum": METRICS}, "week": WEEK, "filter": FILTER}, ["metric", "week"]),
    fn("decompose", "把 GMV 变化拆成 户数 × 频次 × 客单价 三个因子的贡献额（美元，三者相加 = GMV变化额），每个因子附异常分数",
       {"week": WEEK, "filter": FILTER}, ["week"]),
    fn("drill_down", f"按一个维度下钻：各分组 GMV 贡献额（最负的排前）+ 客单价的结构/比率拆分。可选维度：\n{DIM_DESC}",
       {"week": WEEK, "dim": {"type": "string", "enum": DIMS}, "filter": FILTER}, ["week", "dim"]),
    fn("check_data", "数据质量 3 项检查（无效行占比 / 连续大跌天数 / 门店变0占上周GMV）：只报值、阈值、是否超线、日历、按天环比",
       {"week": WEEK, "filter": FILTER}, ["week"]),
]
FUNCS = {"query_metric": tl.query_metric, "decompose": tl.decompose,
         "drill_down": tl.drill_down, "check_data": tl.check_data}

def call(name, args):
    """执行一次工具调用 → JSON 字符串。出错不崩溃：把错误原文当成"观察"还给模型，让它自己改参数"""
    if name not in FUNCS:
        return json.dumps({"错误": f"没有工具 {name}，可选：{list(FUNCS)}"}, ensure_ascii=False)
    try:
        out = FUNCS[name](**args)
    except Exception as e:                                              # 参数错 / 周不对 / 维度不存在…
        out = {"错误": f"{type(e).__name__}: {e}"}
        print(f"  [工具报错] {name}({args}) → {out['错误']}")            # 控制台也打一份，防止真 bug 被吞掉
    return json.dumps(out, ensure_ascii=False, default=str)

if __name__ == "__main__":
    print("说明书约", len(json.dumps(TOOLS, ensure_ascii=False)), "字符｜维度枚举", DIMS)
    tl.SRC = "fact_S03"                                                 # 自测用 S03 的注入数据
    res = json.loads(call("decompose", {"week": "2017-04-03", "filter": {"dim": "main_store_group", "value": "腰部"}}))
    print(res["范围"], [(x["因子"], x["贡献额"], x["异常分数"]) for x in res["拆解"]])
    print(call("drill_down", {"week": "2017-04-03", "dim": "dau"}))     # 维度不存在
    print(call("query_metric", {"metric": "gmv", "week": "2017-04-05"}))  # 不是周一
