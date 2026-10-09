# checks.py —— M5（10-08）：代码兜底（硬控制）集中在这里，prompt 里是软规则，这里保证一定执行
# guard：调用工具前检查｜gate：模型下结论前检查｜5-4 再加：规则检查 + 数字溯源
# 10-08 gate 加"判正常波动前必须查够"：S03 只下钻 1 个维度就判正常（漏报）
# 10-08 加调用数上限 + parse 搬来：C04 一轮吐出 330 个 query_metric，上下文爆掉、接口返回空
import json, re
VERSION = "h1"                                    # harness 版本（checks + audit）；改了检查规则就 +1，eval 结果里会记下
MAX_DIMS = 2                                      # 每题最多下钻 2 个维度（防多重比较误报）
MAX_PER_ROUND, MAX_CALLS = 4, 20                  # 一轮最多执行 4 个调用；一题最多 20 个（正常约 7 个）
MAX_STEPS = 12                                    # 最多 12 轮：正常约 7 轮（查满 2 个维度 + 组内验证 + 重写 1 次）
USER_DIMS = {"main_store_group", "store_group", "age_band", "income_band", "customer_type"}

def guard(name, args, trace, dims):
    """调用前：违反就不执行，把原因当观察还给模型（返回 None = 放行）"""
    if len(trace) >= MAX_CALLS:
        return f"本题工具调用已达上限 {MAX_CALLS} 次，本次未执行；请根据已有结果下结论"
    if any(t["工具"] == name and t["参数"] == args for t in trace):
        return "和之前某次调用完全相同，结果见上文，本次未执行"
    if not trace and name != "check_data":
        return "第 1 步必须先调用 check_data(week)，本次调用未执行"
    if name == "drill_down" and args.get("dim") not in dims and len(dims) >= MAX_DIMS:
        return f"已下钻 {sorted(dims)}，最多 {MAX_DIMS} 个维度，本次未执行；请按规则 B、C 判断"

def parse(text):
    """从模型文字里取出 JSON（去掉 ```json 包装）；坏 JSON 返回 None"""
    m = re.search(r"\{.*\}", text or "", re.S)
    try: return json.loads(m.group()) if m else None
    except json.JSONDecodeError: return None

def gate(trace, answer):
    """下结论前：必做步骤没做完就退回（返回 None = 放行）"""
    done = [t["工具"] for t in trace]
    if "check_data" not in done:
        return "还没调用 check_data，不能下结论"
    cd = json.loads(next(t["结果"] for t in trace if t["工具"] == "check_data"))
    if cd.get("日历", ["无"]) != ["无"] or any(x.get("超线") for x in cd.get("检查", [])):
        return None                               # 节假日周 / 有项超线：第 1 步就可以结束
    if "decompose" not in done:
        return "check_data 都没超线，第 2 步 decompose(week, filter=提问范围) 还没做，不能下结论"
    if (answer or {}).get("结论类型") != "正常波动":
        return None                               # 判主因的检查留给 5-4（规则检查 + 数字溯源）
    drills = [t for t in trace if t["工具"] == "drill_down"]
    dims = {t["参数"].get("dim") for t in drills}
    if len(dims) < MAX_DIMS:                      # 判"没有异常"前必须查够，防漏报
        return f"判正常波动前必须下钻 {MAX_DIMS} 个不同维度，目前只有 {sorted(dims)}，请再选一个维度"
    for t in drills:                              # 用户类维度：排第 1 的组必须做过组内 decompose
        dim, top = t["参数"]["dim"], (json.loads(t["结果"]).get("分组") or [{}])[0].get("分组")
        if dim in USER_DIMS and top and not any(x["工具"] == "decompose" and (x["参数"].get("filter") or {})
                                                .get("value") == str(top) for x in trace):
            return f"{dim} 排第 1 的组「{top}」还没做组内验证：decompose(week, filter={{dim: {dim}, value: {top}}})"
