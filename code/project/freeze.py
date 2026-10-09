# freeze.py —— M7 第 1 步（10-08）：冻结系统 = 记下所有"系统文件"的指纹（md5），跑测试集前核对一遍
# 运行：python code\project\freeze.py        → 生成 data\frozen_<prompt版本>_<harness版本>.json（每个版本冻结一次，已存在就不覆盖；v3_h2 的是 frozen_v3.json）
#       python code\project\freeze.py check  → 核对：冻结后有文件被改过就列出来（M7 跑测试集前自动调用）
import hashlib, json, sys, datetime as dt
from prompt import VERSION as P
from checks import VERSION as H
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
SYSTEM = [f"code/project/{f}" for f in (               # 测试集成绩依赖的全部文件：改任何一个，成绩就不再代表这个冻结版本
    "config.py", "semantic.py", "metrics.yaml",          # 模型名 / 口径
    "tools.py", "tool_spec.py", "pipeline.py",           # 工具 + 代码召回（分数阈值 -1、体量 0.1、数据质量 3 项）
    "prompt.py", "agent.py", "checks.py", "audit.py",    # 模型复核 + 硬控制 + 结论校验
    "plan.py", "audience.py", "experiment.py", "playbook.py", "playbook.yaml",   # 方案卡链路
    "baseline.py")] + ["docs/策略手册.md"]               # 对照组（规则基线）和策略手册也冻结
OUT = ROOT / "data" / ("frozen_v3.json" if H == "h2" else f"frozen_{P}_{H}.json")   # 每个版本一个指纹文件，旧的保留

def fingerprint():
    """每个文件 → md5：内容改了一个字，md5 就会变"""
    return {f: hashlib.md5((ROOT / f).read_bytes()).hexdigest() for f in SYSTEM}

def check():
    """返回冻结后被改过（或被删掉）的文件；空列表 = 和冻结时完全一致"""
    old, new = json.loads(OUT.read_text(encoding="utf-8"))["文件"], fingerprint()
    return [f for f in old if old[f] != new.get(f)]

if __name__ == "__main__":
    if "check" in sys.argv:
        bad = check()
        print("✅ 系统与冻结时一致" if not bad else f"❌ 以下文件冻结后被改过：{bad}")
    elif OUT.exists():
        print(f"已冻结过（{OUT.name}），不覆盖；确需重新冻结：先手动删掉它，并在规格说明书变更记录登记原因")
    else:
        OUT.write_text(json.dumps({"版本": f"{P}_{H}", "时间": dt.datetime.now().isoformat(timespec="seconds"),
                                   "文件": fingerprint()}, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"已冻结 {len(SYSTEM)} 个文件 → {OUT}")
