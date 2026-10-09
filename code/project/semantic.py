# semantic.py —— 语义层：读 metrics.yaml → 建 fact 视图 → 按「指标 + 周 + 维度」拼 SQL
# 安装：python -m pip install pyyaml -i https://pypi.tuna.tsinghua.edu.cn/simple
# 运行：python code\project\semantic.py（先跑过 data_prep.py；会在 cj.duckdb 里建 fact 视图）
# 改动记录：M3 6-1（10-07）加主力门店 CTE（ms）；compile_sql 的表名改为读 yaml 的 source，可传 src 覆盖｜M8（10-09）按 DATASET 选库和 yaml
import os
from pathlib import Path
import duckdb, yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]
load_dotenv(ROOT / ".env")                                     # M8（10-09）：.env 里写 DATASET=xxx 切换数据集
DATASET = os.getenv("DATASET", "cj")                           # 默认 cj：路径与 v4 完全相同
HERE = Path(__file__).parent if DATASET == "cj" else ROOT / "datasets" / DATASET   # 该数据集的 metrics.yaml（+ adapter.sql）
SEM = yaml.safe_load(open(HERE / "metrics.yaml", encoding="utf-8"))
DB = ROOT / "data" / f"{DATASET}.duckdb"

def build_fact(con):
    """建 fact 视图：有效销售行 + 自然周 + 各维度列（维度规则全部来自 metrics.yaml）"""
    t = SEM["time"]
    dims = ",\n  ".join(f"{d['sql']} AS {k}" for k, d in SEM["dimensions"].items() if d["sql"])
    sg = SEM["dimensions"]["store_group"]["sql"]               # 复用门店分组规则，不写第二份
    con.execute(f"""CREATE OR REPLACE VIEW {SEM['source']} AS
WITH t AS (SELECT *, DATE_TRUNC('week', dt) AS wk FROM transactions WHERE is_sale),
     sr AS (SELECT store_id, ROW_NUMBER() OVER (ORDER BY SUM(sales_value) DESC) r FROM t GROUP BY 1),
     fw AS (SELECT household_id, MIN(wk) first_wk FROM t GROUP BY 1),
     hs AS (SELECT household_id, {sg} AS grp, SUM(sales_value) AS v
            FROM t JOIN sr USING (store_id) GROUP BY 1, 2),
     ms AS (SELECT household_id, grp AS main_group FROM hs
            QUALIFY ROW_NUMBER() OVER (PARTITION BY household_id ORDER BY v DESC, grp) = 1)
SELECT t.*, (t.wk = fw.first_wk) AS is_new,
  {dims}
FROM t JOIN sr USING (store_id) JOIN fw USING (household_id) JOIN ms USING (household_id)
LEFT JOIN products p USING (product_id) LEFT JOIN demographics d USING (household_id)
WHERE t.wk BETWEEN DATE '{t['valid_from']}' AND DATE '{t['valid_to']}'""")

def compile_sql(metric, week, by=None, src=None):
    """指标名 + 周（周一日期）+ 可选维度 → SQL。src 默认读 yaml 的 source（M3 注入后可传 fact_S01 等）"""
    m = SEM["metrics"].get(metric)
    if m is None or m["sql"] is None:
        raise ValueError(f"不支持的指标：{metric}，可选：{[k for k, v in SEM['metrics'].items() if v['sql']]}")
    d = SEM["dimensions"].get(by) if by else None
    if by and (d is None or d["sql"] is None):
        raise ValueError(f"不支持的维度：{by}，可选：{[k for k, v in SEM['dimensions'].items() if v['sql']]}")
    if d and week < d.get("valid_from", week):                 # 例：新老客 2017-02-06 前不可用
        raise ValueError(f"维度 {by} 从 {d['valid_from']} 起才可用")
    sel, grp = (f"{by}, ", f" AND {by} IS NOT NULL GROUP BY {by} ORDER BY 2 DESC") if by else ("", "")
    return f"SELECT {sel}{m['sql']} AS {metric} FROM {src or SEM['source']} WHERE wk = DATE '{week}'{grp}"

if __name__ == "__main__":                                     # 自测：建视图 + 查例子
    con = duckdb.connect(str(DB))
    build_fact(con)
    print("fact 视图周数：", con.execute("SELECT COUNT(DISTINCT wk) FROM fact").fetchone()[0])
    print("\n全年按主力门店：\n", con.execute("""SELECT main_store_group, COUNT(DISTINCT household_id) 户数,
        ROUND(SUM(sales_value) / (SELECT SUM(sales_value) FROM fact) * 100, 1) GMV占比
        FROM fact GROUP BY 1 ORDER BY 3 DESC""").df())
    for args in [("gmv", "2017-07-24", "main_store_group"), ("gmv", "2017-07-24", "store_group")]:
        sql = compile_sql(*args)
        print(f"\n{args}\nSQL：{sql}\n{con.execute(sql).df()}")
    for bad in [("dau", "2017-06-05"), ("gmv", "2017-01-09", "customer_type")]:
        try: compile_sql(*bad)
        except ValueError as e: print("\n拦截：", e)
