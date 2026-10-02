import { metric, percent } from "./components.js";
export function renderSummary(snapshot) {
  const summary = snapshot.summary;
  document.querySelector("#summary").innerHTML = [
    metric("Availability", percent(summary.availability), "availability", summary.verdict),
    metric("Objective", percent(summary.objective), "objective"),
    metric("Verdict", summary.verdict, "verdict", summary.verdict),
    metric("Budget consumed", `${summary.budgetConsumed.toFixed(1)}%`, "budget-consumed"),
    metric("Budget remaining", `${summary.budgetRemaining.toFixed(1)}%`, "budget-remaining"),
  ].join("");
}
