// Shared performance integration. Timing, artwork and editions arrive separately.
const performance = {
  "raise": [
    {
      "cel": "rest",
      "facing": "right"
    },
    {
      "cel": "cradle",
      "facing": "right"
    },
    {
      "cel": "lift-mid",
      "facing": "right"
    },
    {
      "cel": "offer",
      "facing": "right"
    },
    {
      "cel": "hat-touch",
      "facing": "right"
    },
    {
      "cel": "salute",
      "facing": "right"
    },
    {
      "cel": "settle",
      "facing": "right"
    }
  ],
  "cross": [
    {
      "cel": "rest",
      "facing": "right"
    },
    {
      "cel": "stride",
      "facing": "right"
    },
    {
      "cel": "cross-step",
      "facing": "right"
    },
    {
      "cel": "toe-up",
      "facing": "right"
    },
    {
      "cel": "balance",
      "facing": "right"
    },
    {
      "cel": "exit-step",
      "facing": "right"
    },
    {
      "cel": "settle",
      "facing": "right"
    }
  ],
  "catch": [
    {
      "cel": "reach-low",
      "facing": "right"
    },
    {
      "cel": "kneel",
      "facing": "right"
    },
    {
      "cel": "scoop",
      "facing": "right"
    },
    {
      "cel": "catch-chest",
      "facing": "right"
    },
    {
      "cel": "catch-high",
      "facing": "right"
    },
    {
      "cel": "balance",
      "facing": "right"
    },
    {
      "cel": "cradle",
      "facing": "right"
    }
  ],
  "greet": [
    {
      "cel": "hat-touch",
      "facing": "right"
    },
    {
      "cel": "bow-start",
      "facing": "right"
    },
    {
      "cel": "bow-deep",
      "facing": "right"
    },
    {
      "cel": "wave-low",
      "facing": "right"
    },
    {
      "cel": "wave-wide",
      "facing": "right"
    },
    {
      "cel": "wave-high",
      "facing": "right"
    },
    {
      "cel": "rest",
      "facing": "right"
    }
  ]
};
export function poseFor(edition,clip,beat){ return performance[clip][beat]; }
