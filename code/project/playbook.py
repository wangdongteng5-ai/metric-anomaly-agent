# playbook.py —— M6 6-2 v2（10-08）：search_playbook = 向量检索策略手册（RAG，给模型读文字）
#                                    playbook_rule = 按动作名从 playbook.yaml 精确取硬数字（给 build_audience 算账）
# 运行前先启动 Ollama（bge-m3）｜自测：cd D:\ai-agent-learning → python code\project\playbook.py
import re, json, yaml, numpy as np
from pathlib import Path
from config import emb, EMB_MODEL
ROOT = Path(__file__).resolve().parents[2]                          # D:\ai-agent-learning
PB = yaml.safe_load(open(ROOT / "code/project/playbook.yaml", encoding="utf-8"))
MD = open(ROOT / "docs/策略手册.md", encoding="utf-8").read()
SECTIONS = {m.group(1).strip(): m.group(0).strip()                  # 按 "## 标题" 切段（Day 3：按标题切）
            for m in re.finditer(r"^## (.+?)\n.*?(?=^## |\Z)", MD, re.S | re.M)}
TITLES, VECS = list(SECTIONS), None

def embed(texts):
    return np.array([d.embedding for d in emb.embeddings.create(model=EMB_MODEL, input=texts).data])

def search_playbook(query, k=2):
    """问题 → 最相似的 k 段（附相似度）；"通用规则"每次都带上，不参与排名"""
    global VECS
    if VECS is None: VECS = embed([SECTIONS[t] for t in TITLES])    # 离线准备：第一次检索时把全部段落转成向量
    q = embed([query])[0]
    s = VECS @ q / (np.linalg.norm(VECS, axis=1) * np.linalg.norm(q))   # 余弦相似度
    top = [i for i in s.argsort()[::-1] if TITLES[i] != "通用规则"][:k]
    return {"通用规则": SECTIONS["通用规则"],
            "检索结果": [{"段落": TITLES[i], "相似度": round(float(s[i]), 3), "原文": SECTIONS[TITLES[i]]} for i in top]}

def playbook_rule(action):
    """动作名 → 硬数字；不走相似度：算钱的数字必须精确取"""
    if action not in PB["actions"]:
        return {"错误": f"playbook.yaml 里没有动作「{action}」，可选：{list(PB['actions'])}"}
    rule = dict(PB["actions"][action])
    if isinstance(rule.get("rate"), list):                          # [B, A] → 换成实际核销率区间
        rule["核销率区间"] = [PB["redemption_rate"][k] for k in rule["rate"]]
    return {**PB["global"], **rule}

if __name__ == "__main__":
    print("同步检查：yaml 有、md 没有 →", [a for a in PB["actions"] if a not in SECTIONS],
          "｜md 有、yaml 没有 →", [a for a in SECTIONS if a not in PB["actions"] and a != "通用规则"])
    hit = 0
    for a in PB["actions"]:                                         # 检索命中率：用动作名去搜，第 1 名是不是它自己
        r = search_playbook(a)["检索结果"]; hit += r[0]["段落"] == a
        print(f"  {a:　<6} → {[(x['段落'], x['相似度']) for x in r]}")
    print(f"检索命中（第 1 名）：{hit}/{len(PB['actions'])}")
    for q in ["满减和免运费哪个更适合召回", "活动刚结束，被触达的用户不来了怎么办"]:   # 自由提问
        print(q, "→", [(x["段落"], x["相似度"]) for x in search_playbook(q)["检索结果"]])
    print(json.dumps(playbook_rule("召回流失家庭"), ensure_ascii=False))
    print(playbook_rule("发短信"))
