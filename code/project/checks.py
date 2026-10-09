# checks.py —— 代码兜底（硬控制）：guard 在模型调用工具前检查；parse 取出模型输出的 JSON；结论校验在 audit.py
# h2（10-08，配合 v3）：去掉"第 1 步必须 check_data""下钻 ≤ 2 个维度""gate"——这些步骤已改由 pipeline.py 代码执行
# h3（10-08 M7，v4）：check_data 按天检查改看全平台（tools.py）；动作由代码按映射改写（audit.remap）。依据：测试集 S34、S26
# h4（10-09 M8）：重构，判断逻辑不变——按 DATASET 选库（semantic.py）、数据质量阈值移进 metrics.yaml、无画像维度不扫（tools.py）；CJ 51 周 + 开发集回归一致
# h5（10-09 M8）：valid_to: auto（新一周到达后自动纳入）；诊断原始数据时按诊断周滚动分组（live.py 建 fact_asof），评估路径不变
# 保留：调用数上限、每轮调用数上限、重复调用拦截（v2 实测：一轮吐出 330 个重复调用把上下文撑爆）
import json, re
VERSION = "h5"                                    # harness 版本（checks + audit + pipeline）；改了就 +1，eval 结果里会记下
MAX_PER_ROUND, MAX_CALLS, MAX_STEPS = 4, 10, 8    # 每轮最多 4 个调用｜模型一题最多 10 个调用｜最多 8 轮

def guard(name, args, trace):
    """调用前：违反就不执行，把原因当观察还给模型（返回 None = 放行）"""
    if sum(t["轮"] > 0 for t in trace) >= MAX_CALLS:
        return f"本题工具调用已达上限 {MAX_CALLS} 次，本次未执行；请根据已有结果下结论"
    if any(t["工具"] == name and t["参数"] == args for t in trace):
        return "和之前某次调用完全相同，结果见上文，本次未执行"

def parse(text):
    """从模型文字里取出 JSON（去掉 ```json 包装）；坏 JSON 返回 None"""
    m = re.search(r"\{.*\}", text or "", re.S)
    try: return json.loads(m.group()) if m else None
    except json.JSONDecodeError: return None
