#!/usr/bin/env python3
"""Deterministic H1a/H2 experiments for the CCE minimal model.

The experiments use synthetic sequences only. They test model adaptation and
proposal behavior, not real-world clinical performance or permission to act.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

from cce.simulation.cce_mvm import clip, nearest_options


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "config"
    / "h1_h2_v0.1.json"
)


@dataclass(frozen=True)
class TrajectoryPoint:
    experiment: str
    learning_rate: float
    time: int
    reference: float
    observation: float
    model: float
    proposal: float
    reference_option: float
    proposed_options: tuple[float, ...]
    model_error: float
    proposal_matches_reference: bool

    def as_dict(self) -> dict[str, object]:
        return {
            "experiment": self.experiment,
            "learning_rate": round(self.learning_rate, 6),
            "time": self.time,
            "reference": round(self.reference, 6),
            "observation": round(self.observation, 6),
            "model": round(self.model, 6),
            "proposal": round(self.proposal, 6),
            "reference_option": self.reference_option,
            "proposed_options": "|".join(str(value) for value in self.proposed_options),
            "model_error": round(self.model_error, 6),
            "proposal_matches_reference": self.proposal_matches_reference,
        }


def validate_learning_rates(values: Iterable[float]) -> tuple[float, ...]:
    rates = tuple(float(value) for value in values)
    if not rates:
        raise ValueError("learning_rates must not be empty")
    if any(value < 0.0 or value > 1.0 for value in rates):
        raise ValueError("learning rates must be in [0, 1]")
    if tuple(sorted(set(rates))) != rates:
        raise ValueError("learning rates must be unique and ascending")
    return rates


def simulate_sequence(
    *,
    experiment: str,
    learning_rate: float,
    initial_model: float,
    references: Sequence[float],
    observations: Sequence[float],
    risk_deduction: float,
) -> list[TrajectoryPoint]:
    if len(references) != len(observations):
        raise ValueError("references and observations must have equal length")
    if not references:
        raise ValueError("sequence must not be empty")
    if not 0.0 <= learning_rate <= 1.0:
        raise ValueError("learning_rate must be in [0, 1]")

    model = initial_model
    points: list[TrajectoryPoint] = []
    for time, (reference, observation) in enumerate(zip(references, observations)):
        model = (1.0 - learning_rate) * model + learning_rate * observation
        proposal = clip(model - risk_deduction)
        reference_options = nearest_options(reference)
        proposed_options = nearest_options(proposal)
        matches = any(option in proposed_options for option in reference_options)
        points.append(
            TrajectoryPoint(
                experiment=experiment,
                learning_rate=learning_rate,
                time=time,
                reference=reference,
                observation=observation,
                model=model,
                proposal=proposal,
                reference_option=reference_options[0],
                proposed_options=proposed_options,
                model_error=abs(model - reference),
                proposal_matches_reference=matches,
            )
        )
    return points


def first_recovery_step(
    points: Sequence[TrajectoryPoint],
    *,
    start: int,
    tolerance: float,
    already_recovered_time: int | None = None,
) -> int | None:
    """Return recovery time only after an excursion beyond the tolerance band.

    ``None`` means either that no qualifying excursion occurred or that recovery
    was not observed. Callers must use the trajectory to distinguish those two
    states; zero is not used for both "no excursion" and "instant recovery".
    """

    if already_recovered_time is not None:
        if points[already_recovered_time].model_error <= tolerance:
            return None
    for point in points:
        if point.time >= start and point.model_error <= tolerance:
            return point.time - start + 1
    return None


def recovery_measure(
    points: Sequence[TrajectoryPoint],
    *,
    start: int,
    tolerance: float,
    excursion_check_time: int | None = None,
) -> tuple[int | None, str]:
    """Return a recovery value together with its unambiguous status.

    The status distinguishes a trajectory that never left the tolerance band
    from one that left it but did not recover within the simulated horizon.
    """

    if not points:
        raise ValueError("points must not be empty")
    if start < 0 or start >= len(points):
        raise ValueError("start must index the trajectory")
    if tolerance < 0.0:
        raise ValueError("tolerance must be non-negative")
    check_time = start if excursion_check_time is None else excursion_check_time
    if check_time < 0 or check_time >= len(points):
        raise ValueError("excursion_check_time must index the trajectory")
    if points[check_time].model_error <= tolerance:
        return None, "no_qualifying_excursion"
    step = first_recovery_step(points, start=start, tolerance=tolerance)
    if step is None:
        return None, "not_recovered_within_horizon"
    return step, "recovered"


def run_h1(config: Mapping[str, object]) -> tuple[list[dict[str, object]], list[TrajectoryPoint]]:
    time_steps = int(config["time_steps"])
    change_step = int(config["change_step"])
    if not 0 < change_step < time_steps:
        raise ValueError("H1 change_step must be inside the sequence")
    before = float(config["will_before"])
    after = float(config["will_after"])
    references = [before if time < change_step else after for time in range(time_steps)]
    observations = list(references)
    rates = validate_learning_rates(config["learning_rates"])
    tolerance = float(config["recovery_tolerance"])

    summaries: list[dict[str, object]] = []
    all_points: list[TrajectoryPoint] = []
    for rate in rates:
        points = simulate_sequence(
            experiment="H1a",
            learning_rate=rate,
            initial_model=float(config["initial_model"]),
            references=references,
            observations=observations,
            risk_deduction=float(config["risk_deduction"]),
        )
        after_change = points[change_step:]
        recovery_steps, recovery_status = recovery_measure(
            points, start=change_step, tolerance=tolerance
        )
        summaries.append(
            {
                "experiment": "H1a",
                "learning_rate": rate,
                "cumulative_model_error": round(
                    sum(point.model_error for point in after_change), 6
                ),
                "maximum_model_error": round(
                    max(point.model_error for point in after_change), 6
                ),
                "proposal_mismatch_steps": sum(
                    not point.proposal_matches_reference for point in after_change
                ),
                "recovery_steps": recovery_steps,
                "recovery_status": recovery_status,
                "final_model_error": round(points[-1].model_error, 6),
            }
        )
        all_points.extend(points)
    return summaries, all_points


def run_h2(config: Mapping[str, object]) -> tuple[list[dict[str, object]], list[TrajectoryPoint]]:
    time_steps = int(config["time_steps"])
    shock_start = int(config["shock_start"])
    shock_end = int(config["shock_end_exclusive"])
    if not 0 < shock_start < shock_end < time_steps:
        raise ValueError("H2 shock interval must be inside the sequence")
    stable_reference = float(config["stable_reference"])
    references = [stable_reference] * time_steps
    observations = [
        float(config["shock_observation"])
        if shock_start <= time < shock_end
        else float(config["normal_observation"])
        for time in range(time_steps)
    ]
    rates = validate_learning_rates(config["learning_rates"])
    tolerance = float(config["recovery_tolerance"])

    summaries: list[dict[str, object]] = []
    all_points: list[TrajectoryPoint] = []
    for rate in rates:
        points = simulate_sequence(
            experiment="H2",
            learning_rate=rate,
            initial_model=float(config["initial_model"]),
            references=references,
            observations=observations,
            risk_deduction=float(config["risk_deduction"]),
        )
        recovery_steps, recovery_status = recovery_measure(
            points,
            start=shock_end,
            tolerance=tolerance,
            excursion_check_time=shock_end - 1,
        )
        summaries.append(
            {
                "experiment": "H2",
                "learning_rate": rate,
                "cumulative_model_error": round(
                    sum(point.model_error for point in points), 6
                ),
                "maximum_model_error": round(
                    max(point.model_error for point in points), 6
                ),
                "proposal_mismatch_steps": sum(
                    not point.proposal_matches_reference for point in points
                ),
                "recovery_steps": recovery_steps,
                "recovery_status": recovery_status,
                "final_model_error": round(points[-1].model_error, 6),
            }
        )
        all_points.extend(points)
    return summaries, all_points


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def run_all(
    config: Mapping[str, object],
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, object]:
    h1_summary, h1_points = run_h1(config["h1"])
    h2_summary, h2_points = run_h2(config["h2"])
    return {
        "model": config["model"],
        "model_version": config["model_version"],
        "specification_version": config["specification_version"],
        "config_sha256": file_sha256(config_path),
        "generator_module": config["generator_module"],
        "source_release_status": config["source_release_status"],
        "synthetic_only": config["synthetic_only"],
        "summary": h1_summary + h2_summary,
        "trajectories": h1_points + h2_points,
    }


def write_results(result: Mapping[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    summary_rows = result["summary"]
    trajectory_rows = [point.as_dict() for point in result["trajectories"]]

    with (output_dir / "summary.csv").open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(summary_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(summary_rows)

    with (output_dir / "trajectories.csv").open(
        "w", encoding="utf-8", newline=""
    ) as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(trajectory_rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(trajectory_rows)

    metadata = {
        "model": result["model"],
        "model_version": result["model_version"],
        "specification_version": result["specification_version"],
        "config_sha256": result["config_sha256"],
        "generator_module": result["generator_module"],
        "source_release_status": result["source_release_status"],
        "synthetic_only": result["synthetic_only"],
        "summary_rows": len(summary_rows),
        "trajectory_rows": len(trajectory_rows),
        "files": ["summary.csv", "trajectories.csv"],
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
                "summary": result["summary"],
            },
            fp=sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
