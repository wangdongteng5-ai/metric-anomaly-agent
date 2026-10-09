-- make_source.sql —— 演示用（M8，10-09）：把 CJ 改造成"国内电商"风格的源库 data\cj_ecom_src.duckdb
-- 只改表名、列名，并把交易表拆成 订单头 / 订单明细；数据本身一行不变 → 接入后诊断结果应与 CJ 完全一致
ATTACH 'data/cj.duckdb' AS cj (READ_ONLY);
CREATE OR REPLACE TABLE orders AS                              -- 订单头：一行 = 一个订单
SELECT basket_id AS order_id, ANY_VALUE(household_id) AS user_id, ANY_VALUE(store_id) AS shop_id,
       MIN(transaction_timestamp) AS pay_time FROM cj.transactions GROUP BY 1;
CREATE OR REPLACE TABLE order_item AS                          -- 订单明细：一行 = 订单里的一个商品
SELECT basket_id AS order_id, product_id AS sku_id, quantity AS qty, sales_value AS pay_amount,
       retail_disc AS promo_discount, coupon_disc AS coupon_discount, coupon_match_disc AS coupon_match_discount
FROM cj.transactions;
CREATE OR REPLACE TABLE sku AS SELECT product_id AS sku_id, department AS cat1, product_category AS cat2 FROM cj.products;
CREATE OR REPLACE TABLE user_profile AS
SELECT household_id AS user_id, CAST(age AS VARCHAR) AS age_range, CAST(income AS VARCHAR) AS income_range FROM cj.demographics;
CREATE OR REPLACE TABLE mkt_reach AS SELECT campaign_id AS activity_id, household_id AS user_id FROM cj.campaigns;
CREATE OR REPLACE TABLE mkt_activity AS
SELECT campaign_id AS activity_id, CAST(campaign_type AS VARCHAR) AS activity_type, start_date AS begin_date, end_date AS finish_date
FROM cj.campaign_descriptions;
CREATE OR REPLACE TABLE coupon_use AS
SELECT household_id AS user_id, campaign_id AS activity_id, redemption_date AS use_date FROM cj.coupon_redemptions;
DETACH cj;
