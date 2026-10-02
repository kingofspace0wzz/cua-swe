export function buildExportRequest(scope, activeFilters, workspacePolicy) {
  const input = { scope, exportInfo: { fields: ['NAME', 'SKU'] } };
  if (scope === 'CURRENT_SEARCH') {
    // Regression: the selected search scope is never attached to the request.
    return input;
  }
  return input;
}
