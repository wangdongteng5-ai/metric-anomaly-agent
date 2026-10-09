-- adapter.sql —— 适配层（数据集 cj_ecom，M8 10-09）：把源库的表"翻译"成数据契约规定的 6 张标准表
-- 换一个数据库只需重写本文件：ATTACH 那一行换成公司库（Postgres / MySQL / CSV 的写法以 DuckDB 官方文档为准），下面改列名映射
-- 契约：transactions、products 必须有数据；demographics 和营销 3 张表可以为空，但必须建出来、列名齐全
ATTACH 'data/cj_ecom_src.duckdb' AS src (READ_ONLY);
CREATE OR REPLACE TABLE transactions AS                        -- 一行 = 订单里的一个商品（粒度错了金额会翻倍）
SELECT CAST(o.pay_time AS DATE) AS dt, o.user_id AS household_id, o.order_id AS basket_id, o.shop_id AS store_id,
       i.sku_id AS product_id, i.pay_amount AS sales_value, (i.qty > 0 AND i.pay_amount > 0) AS is_sale,
       i.promo_discount AS retail_disc, i.coupon_discount AS coupon_disc, i.coupon_match_discount AS coupon_match_disc
FROM src.orders o JOIN src.order_item i USING (order_id);
CREATE OR REPLACE TABLE products AS SELECT sku_id AS product_id, cat1 AS department, cat2 AS product_category FROM src.sku;
CREATE OR REPLACE TABLE demographics AS SELECT user_id AS household_id, age_range AS age, income_range AS income FROM src.user_profile;
CREATE OR REPLACE TABLE campaigns AS SELECT activity_id AS campaign_id, user_id AS household_id FROM src.mkt_reach;
CREATE OR REPLACE TABLE campaign_descriptions AS
SELECT activity_id AS campaign_id, activity_type AS campaign_type, begin_date AS start_date, finish_date AS end_date FROM src.mkt_activity;
CREATE OR REPLACE TABLE coupon_redemptions AS
SELECT user_id AS household_id, activity_id AS campaign_id, use_date AS redemption_date FROM src.coupon_use;
DETACH src;
