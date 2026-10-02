import { useLayoutEffect, useRef } from "react";

import GroupPanel, { applyGroupPanelLayout } from "./components/GroupPanel.jsx";
import { DASHBOARD_GROUPS } from "./dashboard/config.js";
import { measureDashboardGroups } from "./layout/group-measurement.js";
import { calculateGroupPlacement } from "./layout/placement.js";
import { createResizeScheduler } from "./layout/resize-scheduler.js";
import { availableLayoutWidth } from "./layout/size-service.js";

export default function App() {
  const dashboardRef = useRef(null);

  useLayoutEffect(() => {
    const dashboard = dashboardRef.current;
    if (!dashboard) {
      return undefined;
    }

    const runLayout = () => {
      const groups = measureDashboardGroups(dashboard, DASHBOARD_GROUPS);
      const layout = calculateGroupPlacement(
        groups,
        availableLayoutWidth(dashboard)
      );
      applyGroupPanelLayout(dashboard, layout);
    };

    const scheduler = createResizeScheduler(runLayout, dashboard);
    scheduler.start();
    return () => scheduler.destroy();
  }, []);

  return (
    <>
      <header className="dashboard-header">
        <div>
          <p className="eyebrow">North plant · live operations</p>
          <h1>System dashboard</h1>
        </div>
        <div className="sync-state" aria-label="Data connection status">
          <span className="sync-dot" />
          Connected
        </div>
      </header>
      <main
        ref={dashboardRef}
        className="dashboard-grid"
        aria-label="Operations groups"
      >
        {DASHBOARD_GROUPS.map((group) => (
          <GroupPanel key={group.id} group={group} />
        ))}
      </main>
    </>
  );
}
