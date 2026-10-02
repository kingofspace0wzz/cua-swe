import { dedupeSpans, sortSpans } from "./basicAdjusters.js";

export function compileAdjusters(policy) {
  return [
    { name: "dedupe", apply: dedupeSpans },
    { name: "sort", apply: sortSpans },
  ];
}
