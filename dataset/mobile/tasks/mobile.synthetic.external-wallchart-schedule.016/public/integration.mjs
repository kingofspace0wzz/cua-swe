// Complete earlier yard integration, retained by the received-chart import.
// No drawing interpretation belongs to the generic scheduling engine.
const earlier=[
  {
    "id": "strip",
    "name": "Strip fittings",
    "crew": "Earlier yard crew",
    "start": 40,
    "duration": 2,
    "links": []
  },
  {
    "id": "survey",
    "name": "Hull survey",
    "crew": "Earlier yard crew",
    "start": 43,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "strip"
      }
    ]
  },
  {
    "id": "frames",
    "name": "Renew frames",
    "crew": "Earlier yard crew",
    "start": 46,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "survey"
      }
    ]
  },
  {
    "id": "tank",
    "name": "Lift tank",
    "crew": "Earlier yard crew",
    "start": 49,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "frames"
      }
    ]
  },
  {
    "id": "loom",
    "name": "Run loom",
    "crew": "Earlier yard crew",
    "start": 52,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "tank"
      }
    ]
  },
  {
    "id": "planks",
    "name": "Fit planks",
    "crew": "Earlier yard crew",
    "start": 55,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "loom"
      }
    ]
  },
  {
    "id": "deck",
    "name": "Lay deck",
    "crew": "Earlier yard crew",
    "start": 58,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "planks"
      }
    ]
  },
  {
    "id": "mast",
    "name": "Rig mast",
    "crew": "Earlier yard crew",
    "start": 61,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "deck"
      }
    ]
  },
  {
    "id": "hoses",
    "name": "Route hoses",
    "crew": "Earlier yard crew",
    "start": 64,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "mast"
      }
    ]
  },
  {
    "id": "caulk",
    "name": "Caulk seams",
    "crew": "Earlier yard crew",
    "start": 67,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "hoses"
      }
    ]
  },
  {
    "id": "prime",
    "name": "Prime hull",
    "crew": "Earlier yard crew",
    "start": 70,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "caulk"
      }
    ]
  },
  {
    "id": "glaze",
    "name": "Glaze cabin",
    "crew": "Earlier yard crew",
    "start": 73,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "prime"
      }
    ]
  },
  {
    "id": "anodes",
    "name": "Renew anodes",
    "crew": "Earlier yard crew",
    "start": 76,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "glaze"
      }
    ]
  },
  {
    "id": "dock",
    "name": "Dock checks",
    "crew": "Earlier yard crew",
    "start": 79,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "anodes"
      }
    ]
  },
  {
    "id": "trial",
    "name": "Sea trial",
    "crew": "Earlier yard crew",
    "start": 82,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "dock"
      }
    ]
  },
  {
    "id": "spars",
    "name": "Lift spars",
    "crew": "Earlier yard crew",
    "start": 85,
    "duration": 2,
    "links": [
      {
        "type": "FS",
        "lag": 1,
        "from": "trial"
      }
    ]
  }
];
export function load(record) { return structuredClone(earlier); }
