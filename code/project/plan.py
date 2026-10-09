# plan.py —— M6 6-5（10-08）诊断 → 方案卡：agent.run 出结论 → 代码算名单 / 实验 → 代码写执行摘要 → RAG 取手册 → 模型写理由 + 风险 → 溯源校验 → 建议（需人工确认后执行；v1.8 起不做审批）
# 运行：cd D:\ai-agent-learning → python code\project\plan.py（需要 Ollama + OpenRouter）｜审批：python code\project\approve.py
import json, time
from pathlib import Path
import tools as tl
from config import llm, CHAT_MODEL
from audit import matches, nums, traced
from audience import build_audience
from experiment import design_test
from playbook import search_playbook
OUT = Path(tl.s.DB).parent / "plans"
SYS = """你是运营方案撰写助手。执行信息（名单、对照组、成本、验证周数）已由代码写在执行摘要里，你不用重复。
根据【诊断】【策略手册】写 2～3 句给运营看：① 为什么是这个动作（引用诊断证据）② 风险提示：必须引用策略手册"注意"那一条 ③ 可提一个备选手段。
规则：数字只能原样引用给定内容里的，不要自己计算。只输出说明文字。"""

def cause_of(res):
    """主因文字 → 候选清单里的 (维度, 分组)；代码直接判定的题（数据问题 / 正常波动）返回 None"""
    ctx = next((json.loads(t["结果"]) for t in res["trace"] if t["工具"] == "候选清单"), None)
    hit = [c for c in (ctx or {}).get("候选", []) if matches(c, str(res["回答"].get("主因", "")))]
    return (hit[0]["维度"], hit[0]["分组"]) if hit else None

def write_note(mat):
    """模型写说明 → 数字溯源（同 audit）→ 不通过重写 1 次，仍不通过就标出来交给人看"""
    pool = [abs(float(x.replace(",", ""))) for x in nums(json.dumps(mat, ensure_ascii=False, default=str))]
    msgs = [{"role": "system", "content": SYS}, {"role": "user", "content": json.dumps(mat, ensure_ascii=False, default=str)}]
    for i in range(2):
        note = llm.chat.completions.create(model=CHAT_MODEL, messages=msgs, temperature=0, max_tokens=600).choices[0].message.content
        lost = [x for x in nums(note) if not traced(x, pool)]
        if not lost: return note, []
        msgs += [{"role": "assistant", "content": note}, {"role": "user", "content": f"数字 {lost} 在材料里找不到，只能原样引用，请重写"}]
    return note, lost

def summary(mat):
    """执行摘要：执行必需的信息全部由代码生成，不交给模型写（6-5 修法 A，10-08 Morgan）"""
    a, e = mat.get("名单", {}), mat.get("实验")
    if not e: return ""
    x = next(r for r in e["方案"] if r["对照组比例"] == e["对照组比例"])
    warn = ([f"⚠️ 按当前对照比例，单周 MDE {x['MDE']:.1%} 大于效果上限 {e['效果上限(核销率)']:.1%}：单周连上限都测不出"] * (not x["测得出上限吗"])
            + [f"⚠️ 需累计 {x['要累计几周(测6.5pp)']} 周，周期长：可把对照提到 50%（{e['方案'][-1]['要累计几周(测6.5pp)']} 周）或只做方向判断"] * (x["要累计几周(测6.5pp)"] > 8))
    return "\n".join(["## 执行摘要（代码生成）", "| 项 | 内容 |", "|---|---|",
        f"| 名单 | 圈人 {a['圈人']} → 排除疲劳 {a['排除疲劳']}、频控 {a['排除频控']} → **{a['最终人数']} 户** |",
        f"| 发券（实验组） | **{e['分组'].get('实验', 0)} 户**：{a['权益']} |",
        f"| 不发（对照组） | **{e['分组'].get('对照', 0)} 户**（{e['对照组比例']:.0%}，按 {e['实验名']} 哈希固定，跨周不换组） |",
        f"| 成本 | {a['成本区间'][0]}～{a['成本区间'][1]} 美元 |",
        f"| 用券户 GMV | {a['用券户GMV区间（非增量）'][0]}～{a['用券户GMV区间（非增量）'][1]} 美元（**不是增量**：自然回流率 {e['自然回流率(历史8周)']:.1%}） |",
        f"| 何时执行 | **本周即可执行**，不用等实验结果 |",
        f"| 对照组用途 | 评估该策略本身；本数据规模（2,469 户抽样）下约需累计 {x['要累计几周(测6.5pp)']} 周，真实平台规模下显著缩短 |"]
        + ([""] + warn if warn else [])) + "\n\n"                    # 空一行，警示不会被并进表格

def make_plan(res, week, scope="全部"):
    ans, act = res["回答"], res["回答"]["动作"]
    f = None if scope == "全部" else dict(zip(["dim", "value"], scope.split("=", 1)))
    mat, c = {"诊断": {k: ans.get(k) for k in ("结论类型", "主因", "动作", "证据")}}, cause_of(res)
    if c and act in ("召回流失家庭", "提升频次", "提升客单价", "补券"):
        mat["名单"] = aud = build_audience(week, act, *c, filter=f)
        if "错误" not in aud: mat["实验"] = {k: v for k, v in design_test(aud).items() if k != "说明"}
    elif c and act == "排查商品":
        g = {"dim": "department", "value": c[1]} if c[0] == "department" else f
        mat["问题商品"] = [{k: x[k] for k in ("分组", "GMV贡献额")} for x in tl.drill_down(week, "product_category", g, top=20)["分组"]]
    mat["策略手册"] = [x["原文"] for x in search_playbook(f"{act}：{ans.get('主因', '')}", k=1)["检索结果"]]
    note, lost = write_note(mat)
    OUT.mkdir(exist_ok=True); card = OUT / f"{tl.SRC}_{week}_{act}.md"
    card.write_text(f"# 方案卡｜{week}｜{scope}｜{act}\n\n状态：建议（需人工确认后执行）\n\n{summary(mat)}## 方案说明（模型撰写）\n{note}\n\n"
                    + (f"⚠️ 溯源未通过的数字：{lost}\n\n" if lost else "")
                    + f"## 材料（代码计算）\n```json\n{json.dumps(mat, ensure_ascii=False, indent=2, default=str)}\n```\n", encoding="utf-8")
    return card

if __name__ == "__main__":
    from agent import run
    for src, wk in [("fact_S01", "2017-07-24"), ("fact_S03", "2017-04-03")]:
        res = run(wk, "全部", src)
        if res["回答"]: print("方案卡：", make_plan(res, wk)); time.sleep(2)
