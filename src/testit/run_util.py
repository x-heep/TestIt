# Copyright (C) 2025 Politecnico di Torino
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program. If not, see <https://www.gnu.org/licenses/>.

import hjson
import os
import re
import importlib_resources as resources
import shutil
import time
import subprocess
import threading
import rich

from . import testit_util

# Set this to True to enable debugging prints
DEBUG_MODE = False  # TODO: REMOVE THIS LINE BEFORE RELEASE

_MAX_NUMPY_SEED = 2**32 - 1


# Redefine print() to be enabled only during debugging
def _PRINT(*args, **kwargs):
    if DEBUG_MODE:
        print(*args, **kwargs)


# Parses a configuration file from testit/config/ as HJSON; returns None if it is missing
def _load_config(config_name):
    config_path = testit_util.config_path(config_name)

    if not os.path.exists(config_path):
        return None

    with open(config_path, "r") as file:
        return hjson.load(file)


# Checks if the targets required by the selected workflow exist in the project Makefile
def _makefile_target_check(target_type):
    required_targets = {
        "sim": {"sim-build", "sw-sim", "sim-run"},
        "fpga": {
            "fpga-build",
            "fpga-load",
            "sw-fpga",
            "deb-setup",
            "gdb-setup",
        },
    }

    if target_type not in required_targets:
        return False

    makefile_targets = set(__extract_makefile_targets())
    return required_targets[target_type].issubset(makefile_targets)


# Copies a file from the package directory to the given destination path
def _copy_package_file(filename, destination):
    resource_path = resources.files("testit") / filename
    shutil.copy(resource_path, destination)


# Extracts all top-level targets from a Makefile.
def __extract_makefile_targets():
    targets = []

    with open(f"{os.getcwd()}/Makefile", "r") as file:
        for line in file:
            match = re.match(r"^([a-zA-Z0-9_\-]+):", line)
            if match:
                targets.append(match.group(1))

    return targets


# Background thread to update time estimation frequently
def _update_time_estimation(progress, task_id):
    while not progress.tasks[task_id].finished:
        progress.refresh()
        time.sleep(0.2)  # Adjust this to control the update frequency


def _normalize_campaign_seed(seed):
    if seed is None:
        return None

    if isinstance(seed, str):
        stripped_seed = seed.strip()
        if stripped_seed.lower() in ("", "none", "null"):
            return None
        try:
            seed = int(stripped_seed, 0)
        except ValueError as exc:
            raise ValueError("seed must be None/null or an integer") from exc

    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("seed must be None/null or an integer")

    if seed < 0 or seed > _MAX_NUMPY_SEED:
        raise ValueError(f"seed must be between 0 and {_MAX_NUMPY_SEED}")

    return seed


def _configuration_check(configuration, sweep_mode):
    if configuration["target"]["type"] not in ["sim", "fpga"]:
        rich.print("   [bold red]ERROR: Invalid target type![/bold red]")
        rich.print(f"   {configuration['target']['type']} is neither 'sim' nor 'fpga'")
        return False

    try:
        configuration["target"]["seed"] = _normalize_campaign_seed(
            configuration["target"].get("seed")
        )
    except ValueError as exc:
        rich.print("   [bold red]ERROR: Invalid campaign seed![/bold red]")
        rich.print(f"   {exc}")
        return False

    if configuration["target"]["type"] == "fpga" and (
        configuration["target"]["usbPort"] == ""
        or configuration["target"]["baudrate"] == ""
    ):
        rich.print("   [bold red]ERROR: invalid usbPort and/or baudrate![/bold red]")
        return False

    for test in configuration.get("tests", []):
        output_mode = test.get("outputMode", "default")
        if output_mode not in ("default", "custom"):
            rich.print(
                "   [bold red]ERROR: unsupported outputMode "
                f"'{output_mode}'![/bold red]"
            )
            rich.print("   outputMode must be either 'default' or 'custom'")
            return False

        if output_mode == "custom":
            for dataset_field in ("inputDataset", "outputDataset"):
                datasets = test.get(dataset_field, [])
                if isinstance(datasets, dict):
                    datasets = [datasets]

                for dataset in datasets:
                    extension = dataset.get("extension")
                    if not isinstance(extension, str) or not extension.strip():
                        rich.print(
                            "   [bold red]ERROR: custom output mode requires an "
                            "extension for every dataset![/bold red]"
                        )
                        rich.print(
                            "   Dataset "
                            f"'{dataset.get('name', '<unnamed>')}' has no extension"
                        )
                        return False

    if sweep_mode:
        for test in configuration["tests"]:
            if not any(
                isinstance(param["value"], list) for param in test["parameters"]
            ):
                rich.print(
                    "   [bold red]ERROR: sweep mode requires every test to have at least one dynamic parameter![/bold red]"
                )
                return False
            for param in test["parameters"]:
                if isinstance(param["value"], list):
                    if "step" not in param or not isinstance(param["step"], int):
                        rich.print(
                            "   [bold red]ERROR: with sweep mode, each parameter requires a 'step' parameter to be defined as an integer![/bold red]"
                        )
                        return False

    return True


# Returns all the possible combinations of tests
def _get_tot_sweep_iterations(data):
    sweep_parameters = []
    for test in data["tests"]:
        tot = 1
        for parameter in test["parameters"]:
            if isinstance(parameter["value"], list):
                tot *= (
                    int(
                        abs(parameter["value"][0] - parameter["value"][1])
                        / parameter["step"]
                    )
                    + 1
                )
        sweep_parameters.append(tot)

    return sweep_parameters
