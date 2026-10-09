# agent.py —— M5（10-08）：ReAct 主循环 + 硬控制（checks.py）+ 结论校验（audit.py）｜运行：python code\project\agent.py
import json, time
from openai import RateLimitError, APITimeoutError
from config import llm, CHAT_MODEL
from prompt import SYSTEM, VERSION
from tool_spec import TOOLS, call, tl
from checks import guard, gate, parse, MAX_PER_ROUND, MAX_STEPS   # 所有上限都在 checks.py
from audit import audit
def chat(msgs):
    for i in range(3):                            # 限流 / 接口返回空：等待后重发
        try:
            resp = llm.chat.completions.create(model=CHAT_MODEL, messages=msgs, tools=TOOLS,
                                               temperature=0, max_tokens=1500, timeout=120)  # 防吐出几百个调用；2 分钟没回就重试
            if resp.choices: return resp.choices[0].message
            print(f"  [接口返回空] {getattr(resp, 'error', '')}")
        except (RateLimitError, APITimeoutError) as e: print(f"  [{type(e).__name__}] 等待后重试（第 {i + 1} 次）")
        time.sleep(10 * (i + 1))
    raise RuntimeError("接口连续失败（限流或上下文过长），稍后再试")
def run(question, src="fact", tx="transactions"):
    tl.SRC, tl.TX = src, tx; print(f"\n[{VERSION}] {src}｜{question}")   # 评估时换成注入后的表；模型看不到
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": question}]
    trace, dims, blocked, retried = [], set(), 0, False   # trace 留给 5-4 溯源、5-5 打分
    for step in range(1, MAX_STEPS + 1):          # ===== ReAct 循环 =====
        reply = chat(msgs)
        if not reply.tool_calls:                  # 模型想下结论 → gate（步骤做够没）→ audit（结论对得上证据没）
            ans = parse(reply.content); err = gate(trace, ans); bad = [] if err else audit(ans, trace)
            if not err and (not bad or retried):  # audit 只给 1 次重写机会；仍不通过就带着问题清单输出
                return {"回答": ans, "原文": reply.content, "trace": trace, "拦截": blocked, "轮数": step, "校验": bad}
            if bad: retried, err = True, "；".join(bad)
            blocked += 1; print(f"  第{step}轮 退回结论：{err}")
            msgs += [{"role": "assistant", "content": reply.content or ""}, {"role": "user", "content": f"【系统检查未通过】{err}"}]; continue
        calls, extra = reply.tool_calls[:MAX_PER_ROUND], len(reply.tool_calls) - MAX_PER_ROUND
        m = reply.model_dump(exclude_none=True); m["tool_calls"] = m["tool_calls"][:MAX_PER_ROUND]; msgs.append(m)
        for c in calls:                           # 一轮只执行前 4 个，其余直接丢弃
            name, args = c.function.name, parse(c.function.arguments or "{}")
            err = "参数不是合法 JSON，本次未执行" if args is None else guard(name, args, trace, dims)
            if err: blocked += 1; result = json.dumps({"错误": err}, ensure_ascii=False)
            else:
                result = call(name, args); trace.append({"轮": step, "工具": name, "参数": args, "结果": result})
                if name == "drill_down": dims.add(args.get("dim"))
            print(f"  第{step}轮 {'拦截' if err else '调用'} {name}({args})")
            msgs.append({"role": "tool", "tool_call_id": c.id, "content": result})
        if extra > 0: blocked += extra; print(f"  第{step}轮 丢弃 {extra} 个多余调用"); msgs.append(
                {"role": "user", "content": f"【系统】一轮最多执行 {MAX_PER_ROUND} 个调用，其余 {extra} 个已丢弃；看完结果再决定下一步"})
    return {"回答": None, "原文": "超过最大轮数，停止", "trace": trace, "拦截": blocked, "轮数": MAX_STEPS}
if __name__ == "__main__":                        # 先跑 2 个对照：S03（有注入）/ C04（自然下跌）
    for src, wk in [("fact_S03", "2017-04-03"), ("fact_C04", "2017-10-16")]:
        res = run(f"第 {wk} 周 GMV 为什么变了？该怎么办？", src)
        print(f"  轮数 {res['轮数']}｜工具调用 {len(res['trace'])} 次｜拦截 {res['拦截']} 次｜校验问题 {res.get('校验')}\n"
              + (json.dumps(res["回答"], ensure_ascii=False, indent=2) if res["回答"] else res["原文"]))
