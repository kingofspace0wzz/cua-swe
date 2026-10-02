export function renderTotals(snapshot) {
  const totals = snapshot.totals;
  document.querySelector("#totals").innerHTML = `<table><tbody>
    <tr><th>Good events</th><td data-testid="good-total">${totals.good}</td></tr>
    <tr><th>Bad events</th><td data-testid="bad-total">${totals.bad}</td></tr>
    <tr><th>Total events</th><td data-testid="event-total">${totals.total}</td></tr>
    <tr><th>Allowed failures</th><td data-testid="allowed-total">${totals.allowedFailures.toFixed(2)}</td></tr>
  </tbody></table>`;
}
