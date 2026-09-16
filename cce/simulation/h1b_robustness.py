#!/usr/bin/env python3
"""Run internally prespecified synthetic robustness checks for CCE H1b.

The H1b response equation, decision rule, and rights gates are unchanged.
Only the initial response or researcher-defined option grid is varied. The
configuration was fixed internally before execution and was not registered in
an external registry.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
from pathlib import Path
from typing import Mapping, Sequence

from .cce_mvm import decide, nearest_options, validate_options
from .h1b_experiments import (
    analysis_response_from_nearest,
    counterfactual_decision_from_baseline,
    coupled_response,
    decision_opposes_baseline,
    inactive_delegation,
    normalized_distance,
    rights_gates,
)


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "config"
    / "h1b_robustness_v0.1.json"
)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _pipe(values: Sequence[float]) -> str:
    return "|".join(str(float(value)) for value in values)


def _condition_id(prefix: str, coupling: float) -> str:
    return f"{prefix}|a={coupling:.1f}"


def _run_condition(
    *,
    experiment: str,
    condition_prefix: str,
    option_set_id: str,
    baseline: float,
    proposal: float,
    coupling: float,
    options: Sequence[float],
    gates,
) -> dict[str, object]:
    numeric_options = validate_options(options)
    counterfactual_decision = counterfactual_decision_from_baseline(
        baseline, numeric_options, gates
    )

    response = coupled_response(baseline, proposal, coupling)
    nearest = nearest_options(response, numeric_options)
    (
        person_response,
        person_response_source,
        analysis_substituted_response,
        pause_source,
    ) = analysis_response_from_nearest(nearest)
    decision = decide(
        options=numeric_options,
        person_response=person_response,
        delegation=inactive_delegation(),
        decision_scope="outing_method",
        delegated_option=None,
        rights_gates=gates,
    )
    decision_effect = (
        None
        if decision.value is None or counterfactual_decision is None
        else normalized_distance(decision.value, counterfactual_decision)
    )
    decision_mismatch = (
        None
        if decision.value is None
        else normalized_distance(decision.value, baseline)
    )
    return {
        "experiment": experiment,
        "condition_id": _condition_id(condition_prefix, coupling),
        "option_set_id": option_set_id,
        "baseline_response": baseline,
        "baseline_magnitude": abs(baseline),
        "proposal_value": proposal,
        "coupling": coupling,
        "options": _pipe(numeric_options),
        "post_proposal_response": round(response, 9),
        "nearest_options": _pipe(nearest),
        "person_response": person_response.action,
        "person_response_source": person_response_source,
        "analysis_substituted_response": analysis_substituted_response,
        "pause_source": pause_source,
        "decision_status": decision.status,
        "decision_value": decision.value,
        "response_effect": round(normalized_distance(response, baseline), 9),
        "decision_effect": (
            None if decision_effect is None else round(decision_effect, 9)
        ),
        "decision_mismatch": (
            None if decision_mismatch is None else round(decision_mismatch, 9)
        ),
        "decision_opposes_baseline_response": decision_opposes_baseline(
            decision.value, baseline
        ),
        "ai_option_loss_structural_constant": 0.0,
        "rights_violation_structural_constant": False,
        "analysis_row_valid": True,
    }


def run_baseline_sensitivity(
    config: Mapping[str, object],
) -> list[dict[str, object]]:
    experiment = config["baseline_sensitivity"]
    common = config["common"]
    couplings = tuple(float(value) for value in config["couplings"])
    options = tuple(float(value) for value in experiment["options"])
    gates = rights_gates(common["rights_gates"])
    rows: list[dict[str, object]] = []

    for baseline_raw in experiment["baseline_responses"]:
        baseline = float(baseline_raw)
        proposal = -baseline
        prefix = f"B={baseline:+.2f}"
        for coupling in couplings:
            rows.append(
                _run_condition(
                    experiment="baseline_sensitivity",
                    condition_prefix=prefix,
                    option_set_id="baseline_3",
                    baseline=baseline,
                    proposal=proposal,
                    coupling=coupling,
                    options=options,
                    gates=gates,
                )
            )
    return rows


def run_option_grid_sensitivity(
    config: Mapping[str, object],
) -> list[dict[str, object]]:
    experiment = config["option_grid_sensitivity"]
    common = config["common"]
    couplings = tuple(float(value) for value in config["couplings"])
    baseline = float(experiment["baseline_response"])
    proposal = float(experiment["proposal_value"])
    gates = rights_gates(common["rights_gates"])
    rows: list[dict[str, object]] = []

    for option_set in experiment["option_sets"]:
        option_set_id = str(option_set["id"])
        options = tuple(float(value) for value in option_set["options"])
        for coupling in couplings:
            rows.append(
                _run_condition(
                    experiment="option_grid_sensitivity",
                    condition_prefix=option_set_id,
                    option_set_id=option_set_id,
                    baseline=baseline,
                    proposal=proposal,
                    coupling=coupling,
                    options=options,
                    gates=gates,
                )
            )
    return rows


def run_all(
    config: Mapping[str, object],
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, object]:
    common = config["common"]
    if bool(common["valid_delegation"]):
        raise ValueError("H1b robustness v0.1 requires valid_delegation=false")
    if common["tie_rule"] != "pause_and_present_all_nearest_options":
        raise ValueError("unsupported tie_rule")
    baseline_rows = run_baseline_sensitivity(config)
    option_rows = run_option_grid_sensitivity(config)
    expected_total = int(config["expected_total_conditions"])
    if len(baseline_rows) + len(option_rows) != expected_total:
        raise ValueError("generated rows do not match expected_total_conditions")
    return {
        "model": config["model"],
        "model_version": config["model_version"],
        "specification_version": config["specification_version"],
        "synthetic_only": config["synthetic_only"],
        "provenance_status": config["status"],
        "config_sha256": file_sha256(config_path),
        "generator_module": config["generator_module"],
        "source_release_status": config["source_release_status"],
        "config": config,
        "baseline_sensitivity": baseline_rows,
        "option_grid_sensitivity": option_rows,
    }


def _write_csv(path: Path, rows: Sequence[Mapping[str, object]]) -> None:
    with path.open("w", encoding="utf-8", newline="") as stream:
        writer = csv.DictWriter(
            stream, fieldnames=list(rows[0]), lineterminator="\n"
        )
        writer.writeheader()
        writer.writerows(rows)


def write_results(result: Mapping[str, object], output_dir: Path) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)
    baseline_rows = result["baseline_sensitivity"]
    option_rows = result["option_grid_sensitivity"]
    _write_csv(output_dir / "baseline_sensitivity.csv", baseline_rows)
    _write_csv(output_dir / "option_grid_sensitivity.csv", option_rows)
    metadata = {
        "model": result["model"],
        "model_version": result["model_version"],
        "specification_version": result["specification_version"],
        "config_sha256": result["config_sha256"],
        "generator_module": result["generator_module"],
        "source_release_status": result["source_release_status"],
        "synthetic_only": result["synthetic_only"],
        "provenance_status": result["provenance_status"],
        "config_status_at_fixing_time": result["provenance_status"],
        "implementation_status": "executed_from_internally_fixed_config",
        "baseline_sensitivity_rows": len(baseline_rows),
        "option_grid_sensitivity_rows": len(option_rows),
        "total_rows": len(baseline_rows) + len(option_rows),
        "analysis_valid_rows": sum(
            bool(row["analysis_row_valid"])
            for row in baseline_rows + option_rows
        ),
        "option_set_role": result["config"]["option_grid_sensitivity"][
            "option_set_role"
        ],
        "files": ["baseline_sensitivity.csv", "option_grid_sensitivity.csv"],
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
    config = load_config(args.config)
    result = run_all(config, config_path=args.config)
    if args.output_dir:
        write_results(result, args.output_dir)
    else:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
