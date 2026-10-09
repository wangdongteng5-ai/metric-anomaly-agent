# live.py —— M8 8-2（10-09）：现场跑一题（代码召回 → 模型复核 → 方案卡），最后一行输出 JSON；app.py 用子进程调用，也可单独运行
# 运行：python code\project\live.py <数据集> <周> [提问范围] [表] [交易表]   例：python code\project\live.py cj_ecom 2017-07-24
# 为什么是子进程：semantic / tools 在 import 时就绑定了数据库，换数据集必须开新进程；这样也不用改任何冻结文件
import os, sys, json
os.environ["DATASET"] = sys.argv[1]                       # 必须在 import semantic 之前
from pathlib import Path
import requests, tools as tl, audience, plan
from agent import run
a = sys.argv[2:] + [None] * 3                             # 没给的参数用默认值：全部 / 原始 fact / 原始交易表
week, scope, src, tx = a[0], a[1] or "全部", a[2] or "fact", a[3] or "transactions"
OUT = Path(tl.s.DB).parent / "live" / tl.s.DATASET         # data\live\<数据集>\：不覆盖 M6 / M7 的正式产出
audience.OUT = plan.OUT = OUT                              # monkeypatch：运行时只换输出目录
res = run(week, scope, src, tx)
try: ollama = requests.get("http://localhost:11434", timeout=3).ok       # 方案卡要用 Ollama 检索策略手册
except requests.RequestException: ollama = False
card = ""
if ollama and res["回答"] and res["回答"]["动作"] != "不行动":
    card = plan.make_plan(res, week, scope).read_text(encoding="utf-8")
print("@@JSON@@" + json.dumps({"res": res, "card": card, "ollama": ollama}, ensure_ascii=False, default=str))
