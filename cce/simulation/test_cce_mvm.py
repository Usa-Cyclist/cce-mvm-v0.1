import json
import math
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from cce.simulation.cce_mvm import (
    BASELINE_ACTORS,
    BASELINE_PERSON_WILL,
    DEFAULT_M0_CONFIG,
    OPTIONS,
    PROCEDURAL_PARTICIPATION_NAMES,
    Delegation,
    PersonResponse,
    RightsGates,
    decide,
    evaluate_actor,
    file_sha256,
    load_baseline_config,
    met_rights_gates,
    nearest_options,
    outcome_congruence,
    run_baseline,
    write_baseline_results,
)


class BaselineCalculationTests(unittest.TestCase):
    def test_baseline_matches_hand_calculation(self):
        result = run_baseline()

        self.assertEqual(result["actors"]["A"]["observation"], 0.60)
        self.assertEqual(result["actors"]["F"]["observation"], 0.20)
        self.assertEqual(result["actors"]["C"]["observation"], 0.70)

        self.assertEqual(result["actors"]["A"]["updated_model"], 0.50)
        self.assertEqual(result["actors"]["F"]["updated_model"], 0.12)
        self.assertEqual(result["actors"]["C"]["updated_model"], 0.58)

        self.assertEqual(result["actors"]["A"]["proposal_value"], 0.20)
        self.assertEqual(result["actors"]["F"]["proposal_value"], -0.60)
        self.assertEqual(result["actors"]["C"]["proposal_value"], 0.38)

        self.assertEqual(result["actors"]["A"]["proposed_options"], [0.0])
        self.assertEqual(result["actors"]["F"]["proposed_options"], [-1.0])
        self.assertEqual(result["actors"]["C"]["proposed_options"], [0.0])
        self.assertEqual(result["decision"]["value"], 0.0)
        self.assertEqual(result["decision"]["rule"], "person")
        self.assertEqual(result["outcomes"]["outcome_congruence"]["value"], 0.60)

    def test_learning_rate_zero_preserves_old_model(self):
        actor = replace(BASELINE_ACTORS[0], learning_rate=0.0)
        result = evaluate_actor(BASELINE_PERSON_WILL, actor)
        self.assertAlmostEqual(result.updated_model, actor.old_model)

    def test_learning_rate_one_uses_current_observation(self):
        actor = replace(BASELINE_ACTORS[0], learning_rate=1.0)
        result = evaluate_actor(BASELINE_PERSON_WILL, actor)
        self.assertAlmostEqual(result.updated_model, result.observation)

    def test_equal_distance_returns_both_options(self):
        self.assertEqual(nearest_options(0.5), (0.0, 1.0))

    def test_duplicate_options_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "options must be unique"):
            nearest_options(0.0, (-1.0, -1.0, 1.0))

    def test_nonfinite_and_out_of_range_values_are_rejected(self):
        for value in (math.nan, math.inf, -math.inf, 1.01):
            with self.subTest(value=value):
                with self.assertRaises(ValueError):
                    nearest_options(value)
        with self.assertRaises(ValueError):
            nearest_options(0.0, (-1.0, 2.0))
        with self.assertRaises(ValueError):
            nearest_options(0.0, tolerance=math.nan)
        with self.assertRaises(ValueError):
            nearest_options(0.0, tolerance=-0.1)

    def test_congruence_rejects_invalid_normalized_values(self):
        with self.assertRaises(ValueError):
            outcome_congruence(5.0, 0.8)
        with self.assertRaises(ValueError):
            outcome_congruence(0.0, math.nan)


class DecisionRuleTests(unittest.TestCase):
    def setUp(self):
        self.delegation = Delegation(
            delegate="daughter",
            scopes=("departure_time",),
            within_time_limit=True,
            person_chosen=True,
            revoked=False,
            revocable=True,
        )

    def test_latest_person_choice_does_not_activate_out_of_scope_delegation(self):
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("modify", 0.0),
            delegation=self.delegation,
            decision_scope="outing_method",
            delegated_option=-1.0,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.rule, "person")
        self.assertEqual(result.value, 0.0)

    def test_latest_person_choice_overrides_prior_valid_delegation(self):
        responses = (PersonResponse("accept", -1.0), PersonResponse("modify", 0.0))
        for response in responses:
            with self.subTest(action=response.action):
                result = decide(
                    options=OPTIONS,
                    person_response=response,
                    delegation=self.delegation,
                    decision_scope="departure_time",
                    delegated_option=1.0,
                    rights_gates=met_rights_gates(),
                )
                self.assertEqual(result.rule, "person")
                self.assertEqual(result.value, response.option)

    def test_delegation_is_used_only_for_latest_delegate_response(self):
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("delegate"),
            delegation=self.delegation,
            decision_scope="departure_time",
            delegated_option=1.0,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.rule, "delegation")
        self.assertEqual(result.status, "decided")
        self.assertEqual(result.value, 1.0)

    def test_latest_nonchoice_response_pauses_despite_valid_delegation(self):
        for action in ("reject", "defer", "unconfirmed"):
            with self.subTest(action=action):
                result = decide(
                    options=OPTIONS,
                    person_response=PersonResponse(action),
                    delegation=self.delegation,
                    decision_scope="departure_time",
                    delegated_option=1.0,
                    rights_gates=met_rights_gates(),
                )
                self.assertEqual(result.rule, "person")
                self.assertEqual(result.status, "paused")
                self.assertIsNone(result.value)
                self.assertEqual(result.pause_consequence_status, "not_modeled")
                self.assertEqual(result.pause_duration_status, "not_modeled")

    def test_nonchoice_response_rejects_contradictory_option(self):
        for action in ("reject", "delegate", "defer", "unconfirmed"):
            with self.subTest(action=action):
                with self.assertRaisesRegex(ValueError, "must not include an option"):
                    decide(
                        options=OPTIONS,
                        person_response=PersonResponse(action, 0.0),
                        delegation=self.delegation,
                        decision_scope="departure_time",
                        delegated_option=1.0,
                        rights_gates=met_rights_gates(),
                    )

    def test_invalid_requested_delegation_pauses_instead_of_falling_back(self):
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("delegate"),
            delegation=replace(self.delegation, revoked=True),
            decision_scope="departure_time",
            delegated_option=1.0,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.rule, "delegation")
        self.assertEqual(result.status, "paused")
        self.assertIsNone(result.value)

    def test_requested_delegation_requires_every_safeguard(self):
        invalid_delegations = {
            "missing_delegate": replace(self.delegation, delegate=" "),
            "not_person_chosen": replace(self.delegation, person_chosen=False),
            "out_of_scope": replace(self.delegation, scopes=("outing_method",)),
            "expired": replace(self.delegation, within_time_limit=False),
            "revoked": replace(self.delegation, revoked=True),
            "not_revocable": replace(self.delegation, revocable=False),
            "explicit_ai_flag": replace(
                self.delegation, delegate="automated helper", delegate_is_ai=True
            ),
        }
        for condition, delegation in invalid_delegations.items():
            with self.subTest(condition=condition):
                result = decide(
                    options=OPTIONS,
                    person_response=PersonResponse("delegate"),
                    delegation=delegation,
                    decision_scope="departure_time",
                    delegated_option=1.0,
                    rights_gates=met_rights_gates(),
                )
                self.assertEqual(result.rule, "delegation")
                self.assertEqual(result.status, "paused")
                self.assertIsNone(result.value)

    def test_valid_delegation_with_infeasible_choice_pauses(self):
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("delegate"),
            delegation=self.delegation,
            decision_scope="departure_time",
            delegated_option=0.5,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.rule, "delegation")
        self.assertEqual(result.status, "paused")
        self.assertIsNone(result.value)

    def test_unconfirmed_response_is_not_consent(self):
        invalid_delegation = replace(self.delegation, revoked=True)
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("unconfirmed"),
            delegation=invalid_delegation,
            decision_scope="outing_method",
            delegated_option=None,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.status, "paused")
        self.assertIsNone(result.value)

    def test_ai_cannot_become_delegate(self):
        ai_delegation = replace(
            self.delegation,
            delegate="automated helper",
            scopes=("outing_method",),
            delegate_is_ai=True,
        )
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("delegate"),
            delegation=ai_delegation,
            decision_scope="outing_method",
            delegated_option=1.0,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.rule, "delegation")
        self.assertEqual(result.status, "paused")
        self.assertIsNone(result.value)

    def test_human_named_ai_is_not_misclassified_as_artificial_intelligence(self):
        human_delegation = replace(
            self.delegation,
            delegate="Ai",
            scopes=("outing_method",),
            delegate_is_ai=False,
        )
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("delegate"),
            delegation=human_delegation,
            decision_scope="outing_method",
            delegated_option=1.0,
            rights_gates=met_rights_gates(),
        )
        self.assertEqual(result.rule, "delegation")
        self.assertEqual(result.status, "decided")
        self.assertEqual(result.value, 1.0)

    def test_unconfirmed_rights_gate_pauses_decision(self):
        states = dict(met_rights_gates().states)
        states["no_undue_influence"] = "unconfirmed"
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("modify", 0.0),
            delegation=self.delegation,
            decision_scope="outing_method",
            delegated_option=None,
            rights_gates=RightsGates(states),
        )
        self.assertEqual(result.status, "paused")
        self.assertIsNone(result.value)

    def test_unconfirmed_rights_gate_prevents_requested_delegation(self):
        states = dict(met_rights_gates().states)
        states["review_and_appeal"] = "unconfirmed"
        result = decide(
            options=OPTIONS,
            person_response=PersonResponse("delegate"),
            delegation=self.delegation,
            decision_scope="departure_time",
            delegated_option=1.0,
            rights_gates=RightsGates(states),
        )
        self.assertEqual(result.rule, "none")
        self.assertEqual(result.status, "paused")
        self.assertIsNone(result.value)


class BaselineSchemaTests(unittest.TestCase):
    def setUp(self):
        self.result = run_baseline()

    def test_records_six_procedural_participation_items_separately(self):
        participation = self.result["procedural_participation"]
        self.assertEqual(set(participation), set(PROCEDURAL_PARTICIPATION_NAMES))
        for item in participation.values():
            self.assertIn(item["state"], {"met", "unconfirmed", "violated"})
            self.assertEqual(item["status"], "synthetic_input")

    def test_records_decision_context_and_environment_without_inventing_values(self):
        context = self.result["decision_context"]
        environment = self.result["environment"]
        self.assertEqual(self.result["output_schema_version"], "CCE-M0-output-v0.1")
        self.assertEqual(context["decision_target"], "outing_method")
        self.assertEqual(
            context["deadline"], {"value": None, "status": "not_parameterized"}
        )
        self.assertEqual(context["affected_parties"], ["person", "family"])
        self.assertEqual(environment["feasible_options"], list(OPTIONS))
        self.assertEqual(
            environment["other_constraints"],
            {"value": None, "status": "not_parameterized"},
        )

    def test_records_rights_gates_without_aggregation(self):
        gates = self.result["rights_gates"]
        self.assertEqual(set(gates["states"]), set(met_rights_gates().states))
        self.assertTrue(gates["all_met"])
        self.assertEqual(gates["status"], "synthetic_input")

    def test_records_actor_specific_outcomes_without_composite_score(self):
        outcomes = self.result["outcomes"]
        actor_specific = outcomes["actor_specific"]
        self.assertEqual(outcomes["aggregation"], "none")
        self.assertNotIn("metrics", self.result)
        self.assertEqual(
            actor_specific["person"]["safety"],
            {"value": 0.75, "status": "synthetic_input"},
        )
        self.assertEqual(
            actor_specific["person"]["occupational_participation"],
            {"value": 0.80, "status": "synthetic_input"},
        )
        self.assertEqual(
            actor_specific["family"]["burden"],
            {"value": 0.40, "status": "synthetic_input"},
        )
        self.assertEqual(
            actor_specific["professional"]["burden"],
            {"value": None, "status": "not_parameterized"},
        )
        self.assertEqual(
            actor_specific["ecosystem"]["stability"],
            {"value": None, "status": "not_parameterized"},
        )

    def test_marks_congruence_as_computed_from_synthetic_input(self):
        congruence = self.result["outcomes"]["outcome_congruence"]
        self.assertEqual(congruence["value"], 0.60)
        self.assertEqual(congruence["status"], "computed_from_synthetic_input")

    def test_declares_m0_person_response_as_exogenous(self):
        scope = self.result["model_scope"]
        self.assertEqual(scope["module"], "M0")
        self.assertEqual(scope["actor_proposals"], "computed_from_synthetic_inputs")
        self.assertEqual(scope["proposal_actors"], ["AI", "family", "professional"])
        self.assertEqual(scope["person_response"], "exogenous_synthetic_input")
        self.assertFalse(scope["endogenous_four_actor_interaction"])
        self.assertEqual(scope["pause_consequence_and_duration"], "not_modeled")
        self.assertEqual(
            scope["outcome_table_role"],
            "illustrative_non_normative_synthetic_fixture",
        )
        self.assertEqual(
            self.result["person_response"]["source"],
            "exogenous_synthetic_input",
        )

    def test_records_baseline_delegation_evaluation(self):
        delegation = self.result["delegation"]
        self.assertEqual(delegation["decision_scope"], "outing_method")
        self.assertFalse(delegation["valid_for_decision_scope"])
        self.assertEqual(delegation["status"], "synthetic_input")
        self.assertEqual(
            delegation["delegate_is_ai_provenance"],
            "unverified_exogenous_synthetic_input",
        )

    def test_m0_baseline_is_written_with_config_provenance(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_baseline_results(
                self.result, output_dir, config_path=DEFAULT_M0_CONFIG
            )
            baseline = json.loads(
                (output_dir / "baseline.json").read_text(encoding="utf-8")
            )
            metadata = json.loads(
                (output_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(baseline["decision"]["value"], 0.0)
            self.assertEqual(metadata["saved_output_count"], 1)
            self.assertEqual(metadata["config_sha256"], file_sha256(DEFAULT_M0_CONFIG))
            self.assertEqual(
                metadata["generator_module"],
                "cce.simulation.m0_baseline_experiment",
            )
            self.assertEqual(run_baseline(load_baseline_config()), self.result)


if __name__ == "__main__":
    unittest.main()
