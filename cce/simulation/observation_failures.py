#!/usr/bin/env python3
"""Separate missingness, systematic bias, and delay experiments for CCE.

The three observation failures are applied one at a time to the same synthetic
will-change scenario. No combination of mechanisms is tested in v0.1.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import random
import sys
from collections import defaultdict
from pathlib import Path
from typing import Mapping, Sequence

from cce.simulation.cce_mvm import clip, nearest_options
from cce.simulation.noise_robustness import quantile


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "config"
    / "observation_failures_v0.1.json"
)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def reference_sequence(scenario: Mapping[str, object]) -> list[float]:
    time_steps = int(scenario["time_steps"])
    change_step = int(scenario["change_step"])
    if not 0 < change_step < time_steps:
        raise ValueError("change_step must be inside the sequence")
    before = float(scenario["will_before"])
    after = float(scenario["will_after"])
    return [before if time < change_step else after for time in range(time_steps)]


def paired_random_sequences(
    *,
    seed: int,
    time_steps: int,
    mean: float,
    standard_deviation: float,
) -> tuple[list[float], list[float]]:
    noise_generator = random.Random(seed)
    missing_generator = random.Random(seed + 1_000_000)
    noise = [
        noise_generator.gauss(mean, standard_deviation)
        for _ in range(time_steps)
    ]
    missing_draws = [missing_generator.random() for _ in range(time_steps)]
    return noise, missing_draws


def simulate_run(
    *,
    mechanism: str,
    severity: float,
    seed: int,
    references: Sequence[float],
    scenario: Mapping[str, object],
    noise_config: Mapping[str, object],
) -> dict[str, object]:
    if mechanism not in {"missingness", "systematic_bias", "delay"}:
        raise ValueError(f"unknown mechanism: {mechanism}")
    learning_rate = float(scenario["learning_rate"])
    if not 0.0 <= learning_rate <= 1.0:
        raise ValueError("learning_rate must be in [0, 1]")

    noise, missing_draws = paired_random_sequences(
        seed=seed,
        time_steps=len(references),
        mean=float(noise_config["mean"]),
        standard_deviation=float(noise_config["standard_deviation"]),
    )
    lower = float(noise_config["clip_lower"])
    upper = float(noise_config["clip_upper"])
    change_step = int(scenario["change_step"])
    model = float(scenario["initial_model"])
    evaluated_errors: list[float] = []
    mismatch_steps = 0
    observed_count_full = 0
    observed_count_evaluation = 0

    for time, reference in enumerate(references):
        observation: float | None
        if mechanism == "missingness":
            observation = None if missing_draws[time] < severity else clip(
                reference + noise[time], lower, upper
            )
        elif mechanism == "systematic_bias":
            observation = clip(reference - severity + noise[time], lower, upper)
        else:
            delay_steps = int(severity)
            delayed_time = max(0, time - delay_steps)
            # Delay is defined as replay of the earlier observed sample, so its
            # measurement noise travels with that sample rather than being
            # redrawn at the current clock time.
            observation = clip(
                references[delayed_time] + noise[delayed_time], lower, upper
            )

        if observation is not None:
            observed_count_full += 1
            if time >= change_step:
                observed_count_evaluation += 1
            model = (1.0 - learning_rate) * model + learning_rate * observation

        proposal = clip(model - float(scenario["risk_deduction"]))
        if time >= change_step:
            error = abs(model - reference)
            evaluated_errors.append(error)
            reference_options = nearest_options(reference)
            proposed_options = nearest_options(proposal)
            if not any(option in proposed_options for option in reference_options):
                mismatch_steps += 1

    return {
        "mechanism": mechanism,
        "severity": severity,
        "signed_parameter": -severity if mechanism == "systematic_bias" else severity,
        "mechanism_direction": (
            "negative_away_from_postchange_reference"
            if mechanism == "systematic_bias"
            else "past_reference" if mechanism == "delay" else "not_directional"
        ),
        "seed": seed,
        "cumulative_model_error": round(sum(evaluated_errors), 9),
        "maximum_model_error": round(max(evaluated_errors), 9),
        "proposal_mismatch_steps": mismatch_steps,
        "final_model_error": round(evaluated_errors[-1], 9),
        "observed_fraction_full_sequence": round(
            observed_count_full / len(references), 9
        ),
        "observed_fraction_evaluation_window": round(
            observed_count_evaluation / (len(references) - change_step), 9
        ),
    }


def seed_values(config: Mapping[str, object]) -> tuple[int, ...]:
    start = int(config["start"])
    count = int(config["count"])
    if count < 2:
        raise ValueError("seed count must be at least 2")
    return tuple(range(start, start + count))


def condition_values(config: Mapping[str, object]) -> dict[str, tuple[float, ...]]:
    mechanisms = config["mechanisms"]
    return {
        "missingness": tuple(
            float(value) for value in mechanisms["missingness"]["rates"]
        ),
        "systematic_bias": tuple(
            abs(float(value)) for value in mechanisms["systematic_bias"]["offsets"]
        ),
        "delay": tuple(float(value) for value in mechanisms["delay"]["steps"]),
    }


def aggregate_rows(
    rows: Sequence[Mapping[str, object]],
    *,
    lower_probability: float,
    upper_probability: float,
) -> list[dict[str, object]]:
    grouped: dict[tuple[str, float], list[Mapping[str, object]]] = defaultdict(list)
    for row in rows:
        grouped[(str(row["mechanism"]), float(row["severity"]))].append(row)

    metrics = (
        "cumulative_model_error",
        "maximum_model_error",
        "proposal_mismatch_steps",
        "final_model_error",
        "observed_fraction_full_sequence",
        "observed_fraction_evaluation_window",
    )
    result: list[dict[str, object]] = []
    for (mechanism, severity), group in sorted(grouped.items()):
        summary: dict[str, object] = {
            "mechanism": mechanism,
            "severity": severity,
            "signed_parameter": group[0]["signed_parameter"],
            "mechanism_direction": group[0]["mechanism_direction"],
            "runs": len(group),
        }
        for metric in metrics:
            values = [float(row[metric]) for row in group]
            summary[f"{metric}_median"] = round(quantile(values, 0.5), 9)
            summary[f"{metric}_q05"] = round(
                quantile(values, lower_probability), 9
            )
            summary[f"{metric}_q95"] = round(
                quantile(values, upper_probability), 9
            )
        result.append(summary)
    return result


def run_all(
    config: Mapping[str, object],
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, object]:
    references = reference_sequence(config["scenario"])
    seeds = seed_values(config["seeds"])
    rows: list[dict[str, object]] = []
    for mechanism, severities in condition_values(config).items():
        for seed in seeds:
            for severity in severities:
                rows.append(
                    simulate_run(
                        mechanism=mechanism,
                        severity=severity,
                        seed=seed,
                        references=references,
                        scenario=config["scenario"],
                        noise_config=config["common_noise"],
                    )
                )
    aggregation = config["aggregation"]
    aggregate = aggregate_rows(
        rows,
        lower_probability=float(aggregation["lower_quantile"]),
        upper_probability=float(aggregation["upper_quantile"]),
    )
    return {
        "model": config["model"],
        "model_version": config["model_version"],
        "specification_version": config["specification_version"],
        "config_sha256": file_sha256(config_path),
        "generator_module": config["generator_module"],
        "source_release_status": config["source_release_status"],
        "synthetic_only": config["synthetic_only"],
        "config": config,
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

    config = result["config"]
    metadata = {
        "model": result["model"],
        "model_version": result["model_version"],
        "specification_version": result["specification_version"],
        "config_sha256": result["config_sha256"],
        "generator_module": result["generator_module"],
        "source_release_status": result["source_release_status"],
        "synthetic_only": result["synthetic_only"],
        "learning_rate": config["scenario"]["learning_rate"],
        "noise_standard_deviation": config["common_noise"]["standard_deviation"],
        "seed_start": config["seeds"]["start"],
        "seed_count": config["seeds"]["count"],
        "mechanisms": ["missingness", "systematic_bias", "delay"],
        "per_run_rows": len(per_run),
        "aggregate_rows": len(aggregate),
        "nominal_condition_count": 12,
        "effective_condition_count": 10,
        "nominal_rows": 1200,
        "nonduplicated_condition_rows": 1000,
        "independent_noise_sequences": config["seeds"]["count"],
        "comparison_design": "common_random_numbers_paired_across_conditions",
        "independence_unit": "seeded_noise_and_missingness_sequence",
        "delay_semantics": "delayed_reference_and_its_original_measurement_noise",
        "files": ["per_run.csv", "aggregate.csv"],
    }
    (output_dir / "metadata.json").write_bytes(
        (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument("--output-dir", type=Path)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    result = run_all(load_config(args.config), config_path=args.config)
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
