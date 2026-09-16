import json
import tempfile
import unittest
from pathlib import Path

from cce.simulation.h1_h2_experiments import (
    DEFAULT_CONFIG,
    file_sha256,
    first_recovery_step,
    load_config,
    recovery_measure,
    run_all,
    simulate_sequence,
    validate_learning_rates,
    write_results,
)


class H1H2ExperimentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.result = run_all(load_config())
        cls.h1 = [
            row for row in cls.result["summary"] if row["experiment"] == "H1a"
        ]
        cls.h2 = [
            row for row in cls.result["summary"] if row["experiment"] == "H2"
        ]

    def test_h1_lower_learning_rate_has_larger_cumulative_lag(self):
        errors = [row["cumulative_model_error"] for row in self.h1]
        self.assertEqual(errors, sorted(errors, reverse=True))
        self.assertGreater(errors[0], errors[-1])

    def test_h1_lower_learning_rate_has_more_proposal_mismatch(self):
        mismatches = [row["proposal_mismatch_steps"] for row in self.h1]
        self.assertEqual(mismatches, sorted(mismatches, reverse=True))

    def test_h2_higher_learning_rate_has_larger_peak_deviation(self):
        deviations = [row["maximum_model_error"] for row in self.h2]
        self.assertEqual(deviations, sorted(deviations))
        self.assertGreater(deviations[-1], deviations[0])

    def test_h2_high_learning_rate_recovers_after_one_normal_observation(self):
        highest = self.h2[-1]
        self.assertEqual(highest["learning_rate"], 1.0)
        self.assertEqual(highest["recovery_steps"], 1)
        self.assertEqual(highest["recovery_status"], "recovered")

    def test_recovery_is_undefined_when_shock_never_exceeds_tolerance(self):
        points = simulate_sequence(
            experiment="H2-test",
            learning_rate=0.05,
            initial_model=0.8,
            references=[0.8, 0.8, 0.8],
            observations=[0.8, -0.8, 0.8],
            risk_deduction=0.0,
        )
        self.assertIsNone(
            first_recovery_step(
                points,
                start=2,
                tolerance=0.1,
                already_recovered_time=1,
            )
        )
        self.assertEqual(
            recovery_measure(
                points,
                start=2,
                tolerance=0.1,
                excursion_check_time=1,
            ),
            (None, "no_qualifying_excursion"),
        )

    def test_nonrecovery_is_distinct_from_no_excursion(self):
        points = simulate_sequence(
            experiment="H1-test",
            learning_rate=0.01,
            initial_model=-0.8,
            references=[0.8, 0.8],
            observations=[0.8, 0.8],
            risk_deduction=0.0,
        )
        self.assertEqual(
            recovery_measure(points, start=0, tolerance=0.1),
            (None, "not_recovered_within_horizon"),
        )

    def test_every_summary_has_recovery_status(self):
        allowed = {
            "recovered",
            "not_recovered_within_horizon",
            "no_qualifying_excursion",
        }
        self.assertTrue(
            all(row["recovery_status"] in allowed for row in self.result["summary"])
        )

    def test_output_files_are_reproducible(self):
        with tempfile.TemporaryDirectory() as directory:
            output_dir = Path(directory)
            write_results(self.result, output_dir)
            self.assertTrue((output_dir / "summary.csv").is_file())
            self.assertTrue((output_dir / "trajectories.csv").is_file())
            self.assertTrue((output_dir / "metadata.json").is_file())
            self.assertIn("H1a", (output_dir / "summary.csv").read_text())
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
                "cce.simulation.h1_h2_experiments",
            )
            self.assertEqual(
                metadata["source_release_status"],
                "unreleased_internal_candidate",
            )
            self.assertNotIn("python_version", metadata)
            self.assertNotIn("operating_system", metadata)

    def test_learning_rates_must_be_unique_and_ascending(self):
        with self.assertRaises(ValueError):
            validate_learning_rates([0.5, 0.2, 0.5])


if __name__ == "__main__":
    unittest.main()
