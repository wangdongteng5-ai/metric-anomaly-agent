# view_demo.py —— 看清"视图"在数据库里到底是什么（只读）
# 运行：python code\project\view_demo.py（先跑过 semantic.py）
from pathlib import Path
import duckdb, pandas as pd
pd.set_option("display.unicode.east_asian_width", True); pd.set_option("display.width", 200); pd.set_option("display.max_columns", 20)

con = duckdb.connect(str(Path(__file__).resolve().parents[2] / "data" / "cj.duckdb"), read_only=True)

print("① 数据库里有什么：表（TABLE）和视图（VIEW）")
print(con.execute("SELECT table_name 名字, table_type 类型 FROM information_schema.tables ORDER BY 2, 1").df())

print("\n② 视图 fact 在数据库里存的东西 —— 只是一段 SQL 文本：")
sql = con.execute("SELECT sql FROM duckdb_views() WHERE view_name = 'fact'").fetchone()[0]
print(sql[:400], "……（共", len(sql), "个字符）")

print("\n③ 同一笔交易：原始表 transactions 里长这样")
print(con.execute("SELECT household_id, store_id, product_id, sales_value, dt FROM transactions WHERE is_sale AND household_id = '580' AND dt = DATE '2017-06-05' LIMIT 3").df())

print("\n④ 查视图 fact 时，数据库现场跑上面那段 SQL，多出了这些列")
print(con.execute("SELECT household_id, store_id, sales_value, wk, store_group, department, age_band, is_new FROM fact WHERE household_id = '580' AND dt = DATE '2017-06-05' LIMIT 3").df())
