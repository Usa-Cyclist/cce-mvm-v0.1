#!/usr/bin/env python3
"""Seeded observation-noise robustness experiments for CCE H1a and H2.

All inputs are synthetic. The same seed produces the same observation sequence
for every learning rate within an experiment, enabling paired comparisons.
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from cce.simulation.cce_mvm import clip
from cce.simulation.h1_h2_experiments import (
    DEFAULT_CONFIG,
    TrajectoryPoint,
    file_sha256,
    load_config,
    simulate_sequence,
    validate_learning_rates,
)


DEFAULT_NOISE_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "config"
    / "h1_h2_noise_v0.1.json"
)


def quantile(values: Iterable[float], probability: float) -> float:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        raise ValueError("quantile requires at least one value")
    if not 0.0 <= probability <= 1.0:
        raise ValueError("probability must be in [0, 1]")
    position = (len(ordered) - 1) * probability
    lower_index = int(position)
    upper_index = min(lower_index + 1, len(ordered) - 1)
    fraction = position - lower_index
    return ordered[lower_index] + fraction * (
        ordered[upper_index] - ordered[lower_index]
    )


def seeded_observations(
    *,
    bases: Sequence[float],
    seed: int,
    mean: float,
    standard_deviation: float,
    lower: float,
    upper: float,
) -> list[float]:
    if standard_deviation < 0.0:
        raise ValueError("standard_deviation must be non-negative")
    generator = random.Random(seed)
    return [
        clip(
            base + generator.gauss(mean, standard_deviation),
            lower,
            upper,
        )
        for base in bases
    ]


def metrics_from_points(
    *,
    experiment: str,
    learning_rate: float,
    seed: int,
    points: Sequence[TrajectoryPoint],
    evaluation_start: int,
) -> dict[str, object]:
    evaluated = points[evaluation_start:]
    return {
        "experiment": experiment,
        "learning_rate": learning_rate,
        "seed": seed,
        "cumulative_model_error": round(
            sum(point.model_error for point in evaluated), 9
        ),
        "maximum_model_error": round(
            max(point.model_error for point in evaluated), 9
        ),
        "proposal_mismatch_steps": sum(
            not point.proposal_matches_reference for point in evaluated
        ),
        "final_model_error": round(points[-1].model_error, 9),
    }


def seed_values(config: Mapping[str, object]) -> tuple[int, ...]:
    start = int(config["start"])
    count = int(config["count"])
    if count < 2:
        raise ValueError("seed count must be at least 2")
    return tuple(range(start, start + count))


def run_h1_noise(
    *,
    base: Mapping[str, object],
    noise: Mapping[str, object],
    seeds: Sequence[int],
) -> list[dict[str, object]]:
    time_steps = int(base["time_steps"])
    change_step = int(base["change_step"])
    before = float(base["will_before"])
    after = float(base["will_after"])
    references = [before if time < change_step else after for time in range(time_steps)]
    rates = validate_learning_rates(base["learning_rates"])
    rows: list[dict[str, object]] = []

    for seed in seeds:
        observations = seeded_observations(
            bases=references,
            seed=seed,
            mean=float(noise["mean"]),
            standard_deviation=float(noise["standard_deviation"]),
            lower=float(noise["clip_lower"]),
            upper=float(noise["clip_upper"]),
        )
        for rate in rates:
            points = simulate_sequence(
                experiment="H1a-noise",
                learning_rate=rate,
                initial_model=float(base["initial_model"]),
                references=references,
                observations=observations,
                risk_deduction=float(base["risk_deduction"]),
            )
            rows.append(
                metrics_from_points(
                    experiment="H1a-noise",
                    learning_rate=rate,
                    seed=seed,
                    points=points,
                    evaluation_start=change_step,
                )
            )
    return rows


def run_h2_noise(
    *,
    base: Mapping[str, object],
    noise: Mapping[str, object],
    seeds: Sequence[int],
) -> list[dict[str, object]]:
    time_steps = int(base["time_steps"])
    shock_start = int(base["shock_start"])
    shock_end = int(base["shock_end_exclusive"])
    stable_reference = float(base["stable_reference"])
    references = [stable_reference] * time_steps
    observation_bases = [
        float(base["shock_observation"])
        if shock_start <= time < shock_end
        else float(base["normal_observation"])
        for time in range(time_steps)
    ]
    rates = validate_learning_rates(base["learning_rates"])
    rows: list[dict[str, object]] = []

    for seed in seeds:
        observations = seeded_observations(
            bases=observation_bases,
            seed=seed,
            mean=float(noise["mean"]),
            standard_deviation=float(noise["standard_deviation"]),
            lower=float(noise["clip_lower"]),
            upper=float(noise["clip_upper"]),
        )
        for rate in rates:
            points = simulate_sequence(
                experiment="H2-noise",
                learning_rate=rate,
                initial_model=float(base["initial_model"]),
                references=references,
                observations=observations,
                risk_deduction=float(base["risk_deduction"]),
            )
            rows.append(
                metrics_from_points(
                    experiment="H2-noise",
                    learning_rate=rate,
                    seed=seed,
                    points=points,
                    evaluation_start=0,
                )
            )
    return rows


def aggregate_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    lower_quantile: float,
    upper_quantile: float,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, float], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["experiment"]), float(row["learning_rate"]))].append(row)

    result: list[dict[str, object]] = []
    metrics = (
        "cumulative_model_error",
        "maximum_model_error",
        "proposal_mismatch_steps",
        "final_model_error",
    )
    for (experiment, learning_rate), group in sorted(grouped.items()):
        summary: dict[str, object] = {
            "experiment": experiment,
            "learning_rate": learning_rate,
            "runs": len(group),
        }
        for metric in metrics:
            values = [float(row[metric]) for row in group]
            summary[f"{metric}_median"] = round(quantile(values, 0.5), 9)
            summary[f"{metric}_q05"] = round(quantile(values, lower_quantile), 9)
            summary[f"{metric}_q95"] = round(quantile(values, upper_quantile), 9)
        result.append(summary)
    return result


def load_noise_config(path: Path = DEFAULT_NOISE_CONFIG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def run_all(
    base_config: Mapping[str, object],
    noise_config: Mapping[str, object],
    *,
    base_config_path: Path = DEFAULT_CONFIG,
    config_path: Path = DEFAULT_NOISE_CONFIG,
) -> dict[str, object]:
    seeds = seed_values(noise_config["seeds"])
    noise = noise_config["noise"]
    rows = run_h1_noise(
        base=base_config["h1"],
        noise=noise,
        seeds=seeds,
    ) + run_h2_noise(
        base=base_config["h2"],
        noise=noise,
        seeds=seeds,
    )
    aggregation = noise_config["aggregation"]
    aggregate = aggregate_rows(
        rows,
        lower_quantile=float(aggregation["lower_quantile"]),
        upper_quantile=float(aggregation["upper_quantile"]),
    )
    return {
        "model": base_config["model"],
        "model_version": noise_config["model_version"],
        "specification_version": noise_config["specification_version"],
        "config_sha256": file_sha256(config_path),
        "base_config_sha256": file_sha256(base_config_path),
        "generator_module": noise_config["generator_module"],
        "source_release_status": noise_config["source_release_status"],
        "synthetic_only": True,
        "noise_config": noise_config,
        "per_run": rows,
        "aggregate": aggregate,
    }


def write_results(result: Mapping[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    per_run = result["per_run"]
    aggregate = result["aggregate"]

    with (output_dir / "per_run.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(per_run[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(per_run)

    with (output_dir / "aggregate.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(aggregate[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(aggregate)

    noise_config = result["noise_config"]
    metadata = {
        "model": result["model"],
        "model_version": result["model_version"],
        "specification_version": result["specification_version"],
        "config_sha256": result["config_sha256"],
        "base_config_sha256": result["base_config_sha256"],
        "generator_module": result["generator_module"],
        "source_release_status": result["source_release_status"],
        "synthetic_only": result["synthetic_only"],
        "distribution": noise_config["noise"]["distribution"],
        "noise_standard_deviation": noise_config["noise"]["standard_deviation"],
        "seed_start": noise_config["seeds"]["start"],
        "seed_count": noise_config["seeds"]["count"],
        "independent_noise_sequences": noise_config["seeds"]["count"],
        "conditions_per_noise_sequence": len(aggregate),
        "comparison_design": "common_random_numbers_paired_across_conditions",
        "independence_unit": "seeded_observation_noise_sequence",
        "per_run_rows": len(per_run),
        "aggregate_rows": len(aggregate),
        "files": ["per_run.csv", "aggregate.csv"],
    }
    (output_dir / "metadata.json").write_bytes(
        (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--noise-config", type=Path, default=DEFAULT_NOISE_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_all(
        load_config(args.base_config),
        load_noise_config(args.noise_config),
        base_config_path=args.base_config,
        config_path=args.noise_config,
    )
    if args.output_dir:
        write_results(result, args.output_dir)
    else:
        json.dump(
            {
                "model": result["model"],
                "synthetic_only": result["synthetic_only"],
                "aggregate": result["aggregate"],
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
