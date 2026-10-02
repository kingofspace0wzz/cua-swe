export const SLO_ROLLUPS = Object.freeze({
  availability: { mode: "mean_of_slices" },
  budget: { mode: "mean_of_slices" },
});

export const ROLLUP_SCHEDULE = Object.freeze([
  Object.freeze({
    epoch: "rev-2411",
    windows: Object.freeze({
      standing: { availability: { mode: "pooled_events" }, budget: { mode: "pooled_events" } },
      review: { availability: { mode: "pooled_events" }, budget: { mode: "pooled_events" } },
    }),
  }),
  Object.freeze({
    epoch: "rev-2503",
    windows: Object.freeze({
      standing: { availability: { mode: "mean_of_slices" }, budget: { mode: "mean_of_slices" } },
      review: { availability: { mode: "mean_of_slices" }, budget: { mode: "mean_of_slices" } },
    }),
  }),
  Object.freeze({
    epoch: "rev-2507",
    windows: Object.freeze({
      standing: { availability: { mode: "mean_of_slices" }, budget: { mode: "mean_of_slices" } },
    }),
  }),
  Object.freeze({
    epoch: "rev-2509",
    windows: Object.freeze({
      standing: { availability: { mode: "weighted_slices", weight: "good" }, budget: { mode: "weighted_slices", weight: "good" } },
      review: { availability: { mode: "weighted_slices", weight: "good" }, budget: { mode: "weighted_slices", weight: "good" } },
    }),
  }),
]);
