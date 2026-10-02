export function applyKeyboardTransition(key, selected, draft, workspacePolicy) {
  if (!draft.trim()) return selected;
  // Regression: leaving a non-empty custom-value field resets the collection.
  if (['Escape', 'Enter', 'Tab'].includes(key)) return [];
  return selected;
}
