# audit.py —— 结论校验 = 规则检查 + 数字溯源（模型给出结论后执行；不通过就退回重写 1 次）
# v3（10-08）：改为对照"候选清单"检查——主因必须是候选之一，且满足复核标准 ①②③ 和动作映射；④（选最优）不强制，留给评估
# v3（10-08）加 code_review：同样的标准由代码执行，作为评估里的对照组（回答"大模型比代码多贡献了什么"）
import json, re
from prompt import SYSTEM, ACTIONS
TYPES = ["用户侧", "商品侧", "数据问题", "正常波动"]
FACTOR_ACTION = {"户数": "召回流失家庭", "频次": "提升频次", "客单价": "提升客单价"}
PRODUCT = ("department", "product_category")
def nums(text):
    """文字里的数字（字符串，保留小数位）；先去掉日期，避免 2017-10-16 被拆成 3 个数"""
    return re.findall(r"-?\d[\d,]*\.?\d*", re.sub(r"\d{4}-\d{2}-\d{2}", "", str(text)))
def traced(s, pool):
    """数字 s 能否在工具结果里找到：按 s 的小数位比较；也接受百分数写法（4.88% ↔ 0.0488）"""
    n, d = abs(float(s.replace(",", ""))), len(s.split(".")[1]) if "." in s else 0
    tol = 0.5 * 10 ** -d + 1e-9
    return any(abs(n - v) <= tol or abs(n / 100 - v) <= tol / 100 for v in pool)
def matches(c, cause):
    """主因文字是否指向候选 c（维度=分组 + 指标；全部写成"全部"或"整体"）"""
    name = ("全部", "整体") if c["维度"] == "全部" else (f"{c['维度']}={c['分组']}",)
    return any(re.search(rf"(?<![a-z_]){re.escape(n)}", cause) for n in name) and (c["指标"] == "GMV" or c["指标"] in cause)
def expect(c, scope):
    """候选 c 成为主因时，应有的（结论类型, 动作）"""
    if c["维度"] in PRODUCT or scope.startswith("department="): return "商品侧", "排查商品"
    return "用户侧", "补券" if c["维度"] == "camp" else FACTOR_ACTION[c["指标"]]
def fails(c, ctx):
    """候选 c 没通过的复核标准 ①②③（空列表 = 通过）"""
    ms, n = c.get("中位数异常分数"), f"{c['维度']}={c['分组']}·{c['指标']}"
    return ([f"标准①：{n} 的 vs前4周中位数 = {c['vs前4周中位数']}，没有下跌"] * (c["vs前4周中位数"] >= 0)
            + [f"标准②：上周含月初，{n} 的中位数异常分数 = {ms}，不小于 -1"] * ("上周含月初" in ctx["日历"] and (ms is None or ms >= -1))
            + [f"标准③：{n} 的体量占比 = {c.get('体量占比')}，< 0.1"] * (isinstance(c.get("体量占比"), float) and c["体量占比"] < .1))
def code_review(trace):
    """对照组：同样的标准由代码执行——①②③ 排除，④ 选两个分数中更负的最小者；代码已直接判定的题返回 None"""
    ctx = next((json.loads(t["结果"]) for t in trace if t["工具"] == "候选清单"), None)
    if ctx is None: return None
    ok = [c for c in ctx["候选"] if not fails(c, ctx)]
    if not ok: return "不行动"
    return expect(min(ok, key=lambda c: min(c["异常分数"], c["中位数异常分数"] if c["中位数异常分数"] is not None else 0)), ctx["提问范围"])[1]
def remap(ans, trace):
    """v4（h3）：主因选定后，结论类型和动作由代码按映射表定，不交给模型写（S26：主因选对、动作写错，退回 1 次仍没改）"""
    if not ans or ans.get("结论类型") not in ("用户侧", "商品侧"): return ans
    ctx = json.loads(next(t["结果"] for t in trace if t["工具"] == "候选清单"))
    hit = [c for c in ctx["候选"] if matches(c, str(ans.get("主因", "")))]
    if hit and (k := expect(hit[0], ctx["提问范围"])) != (ans["结论类型"], ans.get("动作")):
        ans = {**ans, "结论类型": k[0], "动作": k[1], "动作来源": f"代码映射（模型原写：{ans.get('动作')}）"}
    return ans
def audit(ans, trace):
    """返回问题清单；空列表 = 通过"""
    if not ans: return ["没有输出合法 JSON"]
    kind, cause, act = ans.get("结论类型"), str(ans.get("主因", "")), ans.get("动作")
    bad = [f"结论类型「{kind}」不在 {TYPES} 里"] * (kind not in TYPES) + [f"动作「{act}」不在 {ACTIONS} 里"] * (act not in ACTIONS)
    ctx = json.loads(next(t["结果"] for t in trace if t["工具"] == "候选清单"))
    cands, scope = ctx["候选"], ctx["提问范围"]
    if len(ans.get("候选复核", [])) < len(cands):
        bad.append(f"候选复核只写了 {len(ans.get('候选复核', []))} 个，候选清单有 {len(cands)} 个，要逐个复核")
    if kind in ("用户侧", "商品侧"):
        hit = [c for c in cands if matches(c, cause)]
        if not hit: bad.append(f"主因「{cause}」不是候选清单里的任何一个（写成 维度=分组 的 指标）")
        else:
            c = hit[0]; bad += fails(c, ctx)
            if (kind, act) != expect(c, scope): bad.append(f"这个主因应判为「{expect(c, scope)[0]}」、动作「{expect(c, scope)[1]}」")
    pool = [abs(float(x.replace(",", ""))) for src in [t["结果"] for t in trace] + [SYSTEM] for x in nums(src)]
    lost = [s for e in ans.get("证据", []) for s in nums(e) if not traced(s, pool)]   # 数字溯源
    if lost: bad.append(f"证据里的数字 {lost} 在候选清单和工具结果里找不到（只能原样引用，不要自己计算）")
    return bad
