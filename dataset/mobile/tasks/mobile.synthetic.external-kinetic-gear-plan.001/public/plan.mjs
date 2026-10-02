// Product integration: immediate driving relation for each component.
// This is an ordinary client integration table, not a solver API.
export const connections = [
  {
    "from": "W01",
    "to": "W02",
    "kind": "mesh"
  },
  {
    "from": "W02",
    "to": "W04",
    "kind": "axis"
  },
  {
    "from": "W04",
    "to": "W03",
    "kind": "mesh"
  },
  {
    "from": "W03",
    "to": "W05",
    "kind": "mesh"
  },
  {
    "from": "W05",
    "to": "W07",
    "kind": "mesh"
  },
  {
    "from": "W07",
    "to": "W08",
    "kind": "mesh"
  },
  {
    "from": "W08",
    "to": "W06",
    "kind": "axis"
  },
  {
    "from": "W06",
    "to": "W09",
    "kind": "open belt"
  },
  {
    "from": "W09",
    "to": "W11",
    "kind": "axis"
  },
  {
    "from": "W11",
    "to": "W10",
    "kind": "mesh"
  },
  {
    "from": "W10",
    "to": "W12",
    "kind": "mesh"
  },
  {
    "from": "W08",
    "to": "W13",
    "kind": "mesh"
  },
  {
    "from": "W13",
    "to": "W15",
    "kind": "axis"
  },
  {
    "from": "W15",
    "to": "W14",
    "kind": "mesh"
  },
  {
    "from": "W14",
    "to": "W17",
    "kind": "mesh"
  },
  {
    "from": "W17",
    "to": "W16",
    "kind": "mesh"
  },
  {
    "from": "W06",
    "to": "W18",
    "kind": "crossed belt"
  },
  {
    "from": "W18",
    "to": "W20",
    "kind": "axis"
  },
  {
    "from": "W20",
    "to": "W19",
    "kind": "mesh"
  },
  {
    "from": "W19",
    "to": "W21",
    "kind": "mesh"
  },
  {
    "from": "W08",
    "to": "W22",
    "kind": "mesh"
  },
  {
    "from": "W22",
    "to": "W24",
    "kind": "axis"
  },
  {
    "from": "W24",
    "to": "W23",
    "kind": "mesh"
  }
];
export function connectionsFor(edition) { return connections; }
