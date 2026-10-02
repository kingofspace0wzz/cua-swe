# Runtime replay

1. Open `/`; request `REQ-581` shows `Action unavailable`.
2. Expand **Delegation decision trace** and observe
   `delegation.selected_assignment_ref`,
   `delegation.assignments[*].assignment_ref`,
   `delegation.assignments[*].role_ref`, `delegation.roles[*].role_ref`,
   `delegation.roles[*].grant_refs`, `delegation.grant_precedence`,
   `delegation.grants[*].grant_ref`,
   `delegation.grants[*].required_condition_refs`,
   `delegation.grants[*].ui_mode`, `delegation.grants[*].display_label`,
   `delegation.active_condition_refs`, and `delegation.allowed_modes`.
3. Resolve the selected assignment and role, order that role's grants by
   precedence, require every grant condition to be active and its mode to be
   allowed, then render `Approve with note`.
4. `/?scenario=secondary` changes every opaque id. Its precedence-first grant
   has only some required conditions active, so it must be skipped; the next
   valid grant renders `Reject on behalf`.

The pair rejects first-role, first-grant, any-condition, ignored-mode, and
hard-coded-primary repairs.
