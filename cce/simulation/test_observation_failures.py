import json
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from cce.simulation.observation_failures import (
    DEFAULT_CONFIG,
    file_sha256,
    load_config,
    reference_sequence,
    run_all,
    simulate_run,
    write_results,
)


class ObservationFailureTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.config = load_config()
        cls.result = run_all(cls.config)

    def summaries(self, mechanism):
        return [
            row
            for row in self.result["aggregate"]
            if row["mechanism"] == mechanism
        ]

    def test_output_has_1200_runs_and_12_conditions(self):
        self.assertEqual(len(self.result["per_run"]), 1200)
        self.assertEqual(len(self.result["aggregate"]), 12)
        self.assertTrue(all(row["runs"] == 100 for row in self.result["aggregate"]))

    def test_missingness_increases_median_cumulative_error(self):
        values = [
            row["cumulative_model_error_median"]
            for row in self.summaries("missingness")
        ]
        self.assertEqual(values, sorted(values))

    def test_negative_bias_increases_median_cumulative_error(self):
        values = [
            row["cumulative_model_error_median"]
            for row in self.summaries("systematic_bias")
        ]
        self.assertEqual(values, sorted(values))

    def test_delay_increases_median_cumulative_error(self):
        values = [
            row["cumulative_model_error_median"]
            for row in self.summaries("delay")
        ]
        self.assertEqual(values, sorted(values))

    def test_zero_severity_baselines_are_identical(self):
        baselines = [
            row
            for row in self.result["aggregate"]
            if row["severity"] == 0.0
        ]
        values = {
            row["cumulative_model_error_median"]
            for row in baselines
        }
        self.assertEqual(len(values), 1)

    def test_same_seed_and_condition_are_reproducible(self):
        references = reference_sequence(self.config["scenario"])
        arguments = {
            "mechanism": "systematic_bias",
            "severity": 0.4,
            "seed": 52000,
            "references": references,
            "scenario": self.config["scenario"],
            "noise_config": self.config["common_noise"],
        }
        self.assertEqual(simulate_run(**arguments), simulate_run(**arguments))

    def test_delay_replays_noise_from_the_delayed_sample(self):
        scenario = {
            "change_step": 1,
            "initial_model": -0.8,
            "learning_rate": 0.5,
            "risk_deduction": 0.0,
        }
        noise_config = {
            "mean": 0.0,
            "standard_deviation": 0.1,
            "clip_lower": -1.0,
            "clip_upper": 1.0,
        }
        with mock.patch(
            "cce.simulation.observation_failures.paired_random_sequences",
            return_value=([0.1, -0.5], [1.0, 1.0]),
        ):
            row = simulate_run(
                mechanism="delay",
                severity=1.0,
                seed=1,
                references=[-0.8, 0.8],
                scenario=scenario,
                noise_config=noise_config,
            )
        self.assertAlmostEqual(row["final_model_error"], 1.525)

    def test_missingness_reduces_observed_fraction(self):
        values = [
            row["observed_fraction_evaluation_window_median"]
            for row in self.summaries("missingness")
        ]
        self.assertEqual(values, sorted(values, reverse=True))

    def test_observation_windows_are_named_and_bias_direction_is_preserved(self):
        first = self.result["per_run"][0]
        self.assertIn("observed_fraction_full_sequence", first)
        self.assertIn("observed_fraction_evaluation_window", first)
        biased = next(
            row
            for row in self.result["per_run"]
            if row["mechanism"] == "systematic_bias" and row["severity"] == 0.4
        )
        self.assertEqual(biased["signed_parameter"], -0.4)
        self.assertEqual(
            biased["mechanism_direction"],
            "negative_away_from_postchange_reference",
        )

    def test_result_files_are_written(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_results(self.result, output_dir)
            self.assertTrue((output_dir / "per_run.csv").is_file())
            self.assertTrue((output_dir / "aggregate.csv").is_file())
            self.assertTrue((output_dir / "metadata.json").is_file())
            metadata = json.loads(
                (output_dir / "metadata.json").read_text(encoding="utf-8")
            )
            self.assertEqual(metadata["model_version"], "CCE-MVM-v0.1")
            self.assertEqual(
                metadata["specification_version"], "CCE-SPECIFICATION-v0.1"
            )
            self.assertEqual(metadata["config_sha256"], file_sha256(DEFAULT_CONFIG))
            self.assertEqual(
                metadata["generator_module"],
                "cce.simulation.observation_failures",
            )
            self.assertEqual(
                metadata["source_release_status"],
                "unreleased_internal_candidate",
            )
            self.assertEqual(metadata["effective_condition_count"], 10)
            self.assertNotIn("independent_runs", metadata)
            self.assertEqual(metadata["independent_noise_sequences"], 100)
            self.assertEqual(metadata["nonduplicated_condition_rows"], 1000)
            self.assertEqual(
                metadata["comparison_design"],
                "common_random_numbers_paired_across_conditions",
            )
            self.assertEqual(
                metadata["delay_semantics"],
                "delayed_reference_and_its_original_measurement_noise",
            )
            self.assertNotIn("python_version", metadata)
            self.assertNotIn("operating_system", metadata)


if __name__ == "__main__":
    unittest.main()
