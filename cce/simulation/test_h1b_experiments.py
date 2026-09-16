from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from .h1b_experiments import (
    DEFAULT_CONFIG,
    coupled_response,
    counterfactual_decision_from_baseline,
    file_sha256,
    load_config,
    option_loss,
    run_all,
    rights_gates,
    write_results,
)


class H1BExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config()
        cls.result = run_all(cls.config)
        cls.h1b_1 = cls.result["h1b_1"]
        cls.h1b_2 = cls.result["h1b_2"]

    def test_coupled_response_matches_hand_calculation(self) -> None:
        self.assertAlmostEqual(coupled_response(1.0, -1.0, 0.2), 0.6)
        self.assertAlmostEqual(coupled_response(1.0, -1.0, 0.5), 0.0)
        self.assertAlmostEqual(coupled_response(1.0, -1.0, 0.8), -0.6)

    def test_coupling_range_is_validated(self) -> None:
        with self.assertRaises(ValueError):
            coupled_response(1.0, -1.0, 1.1)

    def test_option_loss_matches_two_of_three_removed(self) -> None:
        self.assertAlmostEqual(option_loss((-1.0, 0.0, 1.0), (-1.0,)), 2 / 3)

    def test_option_loss_rejects_duplicate_options(self) -> None:
        with self.assertRaisesRegex(ValueError, "options must be unique"):
            option_loss((-1.0, -1.0, 1.0), (-1.0,))

    def test_counterfactual_tie_uses_decision_rule_and_is_unscored(self) -> None:
        gates = rights_gates(
            self.config["h1b_1_response_coupling"]["rights_gates"]
        )
        self.assertIsNone(
            counterfactual_decision_from_baseline(0.0, (-1.0, 1.0), gates)
        )

    def test_h1b_1_has_declared_unique_conditions(self) -> None:
        pairs = {(row["proposal_value"], row["coupling"]) for row in self.h1b_1}
        expected = self.config["h1b_1_response_coupling"]["expected_conditions"]
        self.assertEqual(len(self.h1b_1), expected)
        self.assertEqual(len(pairs), expected)

    def test_opposed_response_effect_equals_coupling(self) -> None:
        opposed = [
            row for row in self.h1b_1 if row["proposal_relationship"] == "opposed"
        ]
        self.assertEqual(len(opposed), 11)
        for row in opposed:
            self.assertAlmostEqual(row["response_effect"], row["coupling"])

    def test_opposed_decision_effect_matches_internally_prespecified_steps(self) -> None:
        opposed = [
            row for row in self.h1b_1 if row["proposal_relationship"] == "opposed"
        ]
        for row in opposed:
            coupling = row["coupling"]
            expected = 0.0 if coupling <= 0.2 else 0.5 if coupling <= 0.7 else 1.0
            self.assertEqual(row["decision_effect"], expected)
            self.assertEqual(row["decision_mismatch"], expected)

    def test_aligned_proposal_never_changes_response_or_decision(self) -> None:
        aligned = [
            row for row in self.h1b_1 if row["proposal_relationship"] == "aligned"
        ]
        self.assertEqual(len(aligned), 11)
        for row in aligned:
            self.assertEqual(row["post_proposal_response"], 1.0)
            self.assertEqual(row["response_effect"], 0.0)
            self.assertEqual(row["decision_effect"], 0.0)
            self.assertEqual(row["decision_value"], 1.0)

    def test_intermediate_tie_is_paused_and_not_scored(self) -> None:
        row = next(
            row
            for row in self.h1b_1
            if row["proposal_relationship"] == "intermediate"
            and row["coupling"] == 0.5
        )
        self.assertEqual(row["nearest_options"], "0.0|1.0")
        self.assertEqual(row["decision_status"], "paused")
        self.assertIsNone(row["decision_value"])
        self.assertIsNone(row["decision_effect"])
        self.assertIsNone(row["decision_mismatch"])
        self.assertEqual(
            row["person_response_source"],
            "analysis_substitution_from_discretized_equation_output",
        )
        self.assertTrue(row["analysis_substituted_response"])
        self.assertEqual(row["pause_source"], "discretization_tie")

    def test_h1b_1_keeps_options_and_rejection_available(self) -> None:
        self.assertTrue(
            all(
                row["option_loss_structural_constant"] == 0.0
                for row in self.h1b_1
            )
        )
        self.assertTrue(
            all(
                row["rejection_blockage_structural_constant"] == 0
                for row in self.h1b_1
            )
        )
        self.assertTrue(
            all(not row["rights_violation_structural_constant"] for row in self.h1b_1)
        )
        self.assertTrue(all(row["analysis_row_valid"] for row in self.h1b_1))

    def test_h1b_2_has_eight_cases_after_declared_review_correction(self) -> None:
        ids = {row["case_id"] for row in self.h1b_2}
        expected = self.config["h1b_2_rights_protection"]["expected_cases"]
        self.assertEqual(len(self.h1b_2), expected)
        self.assertEqual(len(ids), expected)

    def test_h1b_2_rows_match_declared_case_expectations(self) -> None:
        by_id = {row["case_id"]: row for row in self.h1b_2}
        for case in self.config["h1b_2_rights_protection"]["cases"]:
            row = by_id[case["id"]]
            self.assertEqual(row["decision_status"], case["expected_status"])
            self.assertEqual(row["decision_value"], case.get("expected_decision"))
            if "expected_rights_violation" in case:
                self.assertEqual(
                    row["rights_violation"], case["expected_rights_violation"]
                )
            if "expected_option_loss" in case:
                self.assertAlmostEqual(
                    row["option_loss"], case["expected_option_loss"]
                )
            if "expected_rejection_blockage" in case:
                self.assertEqual(
                    row["rejection_blockage"], case["expected_rejection_blockage"]
                )
            self.assertEqual(
                row["analysis_row_valid"],
                case.get("expected_analysis_row_valid", True),
            )

    def test_reject_defer_and_unconfirmed_pause(self) -> None:
        by_id = {row["case_id"]: row for row in self.h1b_2}
        for case_id in (
            "reject_all_gates_met",
            "defer_all_gates_met",
            "unconfirmed_all_gates_met",
        ):
            self.assertEqual(by_id[case_id]["decision_status"], "paused")
            self.assertIsNone(by_id[case_id]["decision_value"])
            self.assertEqual(
                by_id[case_id]["pause_consequence_status"], "not_modeled"
            )

    def test_rights_violations_pause_and_option_loss_is_recorded(self) -> None:
        by_id = {row["case_id"]: row for row in self.h1b_2}
        undue = by_id["undue_influence_gate_violated"]
        narrowing = by_id["ai_option_narrowing"]
        self.assertEqual(undue["decision_status"], "paused")
        self.assertTrue(undue["rights_violation"])
        self.assertEqual(narrowing["decision_status"], "paused")
        self.assertTrue(narrowing["rights_violation"])
        self.assertAlmostEqual(narrowing["option_loss"], 2 / 3)

    def test_option_narrowing_isolated_from_rights_gate_violation(self) -> None:
        by_id = {row["case_id"]: row for row in self.h1b_2}
        isolated = by_id["option_narrowing_all_gates_met"]
        self.assertAlmostEqual(isolated["option_loss"], 2 / 3)
        self.assertFalse(isolated["rights_violation"])
        self.assertEqual(isolated["decision_status"], "decided")
        self.assertEqual(isolated["decision_value"], -1.0)
        self.assertEqual(isolated["pause_consequence_status"], "not_applicable")
        self.assertTrue(isolated["decision_opposes_baseline_response"])
        self.assertTrue(isolated["gate_assertion_conflicts_with_spec_definition"])
        self.assertEqual(isolated["person_response_source"], "synthetic_case_input")
        self.assertFalse(isolated["analysis_substituted_response"])

    def test_negative_control_is_detected_and_excluded(self) -> None:
        negative = next(
            row
            for row in self.h1b_2
            if row["case_id"] == "unsafe_reject_bypass_negative_control"
        )
        self.assertEqual(negative["rejection_blockage"], 1)
        self.assertFalse(negative["analysis_row_valid"])
        self.assertTrue(negative["test_fixture_only"])
        self.assertEqual(negative["decision_rule"], "unsafe_negative_control")

    def test_confirmed_modify_is_a_valid_person_rule_decision(self) -> None:
        confirmed = next(
            row
            for row in self.h1b_2
            if row["case_id"] == "confirmed_modify_all_gates_met"
        )
        self.assertEqual(confirmed["decision_status"], "decided")
        self.assertEqual(confirmed["decision_value"], -1.0)
        self.assertEqual(confirmed["decision_rule"], "person")
        self.assertTrue(confirmed["analysis_row_valid"])

    def test_outputs_are_written_with_expected_row_counts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_results(self.result, output_dir)
            with (output_dir / "h1b_1.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 33)
            with (output_dir / "h1b_2.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 8)
            metadata = json.loads(
                (output_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["h1b_1_rows"], 33)
            self.assertEqual(metadata["h1b_2_rows"], 8)
            self.assertEqual(metadata["invalid_negative_controls"], 1)
            self.assertIn("decision_effect equals decision_mismatch", metadata[
                "h1b_1_decision_metric_degeneracy"
            ])
            self.assertEqual(
                metadata["config_status_at_fixing_time"],
                metadata["provenance_status"],
            )
            self.assertEqual(
                metadata["provenance_status"],
                "mixed_provenance_original_internally_fixed_plus_postreview_diagnostic",
            )
            self.assertEqual(
                metadata["provenance_scope"]["option_narrowing_all_gates_met"],
                "added_after_execution_as_independent_ai_review_diagnostic",
            )
            self.assertEqual(metadata["config_sha256"], file_sha256(DEFAULT_CONFIG))
            self.assertEqual(metadata["model_version"], "CCE-MVM-v0.1")
            self.assertEqual(
                metadata["specification_version"], "CCE-SPECIFICATION-v0.1"
            )
            self.assertEqual(
                metadata["generator_module"],
                "cce.simulation.h1b_experiments",
            )
            self.assertEqual(
                metadata["source_release_status"],
                "unreleased_internal_candidate",
            )
            self.assertEqual(
                metadata["implementation_status"],
                "executed_original_internally_fixed_conditions_plus_postreview_diagnostic",
            )
            self.assertNotIn("python_version", metadata)
            self.assertNotIn("operating_system", metadata)


if __name__ == "__main__":
    unittest.main()
