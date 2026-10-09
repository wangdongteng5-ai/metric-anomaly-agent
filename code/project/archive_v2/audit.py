# audit.py —— M5 5-4（10-08）：结论校验 = 规则检查 + 数字溯源（gate 放行之后执行）
# 不通过：agent 把问题清单告诉模型重写 1 次；仍不通过就照常输出、带上问题清单（记为 badcase）
import json, re
from prompt import SYSTEM, ACTIONS
TYPES = ["用户侧", "商品侧", "数据问题", "正常波动"]
FACTOR_ACTION = {"户数": "召回流失家庭", "频次": "提升频次", "客单价": "提升客单价"}
PRODUCT_DIMS = ("department", "product_category")
def nums(text):
    """文字里的数字（字符串，保留小数位）；先去掉日期，避免 2017-10-16 被拆成 3 个数"""
    return re.findall(r"-?\d[\d,]*\.?\d*", re.sub(r"\d{4}-\d{2}-\d{2}", "", str(text)))
def traced(s, pool):
    """数字 s 能否在工具结果里找到：按 s 的小数位比较；也接受百分数写法（4.88% ↔ 0.0488）"""
    n, d = abs(float(s.replace(",", ""))), len(s.split(".")[1]) if "." in s else 0
    tol = 0.5 * 10 ** -d + 1e-9
    return any(abs(n - v) <= tol or abs(n / 100 - v) <= tol / 100 for v in pool)
def facts(trace):
    """trace 里真实 < -1 的证据：[(范围, 因子)]；商品组看 GMV证据，因子记为 None"""
    out = []
    for t in trace:
        r = json.loads(t["结果"])
        if t["工具"] == "decompose":
            out += [(r.get("范围"), x["因子"]) for x in r.get("拆解", []) if x["异常分数"] < -1]
        if t["工具"] == "drill_down" and r.get("维度") in PRODUCT_DIMS:
            out += [(f"{r['维度']}={g['分组']}", None) for g in r.get("分组", []) if (g.get("GMV证据") or {}).get("异常分数", 0) < -1]
    return out
def audit(ans, trace):
    """返回问题清单；空列表 = 通过"""
    if not ans: return ["没有输出合法 JSON"]
    kind, cause, act = ans.get("结论类型"), str(ans.get("主因", "")), ans.get("动作")
    bad = [f"结论类型「{kind}」不在 {TYPES} 里"] * (kind not in TYPES) + [f"动作「{act}」不在 {ACTIONS} 里"] * (act not in ACTIONS)
    for item in ans.get("异常分数小于-1的项", []):                  # ① 列出的分数必须真的 < -1
        if (v := nums(item)) and float(v[-1]) >= -1: bad.append(f"「{item}」的分数 {v[-1]} 不小于 -1，不能算超线")
    dec = [json.loads(t["结果"]) for t in trace if t["工具"] == "decompose"]
    scope0, ok = (dec[0].get("范围") if dec else None), facts(trace)  # scope0 = 第 2 步的提问范围
    hit = [(s, f) for s, f in ok if (re.search(rf"(?<![a-z_]){re.escape(s)}", cause) or (s == scope0 and "整体" in cause))
           and (f is None or f in cause)]
    if kind in ("用户侧", "商品侧") and not hit:                      # ② 主因必须有对应的 < -1 证据
        bad.append(f"主因「{cause}」在工具结果里找不到对应的 < -1 证据（用户类组要做组内 decompose，商品类组看 GMV证据）")
    if kind == "用户侧" and hit and hit[0][1] and act != FACTOR_ACTION[hit[0][1]]:   # ③ 动作要符合映射表
        bad.append(f"主因因子是{hit[0][1]}，动作应为「{FACTOR_ACTION[hit[0][1]]}」")
    if kind == "商品侧" and act != "排查商品": bad.append("商品侧的动作应为「排查商品」")
    if kind == "正常波动" and any(s == scope0 for s, _ in ok): bad.append("提问范围内已有因子 < -1，按规则 B 不能判正常波动")
    cd = next((json.loads(t["结果"]) for t in trace if t["工具"] == "check_data"), {})
    if kind == "数据问题" and (cd.get("日历", ["无"]) != ["无"] or not any(x.get("超线") for x in cd.get("检查", []))):
        bad.append("数据问题要求：日历为无，且 check_data 有超线项")
    pool = [abs(float(x.replace(",", ""))) for src in [t["结果"] for t in trace] + [SYSTEM] for x in nums(src)]
    lost = [s for e in ans.get("证据", []) for s in nums(e) if not traced(s, pool)]   # ④ 数字溯源
    if lost: bad.append(f"证据里的数字 {lost} 在工具结果里找不到（只能原样引用工具结果，不要自己计算）")
    return bad
