-- Reporting queries run against the validated table `clean_invoices`.
-- Each query feeds one summary table in output/.

-- 1. Monthly cost and usage by utility (trend view)
SELECT
    period,
    utility,
    ROUND(SUM(amount_usd), 2)   AS total_cost_usd,
    ROUND(SUM(billed_usage), 1) AS total_usage,
    COUNT(*)                    AS invoice_count,
    -- average per building, so a month with an excluded invoice
    -- does not look like a drop in cost
    ROUND(SUM(amount_usd) / COUNT(*), 2) AS avg_cost_per_building_usd
FROM clean_invoices
GROUP BY period, utility
ORDER BY period, utility;

-- 2. Cost summary by building and utility
SELECT
    building_id,
    building_name,
    utility,
    ROUND(SUM(amount_usd), 2)          AS total_cost_usd,
    ROUND(AVG(amount_usd), 2)          AS avg_monthly_cost_usd,
    ROUND(SUM(amount_usd) / SUM(billed_usage), 4) AS avg_cost_per_unit
FROM clean_invoices
GROUP BY building_id, building_name, utility
ORDER BY total_cost_usd DESC;

-- 3. Fiscal-year comparison (FY runs July to June)
SELECT
    utility,
    CASE WHEN period < '2025-07' THEN 'FY2025' ELSE 'FY2026' END AS fiscal_year,
    ROUND(SUM(amount_usd), 2) AS total_cost_usd
FROM clean_invoices
GROUP BY utility, fiscal_year
ORDER BY utility, fiscal_year;
