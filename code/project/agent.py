# agent.py —— v3（10-08）：代码召回（pipeline.py）→ 模型复核（ReAct，可补查工具）→ 结论校验（audit.py）
# 运行：cd D:\ai-agent-learning → python code\project\agent.py（不需要 Ollama）；v2 存档在 archive_v2\
import json, time
from openai import RateLimitError, APITimeoutError, APIStatusError
from config import llm, CHAT_MODEL
from prompt import SYSTEM, VERSION
from tool_spec import TOOLS, call, tl
from checks import guard, parse, MAX_PER_ROUND, MAX_STEPS
from audit import audit, remap
from pipeline import prepare
TOOLS3 = [t for t in TOOLS if t["function"]["name"] in ("query_metric", "decompose", "drill_down")]  # 模型可补查的工具
def chat(msgs):
    for i in range(4):                            # 限流 / 超时 / 上游 5xx：等待后重发
        try:
            resp = llm.chat.completions.create(model=CHAT_MODEL, messages=msgs, tools=TOOLS3,
                                               temperature=0, max_tokens=2500, timeout=120)
            if resp.choices: return resp.choices[0].message
            print(f"  [接口返回空] {getattr(resp, 'error', '')}")
        except (RateLimitError, APITimeoutError, APIStatusError) as e: print(f"  [{type(e).__name__}] 等待后重试（第 {i + 1} 次）")
        time.sleep(15 * (i + 1))
    raise RuntimeError("接口连续失败（限流 / 上游故障 / 上下文过长），稍后再试")
def run(week, scope="全部", src="fact", tx="transactions"):
    tl.SRC, tl.TX = src, tx; f = None if scope == "全部" else dict(zip(["dim", "value"], scope.split("=", 1)))  # 换表：模型看不到
    q = f"第 {week} 周 GMV{'' if not f else f'（提问范围：{scope}）'} 为什么变了？该怎么办？"; print(f"\n[{VERSION}] {src}｜{q}")
    (early, ctx, trace), n = prepare(week, f), {"拦截": 0, "丢弃": 0, "退回": 0}   # 代码先做：数据质量 → 拆解 → 召回 → 体量
    if early: print(f"  代码判定：{early['结论类型']}"); return {"回答": early, "trace": trace, **n, "轮数": 0, "校验": []}
    print(f"  召回 {ctx['候选数']} 个候选，交给模型复核")
    msgs = [{"role": "system", "content": SYSTEM},
            {"role": "user", "content": f"{q}\n候选清单（代码已算好）：\n{json.dumps(ctx, ensure_ascii=False, default=str)}"}]
    for step in range(1, MAX_STEPS + 1):          # ===== 复核循环（ReAct）=====
        reply = chat(msgs)
        if not reply.tool_calls:                  # 模型给出结论 → audit；只给 1 次重写机会
            ans = remap(parse(reply.content), trace); bad = audit(ans, trace)   # v4：动作由代码映射
            if not bad or n["退回"]: return {"回答": ans, "trace": trace, **n, "轮数": step, "校验": bad}
            n["退回"] += 1; print(f"  第{step}轮 退回：{'；'.join(bad)}")
            msgs += [{"role": "assistant", "content": reply.content or ""}, {"role": "user", "content": "【校验未通过】" + "；".join(bad)}]; continue
        n["丢弃"] += max(0, len(reply.tool_calls) - MAX_PER_ROUND)
        m = reply.model_dump(exclude_none=True); m["tool_calls"] = m["tool_calls"][:MAX_PER_ROUND]; msgs.append(m)
        for c in reply.tool_calls[:MAX_PER_ROUND]:    # 一轮只执行前 4 个，其余丢弃
            name, args = c.function.name, parse(c.function.arguments or "{}")
            err = "参数不是合法 JSON，本次未执行" if args is None else guard(name, args, trace)
            if err: n["拦截"] += 1; result = json.dumps({"错误": err}, ensure_ascii=False)
            else: result = call(name, args); trace.append({"轮": step, "工具": name, "参数": args, "结果": result})
            print(f"  第{step}轮 {'拦截' if err else '调用'} {name}({args})")
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": result})
    return {"回答": None, "trace": trace, **n, "轮数": MAX_STEPS, "校验": ["超过最大轮数"]}
if __name__ == "__main__":                        # 先跑 3 个对照：S03（有注入）/ C04、C01（自然波动）
    for src, wk in [("fact_S03", "2017-04-03"), ("fact_C04", "2017-10-16"), ("fact_C01", "2017-08-07")]:
        res = run(wk, "全部", src)
        print(json.dumps({k: res[k] for k in ("拦截", "丢弃", "退回", "轮数", "校验", "回答")}, ensure_ascii=False, indent=2))
