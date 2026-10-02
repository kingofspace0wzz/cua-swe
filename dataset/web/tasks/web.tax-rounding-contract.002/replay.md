# Runtime replay

1. Open `/`; cart `CART-730` shows `Tax unavailable`.
2. Expand **Tax calculation details** and observe
   `tax.lines[*].taxable_minor`, `tax.lines[*].rate_basis_points`,
   `tax.rounding_scope_ref`, `tax.scope_operations[*].scope_ref`,
   `tax.scope_operations[*].operation`, `tax.rounding_increment_minor`,
   `tax.rounding_mode_ref`, `tax.rounding_operations[*].mode_ref`,
   `tax.rounding_operations[*].operation`, `tax.currency_scale`,
   `tax.display_precision`, and `tax.display_pattern`.
3. Primary resolves its opaque scope and mode refs through the operation
   registries, rounds each line to the configured five-minor-unit increment,
   sums, scales, formats, and renders
   `Estimated tax: 0.30 USD`.
4. `/?scenario=secondary` requires aggregate-before-rounding, floor to a
   different increment, scale 1000, three decimals, and a different pattern;
   it renders `Tax due 0.450 credits`.

The registries define all operations used by both scenarios. The pair rejects
aggregate-only, mode-name inference, fixed cents, ignored-increment,
fixed-pattern, and hard-coded-primary repairs.
