# data_prep.py —— M1：下载 Complete Journey（84.51°，CC0）→ 写入 DuckDB（data\cj.duckdb）
# 安装：python -m pip install pyreadr duckdb requests -i https://pypi.tuna.tsinghua.edu.cn/simple
# 运行：python code\project\data_prep.py（首次下载约 15 MB，需开着 Clash）
from pathlib import Path
import duckdb, pyreadr, requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[2]                     # D:\ai-agent-learning
RAW = ROOT / "data" / "raw"
RAW.mkdir(parents=True, exist_ok=True)
load_dotenv(ROOT / ".env")                                     # requests 会自动读 HTTPS_PROXY
URL = "https://github.com/bradleyboehmke/completejourney/raw/master/data/{}"
FILES = ["transactions.rds", "demographics.rda", "products.rda", "campaigns.rda",
         "campaign_descriptions.rda", "coupons.rda", "coupon_redemptions.rda"]

# 1. 下载（已存在就跳过）
for f in FILES:
    p = RAW / f
    if not p.exists():
        r = requests.get(URL.format(f), timeout=180)
        r.raise_for_status()
        p.write_bytes(r.content)
        print(f"已下载 {f}（{len(r.content) // 1024} KB）")

# 2. R 格式文件 → pandas → DuckDB，一个文件一张表
con = duckdb.connect(str(ROOT / "data" / "cj.duckdb"))
for f in FILES:
    df = list(pyreadr.read_r(str(RAW / f)).values())[0]       # 每个文件里只有一张表
    for c in df.select_dtypes("datetime").columns:             # 时间统一成纳秒精度，DuckDB 才认
        df[c] = df[c].astype("datetime64[ns]")
    name = f.split(".")[0]
    con.execute(f"CREATE OR REPLACE TABLE {name} AS SELECT * FROM df")
    print(f"{name}: {len(df):,} 行")

# 3. 交易表加两列：日期、是否有效销售（只打标记，不删除）
con.execute("""CREATE OR REPLACE TABLE transactions AS SELECT *,
    CAST(transaction_timestamp AS DATE) AS dt,
    (quantity > 0 AND sales_value > 0) AS is_sale
    FROM transactions""")
con.close()
print("已写入 data\\cj.duckdb")
