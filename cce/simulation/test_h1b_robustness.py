from __future__ import annotations

import csv
import json
import tempfile
import unittest
from pathlib import Path

from .h1b_robustness import (
    DEFAULT_CONFIG,
    file_sha256,
    load_config,
    run_all,
    write_results,
)


class H1BRobustnessTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.config = load_config()
        cls.result = run_all(cls.config)
        cls.baseline = cls.result["baseline_sensitivity"]
        cls.options = cls.result["option_grid_sensitivity"]

    def test_internally_fixed_config_status_is_preserved(self) -> None:
        self.assertEqual(
            self.result["provenance_status"],
            "internally_fixed_before_execution_external_registry_not_used",
        )

    def test_config_hash_matches_internally_prespecified_file(self) -> None:
        self.assertEqual(
            self.result["config_sha256"],
            file_sha256(DEFAULT_CONFIG),
        )

    def test_baseline_sensitivity_has_44_unique_conditions(self) -> None:
        ids = {row["condition_id"] for row in self.baseline}
        expected = self.config["baseline_sensitivity"]["expected_conditions"]
        self.assertEqual(len(self.baseline), expected)
        self.assertEqual(len(ids), expected)

    def test_option_grid_sensitivity_has_33_unique_conditions(self) -> None:
        ids = {row["condition_id"] for row in self.options}
        expected = self.config["option_grid_sensitivity"]["expected_conditions"]
        self.assertEqual(len(self.options), expected)
        self.assertEqual(len(ids), expected)

    def test_total_condition_count_is_77(self) -> None:
        self.assertEqual(
            len(self.baseline) + len(self.options),
            self.config["expected_total_conditions"],
        )

    def test_baseline_response_matches_hand_calculation(self) -> None:
        row = next(
            row
            for row in self.baseline
            if row["baseline_response"] == 0.75 and row["coupling"] == 0.2
        )
        self.assertAlmostEqual(row["post_proposal_response"], 0.45)
        self.assertEqual(row["decision_value"], 0.0)

    def test_baseline_response_effect_is_coupling_times_magnitude(self) -> None:
        self.assertEqual(
            self.config["baseline_sensitivity"]["expected_response_effect_rule"],
            "coupling_times_absolute_baseline",
        )
        for row in self.baseline:
            self.assertAlmostEqual(
                row["response_effect"],
                row["coupling"] * abs(row["baseline_response"]),
            )

    def test_absolute_baseline_one_matches_internally_prespecified_steps(self) -> None:
        self.assertEqual(
            self.config["baseline_sensitivity"]["expected_decision_effect_steps"][
                "absolute_baseline_1.0"
            ],
            {"0.0_to_0.2": 0.0, "0.3_to_0.7": 0.5, "0.8_to_1.0": 1.0},
        )
        rows = [row for row in self.baseline if row["baseline_magnitude"] == 1.0]
        for row in rows:
            coupling = row["coupling"]
            expected = 0.0 if coupling <= 0.2 else 0.5 if coupling <= 0.7 else 1.0
            self.assertEqual(row["decision_effect"], expected)

    def test_absolute_baseline_point75_matches_internally_prespecified_steps(self) -> None:
        self.assertEqual(
            self.config["baseline_sensitivity"]["expected_decision_effect_steps"][
                "absolute_baseline_0.75"
            ],
            {"0.0_to_0.1": 0.0, "0.2_to_0.8": 0.5, "0.9_to_1.0": 1.0},
        )
        rows = [row for row in self.baseline if row["baseline_magnitude"] == 0.75]
        for row in rows:
            coupling = row["coupling"]
            expected = 0.0 if coupling <= 0.1 else 0.5 if coupling <= 0.8 else 1.0
            self.assertEqual(row["decision_effect"], expected)

    def test_positive_and_negative_baselines_are_symmetric(self) -> None:
        self.assertTrue(self.config["baseline_sensitivity"]["expected_symmetry"])
        by_key = {
            (row["baseline_response"], row["coupling"]): row
            for row in self.baseline
        }
        for magnitude in (0.75, 1.0):
            for coupling in self.config["couplings"]:
                positive = by_key[(magnitude, coupling)]
                negative = by_key[(-magnitude, coupling)]
                self.assertEqual(
                    positive["response_effect"], negative["response_effect"]
                )
                self.assertEqual(
                    positive["decision_effect"], negative["decision_effect"]
                )
                self.assertEqual(
                    positive["decision_value"], -negative["decision_value"]
                )

    def test_option_grids_have_identical_response_paths(self) -> None:
        by_coupling: dict[float, set[tuple[float, float]]] = {}
        for row in self.options:
            by_coupling.setdefault(row["coupling"], set()).add(
                (row["post_proposal_response"], row["response_effect"])
            )
        self.assertTrue(all(len(values) == 1 for values in by_coupling.values()))

    def test_option_grid_effect_sequences_match_internal_fixing(self) -> None:
        expected = {
            item["id"]: item["expected_effect_sequence"]
            for item in self.config["option_grid_sensitivity"]["option_sets"]
        }
        for option_set_id, sequence in expected.items():
            rows = sorted(
                (
                    row
                    for row in self.options
                    if row["option_set_id"] == option_set_id
                ),
                key=lambda row: row["coupling"],
            )
            self.assertEqual([row["decision_effect"] for row in rows], sequence)

    def test_endpoints_tie_is_the_only_paused_option_condition(self) -> None:
        paused = [
            (row["option_set_id"], row["coupling"])
            for row in self.options
            if row["decision_status"] == "paused"
        ]
        expected = [
            (item["id"], coupling)
            for item in self.config["option_grid_sensitivity"]["option_sets"]
            for coupling in item["expected_paused_couplings"]
        ]
        self.assertEqual(paused, expected)
        tie = next(
            row
            for row in self.options
            if row["option_set_id"] == "endpoints_2" and row["coupling"] == 0.5
        )
        self.assertEqual(tie["pause_source"], "discretization_tie")
        self.assertTrue(tie["analysis_substituted_response"])

    def test_all_conditions_preserve_rights_and_validity(self) -> None:
        rows = self.baseline + self.options
        self.assertTrue(
            all(row["ai_option_loss_structural_constant"] == 0.0 for row in rows)
        )
        self.assertTrue(
            all(not row["rights_violation_structural_constant"] for row in rows)
        )
        self.assertTrue(all(row["analysis_row_valid"] for row in rows))

    def test_outputs_and_metadata_are_written(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_results(self.result, output_dir)
            with (output_dir / "baseline_sensitivity.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 44)
            with (output_dir / "option_grid_sensitivity.csv").open(
                encoding="utf-8", newline=""
            ) as stream:
                self.assertEqual(len(list(csv.DictReader(stream))), 33)
            metadata = json.loads(
                (output_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["total_rows"], 77)
            self.assertEqual(metadata["analysis_valid_rows"], 77)
            self.assertEqual(
                metadata["option_set_role"],
                self.config["option_grid_sensitivity"]["option_set_role"],
            )
            self.assertEqual(
                metadata["config_status_at_fixing_time"],
                metadata["provenance_status"],
            )
            self.assertEqual(
                metadata["config_sha256"],
                file_sha256(DEFAULT_CONFIG),
            )
            self.assertEqual(
                metadata["provenance_status"],
                "internally_fixed_before_execution_external_registry_not_used",
            )
            self.assertEqual(
                metadata["implementation_status"],
                "executed_from_internally_fixed_config",
            )
            self.assertEqual(metadata["model_version"], "CCE-MVM-v0.1")
            self.assertEqual(
                metadata["specification_version"], "CCE-SPECIFICATION-v0.1"
            )
            self.assertEqual(
                metadata["generator_module"],
                "cce.simulation.h1b_robustness",
            )
            self.assertEqual(
                metadata["source_release_status"],
                "unreleased_internal_candidate",
            )
            self.assertNotIn("python_version", metadata)
            self.assertNotIn("operating_system", metadata)


if __name__ == "__main__":
    unittest.main()
