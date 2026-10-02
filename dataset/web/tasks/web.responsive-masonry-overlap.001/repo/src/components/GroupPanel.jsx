import { useState } from "react";

function LampsContent() {
  const [enabled, setEnabled] = useState(true);

  return (
    <div className="lamp-control">
      <span>Lounge lamp: {enabled ? "On" : "Off"}</span>
      <button
        type="button"
        aria-label={`Turn lounge lamp ${enabled ? "off" : "on"}`}
        onClick={() => setEnabled((value) => !value)}
      >
        {enabled ? "Turn off" : "Turn on"}
      </button>
    </div>
  );
}

function FreezerContent() {
  const [running, setRunning] = useState(true);
  const [target, setTarget] = useState(-18);

  return (
    <>
      <div className="mode-row">
        <span>
          Mode: <strong>{running ? "Run" : "Standby"}</strong>
        </span>
        <button type="button" onClick={() => setRunning((value) => !value)}>
          {running ? "Pause" : "Resume"}
        </button>
      </div>
      <div className="temperature-card" data-testid="temperature-card">
        <span>Temperature</span>
        <strong data-testid="temperature-target">{target}°C target</strong>
        <button
          type="button"
          aria-label="Raise target temperature"
          onClick={() => setTarget((value) => value + 1)}
        >
          Raise 1°
        </button>
      </div>
    </>
  );
}

function SystemContent() {
  const [acknowledged, setAcknowledged] = useState(false);

  return (
    <>
      <div className="system-status">
        <span>Grid voltage</span>
        <strong>229 V</strong>
      </div>
      <div className="chart-surface" aria-label="Voltage history chart">
        <span>Voltage history</span>
        <div className="chart-line" />
      </div>
      <button
        type="button"
        className="system-action"
        onClick={() => setAcknowledged((value) => !value)}
      >
        {acknowledged ? "Alert acknowledged" : "Acknowledge alert"}
      </button>
    </>
  );
}

function GroupContent({ kind }) {
  if (kind === "lamps") {
    return <LampsContent />;
  }
  if (kind === "freezer") {
    return <FreezerContent />;
  }
  return <SystemContent />;
}

export function applyGroupPanelLayout(container, layout) {
  for (const group of layout.groups) {
    group.element.style.left = `${group.left}px`;
    group.element.style.top = `${group.top}px`;
    group.element.style.width = `${group.width}px`;
    group.element.classList.add("is-positioned");
  }
  container.style.minHeight = `${layout.minHeight}px`;
  container.dataset.layoutRevision = String(
    Number(container.dataset.layoutRevision || 0) + 1
  );
  container.dataset.layoutReady = "true";
}

export default function GroupPanel({ group }) {
  return (
    <section
      className="group-panel"
      data-dashboard-group
      data-group-id={group.id}
      style={{ height: `${group.height}px` }}
      aria-labelledby={`${group.id}-heading`}
    >
      <h2 id={`${group.id}-heading`}>{group.title}</h2>
      <GroupContent kind={group.kind} />
    </section>
  );
}
