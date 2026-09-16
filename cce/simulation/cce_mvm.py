#!/usr/bin/env python3
"""CCE v0.1 minimal executable model.

This module reproduces the synthetic hand calculation in
model/minimal-equations-and-hand-calculation.md using only Python's standard
library. It is a research explainer, not a clinical or legal decision tool.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import sys
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Iterable, Mapping, Sequence


OPTIONS: tuple[float, ...] = (-1.0, 0.0, 1.0)
GATE_NAMES: tuple[str, ...] = (
    "will_and_preferences",
    "support_access",
    "no_undue_influence",
    "proportionate_and_limited",
    "review_and_appeal",
    "delegation_and_return",
)
VALID_GATE_STATES = {"met", "unconfirmed", "violated"}
PROCEDURAL_PARTICIPATION_NAMES: tuple[str, ...] = (
    "meaningful_contribution",
    "comprehensible_information",
    "real_options",
    "refusal_and_modification",
    "expression_support",
    "time_and_reconsideration",
)

DEFAULT_M0_CONFIG = (
    Path(__file__).resolve().parents[1]
    / "experiments"
    / "config"
    / "m0_baseline_v0.1.json"
)


def validate_normalized_value(value: float, name: str) -> float:
    """Return a finite value in the model's normalized interval [-1, 1]."""

    numeric = float(value)
    if not math.isfinite(numeric):
        raise ValueError(f"{name} must be finite")
    if not -1.0 <= numeric <= 1.0:
        raise ValueError(f"{name} must be in [-1, 1]")
    return numeric


def validate_options(options: Sequence[float]) -> tuple[float, ...]:
    """Validate a nonempty, finite, unique set of normalized options."""

    numeric = tuple(
        validate_normalized_value(value, f"options[{index}]")
        for index, value in enumerate(options)
    )
    if not numeric:
        raise ValueError("options must not be empty")
    if len(set(numeric)) != len(numeric):
        raise ValueError("options must be unique")
    return numeric


def clip(value: float, lower: float = -1.0, upper: float = 1.0) -> float:
    """Keep a numeric value inside the closed interval [lower, upper]."""

    if not all(math.isfinite(float(item)) for item in (value, lower, upper)):
        raise ValueError("value and bounds must be finite")
    if lower > upper:
        raise ValueError("lower must not exceed upper")
    return min(max(value, lower), upper)


def nearest_options(
    value: float, options: Sequence[float] = OPTIONS, *, tolerance: float = 1e-12
) -> tuple[float, ...]:
    """Return every feasible option tied for the shortest distance to value."""

    normalized_value = validate_normalized_value(value, "value")
    numeric_options = validate_options(options)
    if not math.isfinite(float(tolerance)) or tolerance < 0.0:
        raise ValueError("tolerance must be finite and non-negative")
    distances = [
        (option, abs(normalized_value - option)) for option in numeric_options
    ]
    minimum = min(distance for _, distance in distances)
    return tuple(
        option
        for option, distance in distances
        if abs(distance - minimum) <= tolerance
    )


@dataclass(frozen=True)
class ActorParameters:
    code: str
    label: str
    old_model: float
    observation_error: float
    learning_rate: float
    risk: float
    risk_weight: float

    def validate(self) -> None:
        if self.code not in {"A", "F", "C"}:
            raise ValueError(f"unknown actor code: {self.code}")
        validate_normalized_value(self.old_model, "old_model")
        if not math.isfinite(self.observation_error):
            raise ValueError("observation_error must be finite")
        if not math.isfinite(self.learning_rate) or not 0.0 <= self.learning_rate <= 1.0:
            raise ValueError("learning_rate must be in [0, 1]")
        if not math.isfinite(self.risk) or not 0.0 <= self.risk <= 1.0:
            raise ValueError("risk must be in [0, 1]")
        if not math.isfinite(self.risk_weight) or not 0.0 <= self.risk_weight <= 1.0:
            raise ValueError("risk_weight must be in [0, 1]")


@dataclass(frozen=True)
class ActorResult:
    observation: float
    updated_model: float
    risk_deduction: float
    proposal_value: float
    proposed_options: tuple[float, ...]

    def as_dict(self) -> dict[str, object]:
        return {
            "observation": round(self.observation, 6),
            "updated_model": round(self.updated_model, 6),
            "risk_deduction": round(self.risk_deduction, 6),
            "proposal_value": round(self.proposal_value, 6),
            "proposed_options": list(self.proposed_options),
        }


def evaluate_actor(
    person_will: float,
    actor: ActorParameters,
    options: Sequence[float] = OPTIONS,
) -> ActorResult:
    """Apply the observation, model-update, and proposal equations."""

    validate_normalized_value(person_will, "person_will")
    actor.validate()
    validate_options(options)

    observation = clip(person_will + actor.observation_error)
    updated_model = (
        (1.0 - actor.learning_rate) * actor.old_model
        + actor.learning_rate * observation
    )
    risk_deduction = actor.risk_weight * actor.risk
    proposal_value = clip(updated_model - risk_deduction)
    proposed_options = nearest_options(proposal_value, options)
    return ActorResult(
        observation=observation,
        updated_model=updated_model,
        risk_deduction=risk_deduction,
        proposal_value=proposal_value,
        proposed_options=proposed_options,
    )


@dataclass(frozen=True)
class PersonResponse:
    action: str
    option: float | None = None

    def validate(self, options: Sequence[float]) -> None:
        numeric_options = validate_options(options)
        allowed = {"accept", "reject", "modify", "delegate", "defer", "unconfirmed"}
        if self.action not in allowed:
            raise ValueError(f"unknown person response: {self.action}")
        if self.action in {"accept", "modify"}:
            if self.option is None:
                raise ValueError("accept or modify requires a feasible option")
            validate_normalized_value(self.option, "person response option")
        if self.action in {"accept", "modify"} and self.option not in numeric_options:
            raise ValueError("accept or modify requires a feasible option")
        if self.action not in {"accept", "modify"} and self.option is not None:
            raise ValueError(
                f"{self.action} is not a choice response and must not include an option"
            )


@dataclass(frozen=True)
class Delegation:
    delegate: str
    scopes: tuple[str, ...]
    within_time_limit: bool
    person_chosen: bool
    revoked: bool
    revocable: bool
    delegate_is_ai: bool = False

    def is_valid_for(self, decision_scope: str) -> bool:
        delegate_name = self.delegate.strip()
        return all(
            (
                bool(delegate_name),
                self.person_chosen,
                not self.delegate_is_ai,
                decision_scope in self.scopes,
                self.within_time_limit,
                not self.revoked,
                self.revocable,
            )
        )


@dataclass(frozen=True)
class RightsGates:
    states: Mapping[str, str]

    def validate(self) -> None:
        missing = set(GATE_NAMES) - set(self.states)
        extra = set(self.states) - set(GATE_NAMES)
        if missing or extra:
            raise ValueError(f"rights gates mismatch; missing={missing}, extra={extra}")
        invalid = {state for state in self.states.values() if state not in VALID_GATE_STATES}
        if invalid:
            raise ValueError(f"invalid rights gate states: {invalid}")

    @property
    def all_met(self) -> bool:
        self.validate()
        return all(self.states[name] == "met" for name in GATE_NAMES)


@dataclass(frozen=True)
class DecisionResult:
    value: float | None
    rule: str
    status: str
    reason: str
    pause_consequence_status: str = "not_applicable"
    pause_duration_status: str = "not_applicable"

    def as_dict(self) -> dict[str, object]:
        return {
            "value": self.value,
            "rule": self.rule,
            "status": self.status,
            "reason": self.reason,
            "pause_consequence_status": self.pause_consequence_status,
            "pause_duration_status": self.pause_duration_status,
        }


def decide(
    *,
    options: Sequence[float],
    person_response: PersonResponse,
    delegation: Delegation,
    decision_scope: str,
    delegated_option: float | None,
    rights_gates: RightsGates,
) -> DecisionResult:
    """Apply the v0.1 decision hierarchy without averaging actor proposals."""

    numeric_options = validate_options(options)
    rights_gates.validate()
    person_response.validate(numeric_options)
    if delegated_option is not None:
        validate_normalized_value(delegated_option, "delegated_option")

    if not rights_gates.all_met:
        return DecisionResult(
            value=None,
            rule="none",
            status="paused",
            reason="a rights gate is unconfirmed or violated",
            pause_consequence_status="not_modeled",
            pause_duration_status="not_modeled",
        )

    if person_response.action in {"accept", "modify"}:
        return DecisionResult(
            value=person_response.option,
            rule="person",
            status="decided",
            reason="supported latest person response",
        )

    if person_response.action in {"reject", "defer", "unconfirmed"}:
        return DecisionResult(
            value=None,
            rule="person",
            status="paused",
            reason=(
                f"latest person response is {person_response.action}; "
                "no delegation is applied"
            ),
            pause_consequence_status="not_modeled",
            pause_duration_status="not_modeled",
        )

    if not delegation.is_valid_for(decision_scope):
        return DecisionResult(
            value=None,
            rule="delegation",
            status="paused",
            reason="the requested delegation is not valid for this decision",
            pause_consequence_status="not_modeled",
            pause_duration_status="not_modeled",
        )

    if person_response.action == "delegate":
        if delegated_option not in numeric_options:
            return DecisionResult(
                value=None,
                rule="delegation",
                status="paused",
                reason="the delegated choice is not feasible",
                pause_consequence_status="not_modeled",
                pause_duration_status="not_modeled",
            )
        return DecisionResult(
            value=delegated_option,
            rule="delegation",
            status="decided",
            reason="valid delegation for this scope",
        )

    raise RuntimeError("unreachable person response branch")


def outcome_congruence(decision: float, person_will: float) -> float:
    normalized_decision = validate_normalized_value(decision, "decision")
    normalized_will = validate_normalized_value(person_will, "person_will")
    return 1.0 - abs(normalized_decision - normalized_will) / 2.0


BASELINE_PERSON_WILL = 0.80
BASELINE_ACTORS: tuple[ActorParameters, ...] = (
    ActorParameters("A", "AI", 0.40, -0.20, 0.50, 0.60, 0.50),
    ActorParameters("F", "家族", 0.10, -0.60, 0.20, 0.80, 0.90),
    ActorParameters("C", "専門職", 0.50, -0.10, 0.40, 0.50, 0.40),
)
BASELINE_OUTCOMES: Mapping[float, Mapping[str, Mapping[str, float]]] = {
    -1.0: {
        "person": {"safety": 0.95, "occupational_participation": 0.10},
        "family": {"burden": 0.20},
    },
    0.0: {
        "person": {"safety": 0.75, "occupational_participation": 0.80},
        "family": {"burden": 0.40},
    },
    1.0: {
        "person": {"safety": 0.40, "occupational_participation": 1.00},
        "family": {"burden": 0.80},
    },
}

# The hand-calculation scenario explicitly describes explanation, three options,
# a substantive response, and a successful revision. It does not describe
# expression support or time for reconsideration, so those states remain
# unconfirmed rather than being invented for the baseline.
# The separate rights-gate fixture marks review_and_appeal as available in
# principle; that does not assert that time/reconsideration was actually used
# in this event, so the procedural item remains unconfirmed.
BASELINE_PROCEDURAL_PARTICIPATION: Mapping[str, str] = {
    "meaningful_contribution": "met",
    "comprehensible_information": "met",
    "real_options": "met",
    "refusal_and_modification": "met",
    "expression_support": "unconfirmed",
    "time_and_reconsideration": "unconfirmed",
}


def met_rights_gates() -> RightsGates:
    return RightsGates({name: "met" for name in GATE_NAMES})


def baseline_delegation() -> Delegation:
    return Delegation(
        delegate="daughter",
        scopes=("departure_time",),
        within_time_limit=True,
        person_chosen=True,
        revoked=False,
        revocable=True,
    )


def load_baseline_config(path: Path = DEFAULT_M0_CONFIG) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def file_sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _actor_from_config(item: Mapping[str, object]) -> ActorParameters:
    return ActorParameters(
        code=str(item["code"]),
        label=str(item["label"]),
        old_model=float(item["old_model"]),
        observation_error=float(item["observation_error"]),
        learning_rate=float(item["learning_rate"]),
        risk=float(item["risk"]),
        risk_weight=float(item["risk_weight"]),
    )


def run_baseline(
    config: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """Run the configured synthetic M0 baseline decision event."""

    active_config = load_baseline_config() if config is None else config
    options = validate_options(active_config["options"])
    person_will = validate_normalized_value(
        active_config["person_will"], "person_will"
    )
    actors = tuple(_actor_from_config(item) for item in active_config["actors"])
    response_config = active_config["person_response"]
    person_response = PersonResponse(
        str(response_config["action"]),
        None
        if response_config.get("option") is None
        else float(response_config["option"]),
    )
    delegation_config = active_config["delegation"]
    delegation = Delegation(
        delegate=str(delegation_config["delegate"]),
        scopes=tuple(str(scope) for scope in delegation_config["scopes"]),
        within_time_limit=bool(delegation_config["within_time_limit"]),
        person_chosen=bool(delegation_config["person_chosen"]),
        revoked=bool(delegation_config["revoked"]),
        revocable=bool(delegation_config["revocable"]),
        delegate_is_ai=bool(delegation_config["delegate_is_ai"]),
    )
    rights_gates = RightsGates(
        {str(name): str(state) for name, state in active_config["rights_gates"].items()}
    )
    decision_context = active_config["decision_context"]
    decision_scope = str(decision_context["decision_target"])
    delegated_option_raw = delegation_config.get("delegated_option")
    delegated_option = (
        None if delegated_option_raw is None else float(delegated_option_raw)
    )
    actor_results = {
        actor.code: evaluate_actor(person_will, actor, options) for actor in actors
    }
    decision = decide(
        options=options,
        person_response=person_response,
        delegation=delegation,
        decision_scope=decision_scope,
        delegated_option=delegated_option,
        rights_gates=rights_gates,
    )
    if decision.value is None:
        raise RuntimeError("baseline scenario must produce a decision")

    outcomes_by_option = active_config["outcomes_by_option"]
    outcome_key = str(float(decision.value))
    if outcome_key not in outcomes_by_option:
        raise ValueError("the decided option has no configured outcome fixture")
    selected_outcomes = outcomes_by_option[outcome_key]
    participation = active_config["procedural_participation"]
    if set(participation) != set(PROCEDURAL_PARTICIPATION_NAMES):
        raise ValueError("procedural_participation must contain the six named items")
    return {
        "model": active_config["model"],
        "model_version": active_config["model_version"],
        "specification_version": active_config["specification_version"],
        "generator_module": active_config["generator_module"],
        "source_release_status": active_config["source_release_status"],
        "output_schema_version": "CCE-M0-output-v0.1",
        "synthetic_example": bool(active_config["synthetic_only"]),
        "model_scope": {
            "module": "M0",
            "event_scope": "single_decision_event",
            "actor_proposals": "computed_from_synthetic_inputs",
            "proposal_actors": ["AI", "family", "professional"],
            "person_response": "exogenous_synthetic_input",
            "endogenous_four_actor_interaction": False,
            "pause_consequence_and_duration": "not_modeled",
            "outcome_table_role": "illustrative_non_normative_synthetic_fixture",
        },
        "input_provenance": {
            "decision_context": "synthetic_input_with_unparameterized_fields",
            "environment": "synthetic_input_with_unparameterized_fields",
            "person_will": "synthetic_input",
            "actor_parameters": "synthetic_input",
            "person_response": "exogenous_synthetic_input",
            "delegation": "synthetic_input",
            "rights_gates": "synthetic_input",
            "procedural_participation": "synthetic_input",
            "outcome_values": "synthetic_input",
        },
        "decision_context": {
            "decision_target": decision_scope,
            "deadline": decision_context["deadline"],
            "affected_parties": list(decision_context["affected_parties"]),
            "status": "synthetic_input_with_unparameterized_fields",
        },
        "environment": {
            "feasible_options": list(options),
            "other_constraints": {"value": None, "status": "not_parameterized"},
            "status": "synthetic_input_with_unparameterized_fields",
        },
        "person_will": person_will,
        "options": list(options),
        "actors": {code: result.as_dict() for code, result in actor_results.items()},
        "person_response": {
            "action": person_response.action,
            "option": person_response.option,
            "source": "exogenous_synthetic_input",
        },
        "delegation": {
            "delegate": delegation.delegate,
            "scopes": list(delegation.scopes),
            "within_time_limit": delegation.within_time_limit,
            "person_chosen": delegation.person_chosen,
            "revoked": delegation.revoked,
            "revocable": delegation.revocable,
            "delegate_is_ai": delegation.delegate_is_ai,
            "delegate_is_ai_provenance": "unverified_exogenous_synthetic_input",
            "decision_scope": decision_scope,
            "delegated_option": delegated_option,
            "valid_for_decision_scope": delegation.is_valid_for(decision_scope),
            "status": "synthetic_input",
        },
        "rights_gates": {
            "states": dict(rights_gates.states),
            "all_met": rights_gates.all_met,
            "status": "synthetic_input",
        },
        "procedural_participation": {
            name: {
                "state": str(participation[name]),
                "status": "synthetic_input",
            }
            for name in PROCEDURAL_PARTICIPATION_NAMES
        },
        "decision": decision.as_dict(),
        "outcomes": {
            "aggregation": "none",
            "outcome_congruence": {
                "value": round(
                    outcome_congruence(decision.value, person_will), 6
                ),
                "status": "computed_from_synthetic_input",
            },
            "actor_specific": {
                "person": {
                    "safety": {
                        "value": selected_outcomes["person"]["safety"],
                        "status": "synthetic_input",
                    },
                    "occupational_participation": {
                        "value": selected_outcomes["person"][
                            "occupational_participation"
                        ],
                        "status": "synthetic_input",
                    },
                },
                "family": {
                    "burden": {
                        "value": selected_outcomes["family"]["burden"],
                        "status": "synthetic_input",
                    }
                },
                "professional": {
                    "burden": {"value": None, "status": "not_parameterized"}
                },
                "ecosystem": {
                    "stability": {"value": None, "status": "not_parameterized"}
                },
            },
        },
    }


def lambda_sweep(actor_code: str, steps: int) -> Iterable[dict[str, object]]:
    if steps < 2:
        raise ValueError("steps must be at least 2")
    try:
        baseline_actor = next(actor for actor in BASELINE_ACTORS if actor.code == actor_code)
    except StopIteration as exc:
        raise ValueError("actor must be one of A, F, C") from exc

    for index in range(steps):
        learning_rate = index / (steps - 1)
        actor = replace(baseline_actor, learning_rate=learning_rate)
        result = evaluate_actor(BASELINE_PERSON_WILL, actor)
        yield {
            "actor": actor.code,
            "learning_rate": round(learning_rate, 6),
            "observation": round(result.observation, 6),
            "updated_model": round(result.updated_model, 6),
            "proposal_value": round(result.proposal_value, 6),
            "proposed_options": "|".join(str(option) for option in result.proposed_options),
        }


def write_baseline_results(
    result: Mapping[str, object], output_dir: Path, *, config_path: Path
) -> None:
    """Write the canonical M0 result and its machine-readable provenance."""

    output_dir.mkdir(parents=True, exist_ok=True)
    (output_dir / "baseline.json").write_bytes(
        (json.dumps(result, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )
    metadata = {
        "model": result["model"],
        "model_version": result["model_version"],
        "specification_version": result["specification_version"],
        "config_sha256": file_sha256(config_path),
        "generator_module": result["generator_module"],
        "source_release_status": result["source_release_status"],
        "synthetic_only": result["synthetic_example"],
        "experiment_group": "M0_configured_hand_calculation_baseline",
        "saved_output_count": 1,
        "files": ["baseline.json"],
    }
    (output_dir / "metadata.json").write_bytes(
        (json.dumps(metadata, ensure_ascii=False, indent=2) + "\n").encode("utf-8")
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)

    baseline_parser = subparsers.add_parser(
        "baseline", help="print or save the configured synthetic baseline as JSON"
    )
    baseline_parser.add_argument("--config", type=Path, default=DEFAULT_M0_CONFIG)
    baseline_parser.add_argument("--output-dir", type=Path)
    sweep_parser = subparsers.add_parser(
        "sweep", help="print a learning-rate sweep as CSV"
    )
    sweep_parser.add_argument("--actor", choices=("A", "F", "C"), default="A")
    sweep_parser.add_argument("--steps", type=int, default=11)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "baseline":
        result = run_baseline(load_baseline_config(args.config))
        if args.output_dir:
            write_baseline_results(result, args.output_dir, config_path=args.config)
        else:
            json.dump(result, sys.stdout, ensure_ascii=False, indent=2)
            sys.stdout.write("\n")
        return 0

    rows = list(lambda_sweep(args.actor, args.steps))
    writer = csv.DictWriter(
        sys.stdout, fieldnames=list(rows[0]), lineterminator="\n"
    )
    writer.writeheader()
    writer.writerows(rows)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
