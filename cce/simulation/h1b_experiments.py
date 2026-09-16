#!/usr/bin/env python3
"""Run the synthetic H1b influence experiments and review diagnostic.

The experiment separates a proposal-response coupling input, counterfactual
effects on response and decision, and rights-procedure diagnostics. It is an
explanatory model, not a psychological, clinical, or legal assessment. The
original 33 conditions and seven rights cases were fixed internally before
execution and were not registered in an external registry. One unconfounded
option-narrowing diagnostic was added after independent AI review; metadata
records that mixed provenance explicitly.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path
from typing import Mapping, Sequence

from .cce_mvm import (
    Delegation,
    PersonResponse,
    RightsGates,
    clip,
    decide,
    nearest_options,
    validate_normalized_value,
    validate_options,
)


DEFAULT_CONFIG = (
    Path(__file__).resolve().parents[1] / "experiments" / "config" / "h1b_v0.1.json"
)


def load_config(path: Path = DEFAULT_CONFIG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def coupled_response(
    baseline_response: float, proposal_value: float, coupling: float
) -> float:
    """Return the synthetic post-proposal response value."""

    validate_normalized_value(baseline_response, "baseline_response")
    validate_normalized_value(proposal_value, "proposal_value")
    if not 0.0 <= coupling <= 1.0:
        raise ValueError("coupling must be in [0, 1]")
    return clip(
        (1.0 - coupling) * baseline_response + coupling * proposal_value
    )


def normalized_distance(left: float, right: float) -> float:
    """Distance on [-1, 1], normalized to [0, 1]."""

    normalized_left = validate_normalized_value(left, "left")
    normalized_right = validate_normalized_value(right, "right")
    return abs(normalized_left - normalized_right) / 2.0


def option_loss(
    baseline_options: Sequence[float], presented_options: Sequence[float]
) -> float:
    """Return the fraction of baseline options removed from presentation."""

    baseline = set(validate_options(baseline_options))
    presented = set(validate_options(presented_options))
    return 1.0 - len(baseline & presented) / len(baseline)


def inactive_delegation() -> Delegation:
    return Delegation(
        delegate="none",
        scopes=(),
        within_time_limit=False,
        person_chosen=False,
        revoked=False,
        revocable=True,
    )


def rights_gates(
    base: Mapping[str, str], overrides: Mapping[str, str] | None = None
) -> RightsGates:
    states = dict(base)
    states.update(overrides or {})
    return RightsGates(states)


def proposal_relationship(baseline: float, proposal: float) -> str:
    if abs(proposal - baseline) <= 1e-12:
        return "aligned"
    if abs(proposal + baseline) <= 1e-12:
        return "opposed"
    return "intermediate"


def validate_decision_event(event: Mapping[str, object]) -> None:
    """Validate the fixed H1b control choices that the implementation supports."""

    validate_options(event["options"])
    validate_normalized_value(event["baseline_response"], "baseline_response")
    if bool(event["valid_delegation"]):
        raise ValueError("H1b v0.1 requires valid_delegation=false")
    if float(event["counterfactual_coupling"]) != 0.0:
        raise ValueError("H1b v0.1 counterfactual_coupling must be 0")
    if event["tie_rule"] != "pause_and_present_all_nearest_options":
        raise ValueError("unsupported tie_rule")


def analysis_response_from_nearest(
    nearest: Sequence[float],
) -> tuple[PersonResponse, str, bool, str]:
    """Map an equation output to a test response without attributing it to a person."""

    if len(nearest) == 1:
        return (
            PersonResponse("modify", nearest[0]),
            "analysis_substitution_from_discretized_equation_output",
            True,
            "none",
        )
    return (
        PersonResponse("defer"),
        "analysis_substitution_from_discretized_equation_output",
        True,
        "discretization_tie",
    )


def decision_opposes_baseline(
    decision_value: float | None, baseline: float
) -> bool | None:
    if decision_value is None:
        return None
    return normalized_distance(decision_value, baseline) > 0.5


def _pipe(values: Sequence[float]) -> str:
    return "|".join(str(float(value)) for value in values)


def counterfactual_decision_from_baseline(
    baseline: float, options: Sequence[float], gates: RightsGates
) -> float | None:
    """Apply the same decision rule to the no-coupling baseline."""

    nearest = nearest_options(baseline, options)
    response = (
        PersonResponse("modify", nearest[0])
        if len(nearest) == 1
        else PersonResponse("defer")
    )
    result = decide(
        options=options,
        person_response=response,
        delegation=inactive_delegation(),
        decision_scope="outing_method",
        delegated_option=None,
        rights_gates=gates,
    )
    return result.value


def run_h1b_1(config: Mapping[str, object]) -> list[dict[str, object]]:
    event = config["decision_event"]
    validate_decision_event(event)
    experiment = config["h1b_1_response_coupling"]
    options = tuple(float(value) for value in event["options"])
    baseline = float(event["baseline_response"])
    gates = rights_gates(experiment["rights_gates"])
    delegation = inactive_delegation()
    rows: list[dict[str, object]] = []

    for proposal_raw in experiment["proposal_values"]:
        proposal = float(proposal_raw)
        relationship = proposal_relationship(baseline, proposal)
        counterfactual_response = coupled_response(
            baseline, proposal, float(event["counterfactual_coupling"])
        )
        counterfactual_decision = counterfactual_decision_from_baseline(
            counterfactual_response, options, gates
        )
        for coupling_raw in experiment["couplings"]:
            coupling = float(coupling_raw)
            response = coupled_response(baseline, proposal, coupling)
            nearest = nearest_options(response, options)
            (
                person_response,
                person_response_source,
                analysis_substituted_response,
                pause_source,
            ) = analysis_response_from_nearest(nearest)
            decision = decide(
                options=options,
                person_response=person_response,
                delegation=delegation,
                decision_scope="outing_method",
                delegated_option=None,
                rights_gates=gates,
            )
            decision_effect = (
                None
                if decision.value is None or counterfactual_decision is None
                else normalized_distance(decision.value, counterfactual_decision)
            )
            mismatch = (
                None
                if decision.value is None
                else normalized_distance(decision.value, baseline)
            )
            rows.append(
                {
                    "proposal_value": proposal,
                    "proposal_relationship": relationship,
                    "coupling": coupling,
                    "baseline_response": baseline,
                    "post_proposal_response": round(response, 9),
                    "nearest_options": _pipe(nearest),
                    "person_response": person_response.action,
                    "person_response_source": person_response_source,
                    "analysis_substituted_response": analysis_substituted_response,
                    "pause_source": pause_source,
                    "decision_status": decision.status,
                    "decision_value": decision.value,
                    "response_effect": round(
                        normalized_distance(response, baseline), 9
                    ),
                    "decision_effect": (
                        None if decision_effect is None else round(decision_effect, 9)
                    ),
                    "decision_mismatch": (
                        None if mismatch is None else round(mismatch, 9)
                    ),
                    "decision_opposes_baseline_response": decision_opposes_baseline(
                        decision.value, baseline
                    ),
                    "option_loss_structural_constant": round(
                        option_loss(options, options), 9
                    ),
                    "rejection_blockage_structural_constant": 0,
                    "rights_violation_structural_constant": False,
                    "analysis_row_valid": True,
                }
            )
    return rows


def _case_expected_valid(case: Mapping[str, object]) -> bool:
    return bool(case.get("expected_analysis_row_valid", True))


def run_h1b_2(config: Mapping[str, object]) -> list[dict[str, object]]:
    event = config["decision_event"]
    validate_decision_event(event)
    experiment = config["h1b_2_rights_protection"]
    common = experiment["common"]
    if bool(common["valid_delegation"]):
        raise ValueError("H1b v0.1 requires valid_delegation=false")
    baseline_options = tuple(float(value) for value in event["options"])
    baseline = float(common["baseline_response"])
    proposal = float(common["proposal_value"])
    coupling = float(common["coupling"])
    provisional_response = coupled_response(baseline, proposal, coupling)
    delegation = inactive_delegation()
    rows: list[dict[str, object]] = []

    for case in experiment["cases"]:
        presented_options = tuple(float(value) for value in case["presented_options"])
        test_fixture_only = bool(case.get("test_fixture_only", False))
        gate_states = rights_gates(
            common["rights_gates"], case.get("rights_override", {})
        )
        gate_states.validate()
        counterfactual_response = coupled_response(
            baseline, proposal, float(event["counterfactual_coupling"])
        )
        counterfactual_decision = counterfactual_decision_from_baseline(
            counterfactual_response, baseline_options, gate_states
        )
        has_rights_violation = any(
            state == "violated" for state in gate_states.states.values()
        )

        if test_fixture_only:
            decision_status = "decided"
            decision_value = float(case["forced_decision"])
            decision_rule = "unsafe_negative_control"
            pause_consequence_status = "not_applicable"
            pause_source = "none"
        else:
            response_option = case.get("response_option")
            person_response = PersonResponse(
                str(case["person_response"]),
                None if response_option is None else float(response_option),
            )
            decision = decide(
                options=presented_options,
                person_response=person_response,
                delegation=delegation,
                decision_scope="outing_method",
                delegated_option=None,
                rights_gates=gate_states,
            )
            decision_status = decision.status
            decision_value = decision.value
            decision_rule = decision.rule
            pause_consequence_status = decision.pause_consequence_status
            if decision.status != "paused":
                pause_source = "none"
            elif not gate_states.all_met:
                pause_source = "rights_gate"
            else:
                pause_source = "synthetic_case_response"

        person_action = str(case["person_response"])
        rejection_blockage = int(
            person_action == "reject" and decision_status == "decided"
        )
        decision_effect = (
            None
            if decision_value is None or counterfactual_decision is None
            else normalized_distance(decision_value, counterfactual_decision)
        )
        mismatch = (
            None
            if decision_value is None
            else normalized_distance(decision_value, baseline)
        )
        measured_option_loss = option_loss(baseline_options, presented_options)
        gate_assertion_conflict = measured_option_loss > 0.0 and gate_states.all_met
        rows.append(
            {
                "case_id": str(case["id"]),
                "proposal_value": proposal,
                "coupling": coupling,
                "baseline_response": baseline,
                "post_proposal_response": round(provisional_response, 9),
                "person_response": person_action,
                "person_response_source": "synthetic_case_input",
                "analysis_substituted_response": False,
                "pause_source": pause_source,
                "response_option": case.get("response_option"),
                "presented_options": _pipe(presented_options),
                "decision_status": decision_status,
                "decision_value": decision_value,
                "decision_rule": decision_rule,
                "response_effect": round(
                    normalized_distance(provisional_response, baseline), 9
                ),
                "decision_effect": (
                    None if decision_effect is None else round(decision_effect, 9)
                ),
                "decision_mismatch": (
                    None if mismatch is None else round(mismatch, 9)
                ),
                "decision_opposes_baseline_response": decision_opposes_baseline(
                    decision_value, baseline
                ),
                "option_loss": round(measured_option_loss, 9),
                "gate_assertion_conflicts_with_spec_definition": gate_assertion_conflict,
                "rejection_blockage": rejection_blockage,
                "rights_violation": has_rights_violation,
                "analysis_row_valid": _case_expected_valid(case),
                "pause_consequence_status": pause_consequence_status,
                "test_fixture_only": test_fixture_only,
            }
        )
    return rows


def run_all(
    config: Mapping[str, object],
    *,
    config_path: Path = DEFAULT_CONFIG,
) -> dict[str, object]:
    h1b_1 = run_h1b_1(config)
    h1b_2 = run_h1b_2(config)
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
        "h1b_1": h1b_1,
        "h1b_2": h1b_2,
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
    h1b_1 = result["h1b_1"]
    h1b_2 = result["h1b_2"]
    _write_csv(output_dir / "h1b_1.csv", h1b_1)
    _write_csv(output_dir / "h1b_2.csv", h1b_2)
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
        "provenance_scope": result["config"].get("provenance_scope"),
        "review_correction": result["config"].get("review_correction"),
        "implementation_status": (
            "executed_original_internally_fixed_conditions_plus_postreview_diagnostic"
        ),
        "h1b_1_rows": len(h1b_1),
        "h1b_2_rows": len(h1b_2),
        "analysis_valid_h1b_2_rows": sum(
            bool(row["analysis_row_valid"]) for row in h1b_2
        ),
        "invalid_negative_controls": sum(
            not bool(row["analysis_row_valid"]) for row in h1b_2
        ),
        "h1b_1_decision_metric_degeneracy": (
            "decision_effect equals decision_mismatch because the baseline response "
            "is itself a feasible option in all H1b-1 conditions"
        ),
        "files": ["h1b_1.csv", "h1b_2.csv"],
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
                "h1b_1": result["h1b_1"],
                "h1b_2": result["h1b_2"],
            },
            sys.stdout,
            ensure_ascii=False,
            indent=2,
        )
        print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
