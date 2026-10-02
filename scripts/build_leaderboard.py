#!/usr/bin/env python3
"""Render public tables from the paper's integer counts; never call a model."""
from __future__ import annotations

import argparse
import csv
import io
import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DOMAINS = {"Web": 36, "Game": 29, "DevOps": 20, "Mobile": 20}
START, END = "<!-- leaderboard:start -->", "<!-- leaderboard:end -->"


def load_scores():
    data = json.loads((ROOT / "results/paper-results.json").read_text())
    if data["domains"] != DOMAINS:
        raise ValueError("paper denominators differ from the released domains")
    seen = set()
    for row in data["scores"]:
        key = (row["domain"], row["model"], row["condition"], row["metric"])
        if key in seen:
            raise ValueError(f"duplicate score: {key}")
        seen.add(key)
        if row["status"] == "evaluated":
            count, total = row["successes"], row["denominator"]
            if total != DOMAINS[row["domain"]] or not 0 <= count <= total:
                raise ValueError(f"invalid count: {key}")
            if abs(row["percent"] - 100 * count / total) > 1e-9:
                raise ValueError(f"percentage does not match counts: {key}")
        elif any(row.get(field) is not None for field in ("successes", "denominator", "percent")):
            raise ValueError(f"missing result contains a score: {key}")
    return data["scores"]


def label(row):
    name = row["label"]
    if row["model"].startswith("api-"):
        if name.startswith(("Opus", "Sonnet", "Fable")):
            name = "Claude " + name
        name += " (API)"
    return name


def value(row, counts=False):
    if row["status"] != "evaluated":
        return "deferred" if row["status"] == "deferred" else "—"
    percentage = f"{100 * row['successes'] / row['denominator']:.1f}"
    return f"{row['successes']}/{row['denominator']} ({percentage}%)" if counts else percentage


def render():
    rows = load_scores()
    lookup = {(r["domain"], r["model"], r["condition"], r["metric"]): r for r in rows}
    models = list(dict.fromkeys(r["model"] for r in rows))
    maxima = {d: max(r["percent"] for r in rows if r["domain"] == d and
                    r["condition"] == "hybrid" and r["metric"] == "pass@1" and
                    r["status"] == "evaluated") for d in DOMAINS}
    table = ["| Model / agent | Web (36) | Game (29) | DevOps (20) | Mobile (20) |",
             "| --- | ---: | ---: | ---: | ---: |"]
    for model in models:
        cells = []
        for domain in DOMAINS:
            code = lookup[domain, model, "code-only", "pass@1"]
            cua = lookup[domain, model, "hybrid", "pass@1"]
            score = value(cua)
            if cua["percent"] == maxima[domain]:
                score = f"**{score}**"
            cells.append(f"{value(code)} → {score}")
        table.append("| " + label(lookup["Web", model, "hybrid", "pass@1"]) + " | " + " | ".join(cells) + " |")
    table_text = "\n".join(table)
    readme = (ROOT / "README.md").read_text()
    before, rest = readme.split(START, 1)
    _, after = rest.split(END, 1)
    readme = before + START + "\n" + table_text + "\n" + END + after
    details = ["# CUA-SWE paper results", "", "Snapshot: September 24, 2026. Generated from [paper-results.json](paper-results.json).",
               "", "Each score is successes / tasks (percentage). See [scoring and provenance](../docs/results.md).",
               "", "[Web](#web) · [Game](#game) · [DevOps](#devops) · [Mobile](#mobile)", ""]
    for domain in DOMAINS:
        details += [f"## {domain}", "", f"{DOMAINS[domain]} tasks. Original single-attempt results.", "",
                    "| Model / agent | Code-only pass@1 | Hybrid CUA pass@1 |", "| --- | ---: | ---: |"]
        for model in sorted(models, key=lambda m: -(lookup[domain, m, "hybrid", "pass@1"]["percent"] or 0)):
            a, b = (lookup[domain, model, c, "pass@1"] for c in ("code-only", "hybrid"))
            details.append(f"| {label(b)} | {value(a, True)} | {value(b, True)} |")
        details += ["", "### Reviewed repeated-attempt cohort", "",
                    "| Model / agent | First attempt in this set | Pass@3 |", "| --- | ---: | ---: |"]
        for model in models:
            a = lookup.get((domain, model, "hybrid", "repeat-first"))
            b = lookup.get((domain, model, "hybrid", "pass@3"))
            if a and b:
                details.append(f"| {label(b)} | {value(a, True)} | {value(b, True)} |")
        if domain == "Game":
            details += ["", "The repeated set includes eight reviewed runtime replacements. Its first-attempt scores are distinct from the original pass@1 table above."]
        details += [""]
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=["domain", "model", "label", "condition", "metric", "successes", "denominator", "status", "percent"])
    writer.writeheader()
    writer.writerows(rows)
    return {ROOT / "README.md": readme, ROOT / "results/README.md": "\n".join(details),
            ROOT / "results/leaderboard.csv": out.getvalue()}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true")
    args = parser.parse_args()
    stale = []
    for path, content in render().items():
        if args.check:
            if not path.exists() or path.read_bytes() != content.encode():
                stale.append(str(path.relative_to(ROOT)))
        else:
            path.write_bytes(content.encode())
    if stale:
        raise SystemExit("Stale generated tables: " + ", ".join(stale))
    print("Leaderboard tables verified." if args.check else "Leaderboard tables generated.")


if __name__ == "__main__":
    main()
