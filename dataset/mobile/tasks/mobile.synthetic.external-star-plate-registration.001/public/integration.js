// Registration cache from the earlier field import. Kept as complete product state.
// Provider edition slots are reused when the observer replaces the two field sheets.
// The received-plate integration currently returns this earlier cache unchanged.
const registrations = {
  "juniper": {
    "pose": {
      "turn": 0,
      "mirror": false,
      "scale": 1,
      "dx": 0,
      "dy": 0
    },
    "stars": [
      {
        "name": "Adair",
        "x": 70,
        "y": 80,
        "plate": "P03"
      },
      {
        "name": "Beryl",
        "x": 200,
        "y": 100,
        "plate": "P04"
      },
      {
        "name": "Corda",
        "x": 330,
        "y": 60,
        "plate": "P01"
      },
      {
        "name": "Dunlin",
        "x": 505,
        "y": 75,
        "plate": "P02"
      },
      {
        "name": "Esker",
        "x": 90,
        "y": 205,
        "plate": "P07"
      },
      {
        "name": "Flint",
        "x": 245,
        "y": 195,
        "plate": "P06"
      },
      {
        "name": "Gable",
        "x": 405,
        "y": 190,
        "plate": "P05"
      },
      {
        "name": "Hedra",
        "x": 530,
        "y": 230,
        "plate": "P08"
      },
      {
        "name": "Islet",
        "x": 60,
        "y": 325,
        "plate": "P10"
      },
      {
        "name": "Jewel",
        "x": 225,
        "y": 345,
        "plate": "P11"
      },
      {
        "name": "Kora",
        "x": 375,
        "y": 315,
        "plate": "P09"
      },
      {
        "name": "Larch",
        "x": 515,
        "y": 375,
        "plate": "P12"
      },
      {
        "name": "Mora",
        "x": 100,
        "y": 485,
        "plate": "P13"
      },
      {
        "name": "Nim",
        "x": 255,
        "y": 535,
        "plate": "P16"
      },
      {
        "name": "Oaker",
        "x": 390,
        "y": 495,
        "plate": "P14"
      },
      {
        "name": "Pipit",
        "x": 550,
        "y": 520,
        "plate": "P15"
      }
    ]
  },
  "heather": {
    "pose": {
      "turn": 0,
      "mirror": false,
      "scale": 1,
      "dx": 0,
      "dy": 0
    },
    "stars": [
      {
        "name": "Aspen",
        "x": 60,
        "y": 90,
        "plate": "P03"
      },
      {
        "name": "Baylet",
        "x": 190,
        "y": 65,
        "plate": "P02"
      },
      {
        "name": "Clove",
        "x": 365,
        "y": 105,
        "plate": "P04"
      },
      {
        "name": "Dell",
        "x": 490,
        "y": 60,
        "plate": "P01"
      },
      {
        "name": "Erne",
        "x": 85,
        "y": 210,
        "plate": "P07"
      },
      {
        "name": "Fable",
        "x": 265,
        "y": 175,
        "plate": "P05"
      },
      {
        "name": "Gale",
        "x": 440,
        "y": 235,
        "plate": "P08"
      },
      {
        "name": "Holt",
        "x": 535,
        "y": 190,
        "plate": "P06"
      },
      {
        "name": "Iris",
        "x": 100,
        "y": 370,
        "plate": "P11"
      },
      {
        "name": "Juno",
        "x": 215,
        "y": 325,
        "plate": "P09"
      },
      {
        "name": "Kite",
        "x": 370,
        "y": 350,
        "plate": "P10"
      },
      {
        "name": "Loam",
        "x": 525,
        "y": 370,
        "plate": "P12"
      },
      {
        "name": "Moss",
        "x": 55,
        "y": 520,
        "plate": "P15"
      },
      {
        "name": "Nell",
        "x": 235,
        "y": 505,
        "plate": "P13"
      },
      {
        "name": "Opal",
        "x": 415,
        "y": 530,
        "plate": "P16"
      },
      {
        "name": "Plover",
        "x": 545,
        "y": 505,
        "plate": "P14"
      }
    ]
  }
};
export function registrationFor(id, points) {
  if (!registrations[id]) throw Error("This edition has no registration.");
  return registrations[id];
}
