# simulate_week.py —— M8 h5（10-09）模拟上线：源库先只有截至某周的订单，之后一周一周"到达"（演示用；真实业务里由数据同步任务写入源库）
# 用法：cd D:\ai-agent-learning
#   python code\project\simulate_week.py init 2017-11-27   → 源库 data\cj_live_src.duckdb 只保留到这一周，之后的订单放进"未到达"区
#   python code\project\simulate_week.py add               → 下一周的订单到达
#   每次之后都要重跑：python code\project\connect.py cj_live
import os, sys, duckdb
from pathlib import Path
ROOT = Path(__file__).resolve().parents[2]
WK = "DATE_TRUNC('week', CAST(pay_time AS DATE))"              # 订单所在周（周一）
os.chdir(ROOT)                                                 # make_source.sql 里的相对路径以项目根目录为准
con = duckdb.connect(str(ROOT / "data" / "cj_live_src.duckdb"))

if sys.argv[1] == "init":                                      # 先按 cj_ecom 的改名规则生成完整源库，再把截止周之后的订单移到"未到达"区
    con.execute((ROOT / "datasets" / "cj_ecom" / "make_source.sql").read_text(encoding="utf-8"))
    con.execute(f"CREATE OR REPLACE TABLE incoming_orders AS SELECT * FROM orders WHERE {WK} > DATE '{sys.argv[2]}'")
    con.execute("CREATE OR REPLACE TABLE incoming_order_item AS SELECT * FROM order_item WHERE order_id IN (SELECT order_id FROM incoming_orders)")
    con.execute("DELETE FROM order_item WHERE order_id IN (SELECT order_id FROM incoming_orders)")
    con.execute("DELETE FROM orders WHERE order_id IN (SELECT order_id FROM incoming_orders)")
    print(f"源库已到 {sys.argv[2]} 这周；未到达订单 {con.execute('SELECT COUNT(*) FROM incoming_orders').fetchone()[0]:,} 个")
elif sys.argv[1] == "add":                                     # 未到达区里最早的一周 → 搬进正式表
    nxt = con.execute(f"SELECT MIN({WK}) FROM incoming_orders").fetchone()[0]
    if nxt is None: sys.exit("没有未到达的数据了")
    con.execute(f"CREATE TEMP TABLE batch AS SELECT order_id FROM incoming_orders WHERE {WK} = DATE '{nxt}'")
    for t in ("orders", "order_item"):
        con.execute(f"INSERT INTO {t} SELECT * FROM incoming_{t} WHERE order_id IN (SELECT order_id FROM batch)")
        con.execute(f"DELETE FROM incoming_{t} WHERE order_id IN (SELECT order_id FROM batch)")
    print(f"{str(nxt)[:10]} 这周到达：{con.execute('SELECT COUNT(*) FROM batch').fetchone()[0]:,} 个订单")
