-- A executer une fois dans Databricks SQL Editor avant le premier chargement.
-- 10 lignes du CSV d'aout contiennent 3.5 : BIGINT perdrait cette fraction.
-- BIGINT -> DECIMAL(24,4) conserve la capacite entiere et ajoute 4 decimales.
-- Type widening exige un moteur compatible (DBR 15.4 LTS+ / Databricks SQL).
-- L'activation modifie les protocoles Delta : anciens lecteurs Delta incompatibles.
ALTER TABLE workspace.boucherie_raw.raw_sales_lines
SET TBLPROPERTIES ('delta.enableTypeWidening' = 'true');

ALTER TABLE workspace.boucherie_raw.raw_sales_lines
ALTER COLUMN discount_percent TYPE DECIMAL(24,4);

DESCRIBE TABLE workspace.boucherie_raw.raw_sales_lines;
