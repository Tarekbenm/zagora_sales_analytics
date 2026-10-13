select
    cast(product_code as {{ dbt.type_string() }}) as product_code,
    product_label_clean,
    product_category,
    meat_type,
    classification_status
from {{ ref('product_reference') }}