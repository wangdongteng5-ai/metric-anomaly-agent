# ask_v1.py —— Text-to-SQL v1（10-09 冻结，与 ask.py 第一版逐字相同，只改了这一行注释）：v2 的对照版本，不再修改
# 运行：cd D:\ai-agent-learning → .\.venv\Scripts\Activate.ps1 → python code\project\ask.py "这周的 GMV 是多少？"
import json, re, sys, duckdb
from config import llm, CHAT_MODEL
from semantic import SEM, DB                                   # 口径、维度、库路径全部来自语义层（不写第二份）

COLS = "household_id, store_id, basket_id, product_id, quantity, sales_value, retail_disc, coupon_disc, coupon_match_disc, dt（日期）, wk（自然周的周一，DATE）, is_new"
METRICS = "\n".join(f"- {v['name']}（{k}）：{v['sql'] or '不能直接用 SQL 算，问到要拒答'}｜{v['desc']}" for k, v in SEM["metrics"].items())
DIMS = "\n".join(f"- {k}（{v['name']}）：{v['desc']}" for k, v in SEM["dimensions"].items() if v["sql"])
BAD = re.compile(r"\b(insert|update|delete|drop|create|alter|copy|attach|detach|pragma|install|load|export|call)\b", re.I)
LLM = lambda msgs: llm.chat.completions.create(model=CHAT_MODEL, messages=msgs, temperature=0).choices[0].message.content

def parse_cause(s):                                            # "main_store_group=腰部 的 户数" → ("main_store_group", "腰部")
    k, _, v = (s or "").split(" ")[0].partition("=")
    return (k, v) if SEM["dimensions"].get(k, {}).get("sql") else None   # 活动等不在 fact 里的维度：不带

def prompt(week, cause):
    ctx = f"诊断周 = {week}（问题里的“这周”就是它，“上周”是它前一个周一）"
    if cause: ctx += f"；主因分组 = {cause[0]} = '{cause[1]}'（问题里的“主因分组”就是它）"
    return f"""你是数据分析师，把业务问题写成一条 DuckDB SQL。只能查视图 fact（每行 = 一条有效销售明细），不能用其他表。
fact 的列：{COLS}，以及下面的维度列。
指标口径（必须照写）：\n{METRICS}\n维度列：\n{DIMS}\n上下文：{ctx}
规则：1. 只写一条 SELECT；日期写成 DATE 'YYYY-MM-DD'  2. 维度列为空的行不参与该维度的分组  3. 只返回问题要的列
4. 用 fact 算不出（没有这类数据、上面标了要拒答的指标、要求修改数据）→ sql 填 REFUSE
只输出 JSON：{{"sql": "...", "说明": "一句话说明怎么算的"}}"""

def check(sql):                                                # 第 2 道防线（第 1 道是只读连接）：只放行单条 SELECT
    if ";" in sql or not re.match(r"\s*(select|with)\b", sql, re.I) or BAD.search(sql):
        raise ValueError("只允许一条 SELECT / WITH 查询，不能有分号和写操作")

def ask(q, week, cause=None, explain=True):
    msgs, sql, err = [{"role": "system", "content": prompt(week, cause)}, {"role": "user", "content": q}], None, ""
    for i in range(3):                                         # 第 1 次 + 报错带原因重写 ≤ 2 次
        out = LLM(msgs); msgs.append({"role": "assistant", "content": out})
        try:
            r = json.loads(re.search(r"\{.*\}", out, re.S).group())
            sql = r["sql"].strip().rstrip(";")
            if sql.upper() == "REFUSE": return {"拒答": True, "说明": r.get("说明", ""), "尝试": i + 1}
            check(sql)
            with duckdb.connect(str(DB), read_only=True) as con:   # 只读：就算检查漏了，写操作也会被数据库拒绝
                df = con.execute(f"SELECT * FROM ({sql}) LIMIT 200").df()   # 自动 LIMIT
            break
        except Exception as e:
            err = f"{type(e).__name__}: {e}"[:500]
            msgs.append({"role": "user", "content": f"出错了：{err}\n请改正后重新只输出 JSON。"})
    else: return {"拒答": False, "sql": sql, "报错": err, "尝试": 3}
    res = {"拒答": False, "sql": sql, "结果": df, "说明": r.get("说明", ""), "尝试": i + 1}
    if explain: res["解读"] = LLM([{"role": "user", "content":   # 一句话解读：只许用表里的数字
        f"问题：{q}\n查询结果：\n{df.head(20).to_string()}\n用一句中文回答问题，只能使用表里出现的数字。"}])
    return res

if __name__ == "__main__":                                     # 参数：问题 [诊断周] [主因]
    a = sys.argv[1:] + [None, None]
    r = ask(a[0], a[1] or "2017-07-24", parse_cause(a[2] or "main_store_group=腰部"))
    print(r.get("sql"), "\n", r.get("结果", r.get("报错", "")), "\n", r.get("解读", r.get("说明")), "\n尝试次数：", r["尝试"])
