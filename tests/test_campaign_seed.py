import random
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

from testit import run as run_module
from testit import run_util
from testit import testit_util
from testit.testit import LaunchTestResult, TestItEnv


class CampaignSeedTests(unittest.TestCase):
    def test_none_values_disable_seed(self):
        self.assertIsNone(run_util._normalize_campaign_seed(None))
        self.assertIsNone(run_util._normalize_campaign_seed("None"))
        self.assertIsNone(run_util._normalize_campaign_seed("null"))
        self.assertIsNone(run_util._normalize_campaign_seed(""))

    def test_integer_values_enable_seed(self):
        self.assertEqual(run_util._normalize_campaign_seed(123), 123)
        self.assertEqual(run_util._normalize_campaign_seed("123"), 123)
        self.assertEqual(run_util._normalize_campaign_seed("0x10"), 16)

    def test_invalid_seed_values_are_rejected(self):
        for seed in (-1, 2**32, True, "abc"):
            with self.subTest(seed=seed):
                with self.assertRaises(ValueError):
                    run_util._normalize_campaign_seed(seed)

    def test_seed_campaign_restarts_python_and_numpy_random_sequences(self):
        env = TestItEnv({"target": {"seed": 123}})

        env.seed_campaign()
        first_random_value = random.randint(1, 100)
        first_numpy_values = np.random.randint(0, 100, size=4).tolist()

        env.seed_campaign()
        second_random_value = random.randint(1, 100)
        second_numpy_values = np.random.randint(0, 100, size=4).tolist()

        self.assertEqual(first_random_value, second_random_value)
        self.assertEqual(first_numpy_values, second_numpy_values)

    def test_sim_run_receives_target_name(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            output_file = Path(tmpdir) / "sim.out"
            output_file.write_text("1:2:3\n", encoding="utf-8")

            env = TestItEnv(
                {
                    "target": {
                        "type": "sim",
                        "name": "verilator",
                        "outputFile": str(output_file),
                    },
                    "report": {"dir": tmpdir},
                }
            )

            completed = subprocess.CompletedProcess(
                args="make",
                returncode=0,
                stdout="",
                stderr="",
            )

            with mock.patch(
                "testit.testit.subprocess.run", return_value=completed
            ) as run_mock:
                result = env.launch_test(
                    app_name="demo",
                    iteration=0,
                    pattern=r"(\d+):(\d+):(\d+)",
                    output_tags=["ID", "Cycles", "Outcome"],
                )

            self.assertEqual(result, LaunchTestResult.SUCCESS)
            self.assertEqual(
                [call.args[0] for call in run_mock.call_args_list],
                [
                    "make sw-sim tool=verilator app=demo",
                    "make sim-run tool=verilator app=demo",
                ],
            )

    def test_sim_compile_failure_returns_specific_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TestItEnv(
                {
                    "target": {
                        "type": "sim",
                        "name": "verilator",
                        "outputFile": str(Path(tmpdir) / "sim.out"),
                    },
                    "report": {"dir": tmpdir},
                }
            )

            failed_compile = subprocess.CompletedProcess(
                args="make",
                returncode=2,
                stdout="compile failed",
                stderr="",
            )

            with mock.patch(
                "testit.testit.subprocess.run", return_value=failed_compile
            ), mock.patch("builtins.open", mock.mock_open()):
                result = env.launch_test(
                    app_name="demo",
                    iteration=0,
                    pattern=r"(\d+):(\d+):(\d+)",
                    output_tags=["ID", "Cycles", "Outcome"],
                )

            self.assertEqual(result, LaunchTestResult.SIM_COMPILATION_FAILED)

    def test_sim_run_failure_returns_specific_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TestItEnv(
                {
                    "target": {
                        "type": "sim",
                        "name": "verilator",
                        "outputFile": str(Path(tmpdir) / "sim.out"),
                    },
                    "report": {"dir": tmpdir},
                }
            )

            completed = subprocess.CompletedProcess(
                args="make",
                returncode=0,
                stdout="",
                stderr="",
            )
            failed_run = subprocess.CompletedProcess(
                args="make",
                returncode=1,
                stdout="run failed",
                stderr="",
            )

            with mock.patch(
                "testit.testit.subprocess.run",
                side_effect=[completed, failed_run],
            ), mock.patch("builtins.open", mock.mock_open()):
                result = env.launch_test(
                    app_name="demo",
                    iteration=0,
                    pattern=r"(\d+):(\d+):(\d+)",
                    output_tags=["ID", "Cycles", "Outcome"],
                )

            self.assertEqual(result, LaunchTestResult.SIM_RUN_FAILED)

    def test_missing_sim_output_returns_specific_code(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            env = TestItEnv(
                {
                    "target": {
                        "type": "sim",
                        "name": "verilator",
                        "outputFile": str(Path(tmpdir) / "missing.out"),
                    },
                    "report": {"dir": tmpdir},
                }
            )

            completed = subprocess.CompletedProcess(
                args="make",
                returncode=0,
                stdout="",
                stderr="",
            )

            with mock.patch(
                "testit.testit.subprocess.run",
                side_effect=[completed, completed],
            ):
                result = env.launch_test(
                    app_name="demo",
                    iteration=0,
                    pattern=r"(\d+):(\d+):(\d+)",
                    output_tags=["ID", "Cycles", "Outcome"],
                )

            self.assertEqual(result, LaunchTestResult.SIM_OUTPUT_FILE_MISSING)

    def test_launch_test_error_messages_are_specific(self):
        data = {"target": {"outputFile": "sim.out"}}

        sim_message = run_module._launch_test_error_message(
            LaunchTestResult.SIM_RUN_FAILED, "demo", data
        )
        fpga_message = run_module._launch_test_error_message(
            LaunchTestResult.FPGA_GDB_LOAD_TIMEOUT, "demo", data
        )

        self.assertIn("simulation run", sim_message)
        self.assertNotIn("GDB timeout", sim_message)
        self.assertIn("GDB timed out", fpga_message)

    def test_sweep_parameters_cover_all_combinations(self):
        parameters = [
            {"name": "ROWS", "value": [2, 4], "step": 1},
            {"name": "COLS", "value": [8, 4], "step": 2},
            {"name": "MODE", "value": "fast"},
        ]

        self.assertEqual(
            [
                testit_util.get_sweep_parameters(iteration, parameters)
                for iteration in range(9)
            ],
            [
                [2, 8, "fast"],
                [3, 8, "fast"],
                [4, 8, "fast"],
                [2, 6, "fast"],
                [3, 6, "fast"],
                [4, 6, "fast"],
                [2, 4, "fast"],
                [3, 4, "fast"],
                [4, 4, "fast"],
            ],
        )

    def test_sweep_mode_dataset_generation_uses_sweep_parameters(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            test_dir = Path(tmpdir) / "app"
            test_dir.mkdir()
            env = TestItEnv(
                {
                    "target": {"type": "sim"},
                    "report": {"dir": tmpdir},
                    "tests": [
                        {
                            "appName": "demo",
                            "dir": str(test_dir),
                            "genFilesName": "test_data",
                            "parameters": [
                                {"name": "SIZE", "value": [2, 4], "step": 1},
                            ],
                            "inputDataset": [
                                {
                                    "name": "input_data",
                                    "dataType": "uint8_t",
                                    "valueRange": [0, 10],
                                    "dimensions": ["SIZE"],
                                }
                            ],
                        }
                    ],
                }
            )

            self.assertTrue(env.gen_datasets(sweep_mode=True, test_iteration=1))
            header = (test_dir / "test_data.h").read_text(encoding="utf-8")
            self.assertIn("#define SIZE 3", header)


if __name__ == "__main__":
    unittest.main()
