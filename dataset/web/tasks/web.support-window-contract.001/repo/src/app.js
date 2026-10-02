const root = document.querySelector("#root");

function formatWindow(value, timeZone) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Window unavailable";
  const formatted = new Intl.DateTimeFormat("en-US", {
    month: "short", day: "numeric", year: "numeric",
    hour: "numeric", minute: "2-digit", hour12: true, timeZone,
  }).format(date);
  return `${formatted} (${timeZone})`;
}

async function render() {
  const response = await fetch(`/api/support-window${window.location.search}`);
  const data = await response.json();

  // The legacy service returned a ready-to-render UTC window.
  const windowStart = data.window_start;
  const timeZone = "UTC";

  root.innerHTML = `
    <main class="shell"><section class="card">
      <p class="eyebrow">Support scheduling</p>
      <h1>Case ${data.case_ref ?? "unknown"}</h1>
      <div class="total-row"><span>Selected window</span><strong id="support-window">${formatWindow(windowStart, timeZone)}</strong></div>
      <nav aria-label="Support view">
        <button id="overview-tab" type="button" aria-selected="true">Overview</button>
        <button id="details-tab" type="button" aria-selected="false">Schedule details</button>
      </nav>
      <section id="details" class="diagnostics" hidden>
        <h2>Live /api/support-window response</h2><pre>${JSON.stringify(data, null, 2)}</pre>
      </section>
    </section></main>`;

  const detailsTab = document.querySelector("#details-tab");
  const overviewTab = document.querySelector("#overview-tab");
  const details = document.querySelector("#details");
  detailsTab.addEventListener("click", () => {
    details.hidden = false; detailsTab.setAttribute("aria-selected", "true"); overviewTab.setAttribute("aria-selected", "false");
  });
  overviewTab.addEventListener("click", () => {
    details.hidden = true; detailsTab.setAttribute("aria-selected", "false"); overviewTab.setAttribute("aria-selected", "true");
  });
}

render().catch((error) => { root.textContent = `Unable to load schedule: ${error.message}`; });

