# app.py —— M8 指标异动诊断 Agent 演示页。回放：读已跑完的评估结果（不用 key）；现场：子进程跑 live.py（要 key，方案卡要 Ollama）
# 8-1 回放｜8-2 现场 + 选数据集｜UI v2（10-09）：选周放到主区 + 两段数据依据（evidence.py）｜v3：默认"诊断一周"只按周选，题目只在"评估回放"里
# 运行：cd D:\ai-agent-learning → streamlit run code\project\app.py
import html, json, os, subprocess, sys
from pathlib import Path
import pandas as pd, streamlit as st, yaml
from dotenv import dotenv_values
import evidence as ev

HERE = Path(__file__).parent; ROOT = HERE.parents[1]; DATA = ROOT / "data"
DIM = {k: v["name"] for k, v in yaml.safe_load(open(HERE / "metrics.yaml", encoding="utf-8"))["dimensions"].items()} | {"camp": "活动", "全部": "整体"}
COLOR = {"用户侧": "#1C6E6A", "商品侧": "#3F5BA9", "数据问题": "#B7791F", "正常波动": "#7A8C87"}
FMT = {"户数": ",.0f", "频次": ".2f", "客单价": ",.2f", "GMV": ",.0f"}
st.set_page_config(page_title="指标异动诊断 Agent", page_icon="📉", layout="wide")
st.markdown("""<style>
.block-container{padding-top:2rem;max-width:1180px}
h1{font-size:1.5rem!important;font-weight:650!important}
h3{font-size:1.1rem!important;font-weight:650!important;margin-top:1.6rem!important;border-top:1px solid #D5DDDA;padding-top:1.2rem!important}
.sub{color:#5E6E6A;font-size:.92rem;margin:-.5rem 0 .8rem}
.verdict{display:grid;grid-template-columns:1fr 2.2fr 1.4fr 1fr;gap:1.5rem;align-items:end;background:#fff;border:1px solid #D5DDDA;
  border-left:8px solid var(--c);border-radius:6px;padding:1.1rem 1.4rem;margin:1rem 0 .5rem}
.verdict small{display:block;color:#5E6E6A;font-size:.8rem;margin-bottom:.25rem}
.verdict b{font-size:1.4rem;font-weight:650;line-height:1.25}.verdict .act b{color:var(--c)}.verdict .meta{color:#5E6E6A;font-size:.85rem;text-align:right}
.check{font-size:.9rem;margin:0 0 .4rem .2rem}.ok{color:#2F7D4F}.bad{color:#B42318}
div[data-testid="stSlider"] label p{font-size:1.05rem;font-weight:600}
blockquote{border-left:3px solid #1C6E6A!important;color:#3B4A47}
@media (max-width:760px){.verdict{grid-template-columns:1fr 1fr}.verdict .meta{text-align:left}}
</style>""", unsafe_allow_html=True)

def nice(x):                                            # main_store_group=腰部 的 户数 → 主力门店=腰部 的 户数
    for k in sorted(DIM, key=len, reverse=True): x = x.replace(f"{k}=", f"{DIM[k]}=")
    return x

def overview(db, src, scope, week, slider=None):
    """主区顶部：全年周 GMV 趋势 + 选中周的三个数。slider = 可选的周列表（现场模式）"""
    df = ev.weekly(db, src, scope, week)
    if slider: week = st.select_slider("选择要诊断的周（周一）", slider, value=week)
    now, wow, vm, med = ev.stats(df, week)
    c1, c2, c3 = st.columns(3)
    c1.metric("本周 GMV", f"{now:,.0f}"); c2.metric("环比上周", f"{wow:+.1%}"); c3.metric("比前 4 周中位数", f"{vm:+.1%}")
    st.altair_chart(ev.trend(df, week, height=200), width="stretch")
    return week

def verdict(a, truth, sec):
    e, kind, act = html.escape, a.get("结论类型", "未完成"), a.get("动作", "—")
    st.markdown(f"""<div class="verdict" style="--c:{COLOR.get(kind, '#B42318')}"><div><small>结论</small><b>{e(kind)}</b></div>
      <div><small>主因</small><b>{e(nice(str(a.get('主因', '—'))))}</b></div><div class="act"><small>建议动作</small><b>{e(act)}</b></div>
      <div class="meta">{a.get('判定', '模型')}判定{f'<br>{sec} 秒' if sec is not None else ''}</div></div>""", unsafe_allow_html=True)
    if truth:                                           # 只有埋过异常的题才有答案可对
        ok = act == truth[1]
        st.markdown(f'<p class="check {"ok" if ok else "bad"}">{"✓ 与答案一致" if ok else "✗ 与答案不一致"}：答案是 {e(truth[0])} → {e(truth[1])}</p>', unsafe_allow_html=True)

def why_cause(a, trace, db, src, scope, week):
    st.subheader("为什么是这个结论")
    ctx = next((json.loads(x["结果"]) for x in trace if x["工具"] == "候选清单"), None)
    if not ctx: st.info("由代码直接判定（数据质量 / 节假日 / 没有候选），没有进入模型复核。证据：" + "；".join(map(str, a.get("证据", [])))); return
    c1, c2 = st.columns(2)
    c1.markdown("**GMV 变化拆成三个因子**"); c1.caption(f"户数 × 频次 × 客单价：三项相加 = GMV 变化额 {ctx['范围GMV变化额']:,.2f}")
    c1.altair_chart(ev.bars(pd.DataFrame(ctx["整体拆解"]), "因子", "贡献额"), width="stretch")
    if cause := ev.cause_of(a.get("主因")):
        df = ev.weekly(db, src, scope, week, cause[2], cause); now, wow, vm, med = ev.stats(df, week)
        c2.markdown(f"**主因分组：{html.escape(nice(a['主因']))}，近 16 周**")
        c2.caption(f"本周 {now:{FMT[cause[2]]}}｜环比 {wow:+.1%}｜比前 4 周中位数（虚线）{vm:+.1%}")
        c2.altair_chart(ev.trend(df, week, FMT[cause[2]], last=16, median=med), width="stretch")
    with st.expander(f"代码召回的全部 {ctx['候选数']} 个候选，以及模型逐条复核"):
        df = pd.DataFrame(ctx["候选"]).assign(维度=lambda d: d.维度.map(lambda k: DIM.get(k, k)))
        df["体量占比"] = df["体量占比"].map(lambda v: f"{v:.2f}" if isinstance(v, (int, float)) else "—")
        red = lambda v: "color:#B42318;font-weight:600" if isinstance(v, float) and v < -1 else ""
        st.caption("异常分数 < -1（红色）即进入候选；体量占比 = 该组 GMV 变化 ÷ 整体变化")
        st.dataframe(df[["维度", "分组", "指标", "异常分数", "中位数异常分数", "环比", "vs前4周中位数", "体量占比"]].style
                     .map(red, subset=["异常分数", "中位数异常分数"]).format({"环比": "{:+.1%}", "vs前4周中位数": "{:+.1%}",
                     "异常分数": "{:.2f}", "中位数异常分数": "{:.2f}"}, na_rep="—"), hide_index=True, width="stretch")
        if a.get("候选复核"):
            rv = pd.DataFrame(a["候选复核"]).assign(候选=lambda d: d.候选.map(nice))
            st.dataframe(rv[[c for c in ("候选", "判断", "理由") if c in rv]], hide_index=True, width="stretch")

def why_plan(card, nocard):
    st.subheader("为什么是这个方案")
    mat = ev.material(card)
    if not mat: st.info(nocard); return
    for x in mat.get("策略手册", [])[:1]:              # 手册里的"适用"和"注意"：动作为什么对得上主因
        st.markdown("\n".join("> " + l.lstrip("- ") for l in x.splitlines() if l.startswith(("- 适用", "- 注意"))))
    a, e, c1, c2 = mat.get("名单", {}), mat.get("实验"), *st.columns(2)
    if "最终人数" in a:
        c1.markdown(f"**名单：{a['最终人数']} 户**"); c1.caption(f"权益：{a['权益']}｜成本 {a['成本区间'][0]}～{a['成本区间'][1]} 美元")
        c1.altair_chart(ev.bars(pd.DataFrame({"步骤": ["圈人", "排除疲劳户", "排除频控满", "最终名单"],
                        "户数": [a["圈人"], -a["排除疲劳"], -a["排除频控"], a["最终人数"]]}), "步骤", "户数"), width="stretch")
    if e:
        c2.markdown(f"**对照组：{e['对照组比例']:.0%}，要累计几周才测得出效果**")
        c2.caption(f"不发券也会自己回来的比例 {e['自然回流率(历史8周)']:.1%}，所以必须留对照组；对照越多、周数越少")
        c2.altair_chart(ev.bars(pd.DataFrame(e["方案"]).assign(对照=lambda d: d.对照组比例.map("对照 {:.0%}".format),
                        周数=lambda d: d["要累计几周(测6.5pp)"]), "对照", "周数", "d"), width="stretch")   # 列名带括号 Altair 会误读，先改名
    if mat.get("问题商品"):
        c1.markdown("**跌得最多的商品（GMV 贡献额）**")
        c1.altair_chart(ev.bars(pd.DataFrame(mat["问题商品"][:8]), "分组", "GMV贡献额", height=220), width="stretch")
    with st.expander("方案卡全文"): st.markdown(card.partition("## 材料（代码计算）")[0])

def show(a, trace, card, db, src, scope, week, truth=None, sec=None, nocard=""):
    verdict(a or {}, truth, sec); why_cause(a or {}, trace, db, src, scope, week)
    if (a or {}).get("动作") != "不行动": why_plan(card, nocard)   # 正常波动不需要方案
    with st.expander("调用记录（轮 0 = 代码执行；轮 ≥ 1 = 模型复核时追加的查询）"):
        for x in trace: st.markdown(f"`轮 {x['轮']}` **{x['工具']}** `{json.dumps(x['参数'], ensure_ascii=False)}`")

mode = st.sidebar.radio("模式", ["诊断一周", "评估回放"], help="诊断一周：自己选数据集和周，当场诊断。评估回放：看测试集 / 开发集已跑完的结果")
if mode == "诊断一周":                                   # ===== 自选周：只用原始数据，不出现"题"；埋异常的题只在评估回放里看 =====
    sets = ["cj"] + sorted(p.parent.name for p in (ROOT / "datasets").glob("*/adapter.sql") if (DATA / f"{p.parent.name}.duckdb").exists())
    ds = st.sidebar.selectbox("数据集", sets, help="cj = 原始数据；其他是用 connect.py 接入的库")
    db, T = DATA / f"{ds}.duckdb", yaml.safe_load(open((HERE if ds == "cj" else ROOT / "datasets" / ds) / "metrics.yaml", encoding="utf-8"))["time"]
    weeks = [str(d.date()) for d in pd.date_range(T["valid_from"], T["valid_to"], freq="7D")][1:]
    st.title("选一周，看 GMV 为什么变了、该怎么办")
    week = overview(db, "fact", "全部", "2017-07-24" if "2017-07-24" in weeks else weeks[-1], weeks)
    has_key = bool(dotenv_values(ROOT / ".env").get("OPENROUTER_API_KEY"))
    key = (ds, week)
    if st.button(f"诊断 {week} 这周", type="primary", disabled=not has_key, help=None if has_key else ".env 里没有 OPENROUTER_API_KEY，只能看评估回放"):
        with st.spinner("代码召回 → 模型复核 → 写方案卡（交给模型的周约 40～90 秒）"):
            t0 = pd.Timestamp.now()
            p = subprocess.run([sys.executable, str(HERE / "live.py"), ds, week], capture_output=True,
                               text=True, encoding="utf-8", env={**os.environ, "PYTHONIOENCODING": "utf-8"})
        if "@@JSON@@" not in p.stdout: st.error("运行失败，报错的最后部分："); st.code(p.stderr[-3000:]); st.stop()
        st.session_state[key] = (json.loads(p.stdout.split("@@JSON@@")[-1]), round((pd.Timestamp.now() - t0).total_seconds()))
    if key in st.session_state:                         # 结果存在会话里：展开折叠区、切换后再回来都不会丢
        out, sec = st.session_state[key]
        show(out["res"]["回答"], out["res"]["trace"], out["card"], db, "fact", "全部", week, None, sec,
             "没有方案卡：结论是\"不行动\"，或运行时没开 Ollama")
    st.stop()

@st.cache_data                                          # ===== 回放：同一个结果文件只读一次 =====
def load(name):
    res = pd.read_csv(DATA / name, encoding="utf-8-sig").fillna("").set_index("场景ID")
    mf = pd.read_csv(DATA / ("manifest_test.csv" if name.startswith("eval_test_") else "manifest.csv"), dtype=str, encoding="utf-8-sig").fillna("").set_index("场景ID")
    tr = DATA / name.replace(".csv", "_trace.jsonl")
    return res, mf, {x["场景ID"]: x for x in map(json.loads, tr.read_text(encoding="utf-8").splitlines())} if tr.exists() else {}

files = sorted(p.name for p in DATA.glob("eval_*.csv"))
name = st.sidebar.selectbox("结果文件", files, index=files.index("eval_test_promptv3_h2.csv"), help="默认是 v3 测试集正式成绩")
res, mf, trace = load(name)
c = res[res.index.str.startswith("C")]
k1, k2 = st.sidebar.columns(2)
k1.metric("动作对", f"{res.动作对.sum()}/{len(res)}", help=f"{res.动作对.mean():.0%}")
k2.metric("对照周误报", f"{(c['判·主因'] != '正常波动').sum()}/{len(c)}", help="没有埋异常的周，被判成有问题的次数")
sid = st.sidebar.selectbox("题目", res.index, format_func=lambda i: f"{i}  {'✓' if res.动作对[i] else '✗'}")
r, m, t = res.loc[sid], mf.loc[sid], trace.get(sid, {})
src, tx = f"fact_{sid}", (f"tx_{sid}" if m.手法 == "金额置0" else "transactions")
st.title(f"{m.周} 这周 GMV 为什么变了？该怎么办？")
st.markdown(f'<p class="sub">题目 {sid}｜提问范围 {html.escape(nice(m.提问范围))}</p>', unsafe_allow_html=True)
overview(DATA / "cj.duckdb", src, m.提问范围, m.周)
cards = sorted((DATA / "plans").glob(f"*_{sid}_*.md"))
show(t.get("回答") or {"结论类型": r["判·主因"], "主因": r["判·定位"], "动作": r["判·动作"], "判定": r.判定}, t.get("trace", []),
     cards[0].read_text(encoding="utf-8") if cards else "", DATA / "cj.duckdb", src, m.提问范围, m.周, (r["真·主因"], r["真·动作"]), r.秒,
     "这道题评估时没有生成方案卡（M6 / M7 只对部分题跑过 plan.py）")
