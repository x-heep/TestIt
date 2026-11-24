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

from . import run_util
from rich.progress import (
    Progress,
    BarColumn,
    TimeRemainingColumn,
    TextColumn,
    SpinnerColumn,
)
from rich.status import Status
import rich
from . import testit
from . import testit_util
import os
import threading
import queue
import time

import os
import time
import json
from rich import print
from rich.progress import (
    Progress,
    TextColumn,
    BarColumn,
    TimeRemainingColumn,
    SpinnerColumn,
)
from rich.status import Status


def _launch_test_error_message(result, app_name, data):
    """Build the user-facing error for a launch_test result code."""
    messages = {
        testit.LaunchTestResult.FPGA_SERIAL_PORT_NOT_OPEN: (
            f"Test {app_name} failed because the FPGA serial port is not open"
        ),
        testit.LaunchTestResult.FPGA_COMPILATION_FAILED: (
            f"Test {app_name} failed during FPGA application compilation; "
            "see testit_crash.log"
        ),
        testit.LaunchTestResult.FPGA_GDB_LOAD_TIMEOUT: (
            f"Test {app_name} failed because GDB timed out while loading the "
            "FPGA application"
        ),
        testit.LaunchTestResult.SIM_COMPILATION_FAILED: (
            f"Test {app_name} failed during simulation application compilation; "
            "see testit_crash.log"
        ),
        testit.LaunchTestResult.SIM_RUN_FAILED: (
            f"Test {app_name} failed during simulation run; see testit_crash.log"
        ),
        testit.LaunchTestResult.SIM_OUTPUT_FILE_MISSING: (
            f"Test {app_name} failed because simulation output file "
            f"{data['target'].get('outputFile', '<missing>')} was not found"
        ),
    }
    return messages.get(result, f"Test {app_name} failed with unknown launch result")


def _load_config_or_exit(config_name):
    """Load the named configuration file, exiting with a hint if it is missing."""
    data = run_util._load_config(config_name)
    if data is None:
        missing_path = os.path.relpath(testit_util.config_path(config_name))
        rich.print(f"[bold red]ERROR: {missing_path} not found![/bold red]")
        rich.print("Please run the 'setup' command first.")
        exit(1)
    return data


def testit_run(
    no_build=False,
    italian_mode=False,
    sweep_mode=False,
    config_name=testit_util.DEFAULT_CONFIG_NAME,
):
    data = _load_config_or_exit(config_name)

    report_dir = data["report"]["dir"]
    os.makedirs(report_dir, exist_ok=True)

    if not os.path.exists(testit_util.golden_module_path()):
        missing_path = os.path.relpath(testit_util.golden_module_path())
        rich.print(f"[bold red]ERROR: {missing_path} not found![/bold red]")
        rich.print("Please run the 'setup' command first.")
        exit(1)

    # Create the TestIt object
    testEnv = testit.TestItEnv(data)
    testEnv.clear_results()

    if not italian_mode:
        rich.print("[cyan]Setting up TestIt project...[/cyan]")
    else:
        rich.print(
            "\n[bold green][][/bold green][white][][/white][bold red][][/bold red]\n"
        )
        rich.print("[cyan]Bringing salted water to boil...[/cyan]")

    # Check the configuration before selecting the workflow-specific Makefile targets
    if not run_util._configuration_check(data, sweep_mode):
        rich.print(
            f" - [bold red]ERROR: there is an issue with {config_name} critical parameters![/bold red]"
        )
        exit(1)
    elif not run_util._makefile_target_check(data["target"]["type"]):
        rich.print(
            " - [bold red]ERROR: Target project Makefile check failed![/bold red]"
        )
        rich.print(
            "   Please ensure that the Makefile contains the required "
            f"{data['target']['type']} targets"
        )
        exit(1)
    else:
        if not italian_mode:
            rich.print(
                f" - Target project Makefile and {config_name} check [bold green][OK][/bold green]"
            )
        else:
            rich.print(" - Nonna's recipe [bold green][READ][/bold green]")

    if not no_build:
        # Build the model
        if not italian_mode:
            with Status(" - [cyan]Building model...[/cyan]", spinner="dots") as status:
                build_success = testEnv.build_model()
        else:
            with Status(
                " - [cyan]Making pasta dough...[/cyan]", spinner="dots"
            ) as status:
                build_success = testEnv.build_model()

        if not build_success:
            rich.print(" - [bold red]ERROR: Model build failed![/bold red]")
            exit(1)
        else:
            if not italian_mode:
                rich.print(" - Model build [bold green][OK][/bold green]")
            else:
                rich.print(" - Hand-made pasta [bold green][DONE][/bold green]")
    else:
        if not italian_mode:
            rich.print(" - Model build phase [bold green][SKIPPED][/bold green]")
        else:
            rich.print(" - Using [bold green][DRIED][/bold green] pasta")
        
    # If the target is an FPGA board, load the model, then setup the serial connection and GDB
    if data["target"]["type"] == "fpga":
        if not italian_mode:
            with Status(
                f" - [cyan]Loading model on FPGA board {data['target']['name']}...[/cyan]",
                spinner="dots",
            ) as status:
                load_success = testEnv.load_fpga_model()
        else:
            with Status(
                f" - [cyan]Frying the soffritto in a pan...[/cyan]", spinner="dots"
            ) as status:
                load_success = testEnv.load_fpga_model()

        if not load_success:
            rich.print(
                f" - [bold red]ERROR: Model load on FPGA board {data['target']['name']} failed![/bold red]"
            )
            rich.print(
                "   Please ensure that the FPGA board is connected and powered on"
            )
            exit(1)
        else:
            if not italian_mode:
                rich.print(
                    f" - Model load on FPGA board {data['target']['name']} [bold green][OK][/bold green]"
                )
            else:
                rich.print(f" - Soffritto [bold green][COOKED][/bold green]")

        if not italian_mode:
            with Status(
                " - [cyan]Setting up serial connection...[/cyan]", spinner="dots"
            ) as status:
                serial_setup_success = testEnv.serial_begin()
        else:
            with Status(
                " - [cyan]Opening a couple of pelati cans...[/cyan]", spinner="dots"
            ) as status:
                serial_setup_success = testEnv.serial_begin()

        if not serial_setup_success:
            rich.print(" - [bold red]ERROR: Serial setup failed![/bold red]")
            rich.print("   Please ensure that the serial port is correctly configured")
            exit(1)
        else:
            if not italian_mode:
                rich.print(" - Serial setup [bold green][OK][/bold green]")
            else:
                rich.print(" - Pelati cans [bold green][OPENED][/bold green]")

        deb_setup_success = testEnv.setup_deb()
        if not deb_setup_success:
            rich.print(f" - [bold red]ERROR: Debugger setup failed![/bold red]")
            exit(1)
        else:
            if not italian_mode:
                rich.print(" - Debugger setup [bold green][OK][/bold green]")
            else:
                rich.print(" - Basil leaves [bold green][PICKED][/bold green]")

        if not italian_mode:
            with Status(" - [cyan]Setting up GDB...[/cyan]", spinner="dots") as status:
                gdb_setup_success = testEnv.setup_gdb()
        else:
            with Status(
                " - [cyan]Cooking the pomodoro sauce...[/cyan]", spinner="dots"
            ) as status:
                gdb_setup_success = testEnv.setup_gdb()

        if not gdb_setup_success:
            rich.print(" - [bold red]ERROR: GDB setup failed![/bold red]")
            exit(1)
        else:
            if not italian_mode:
                rich.print(" - GDB setup [bold green][OK][/bold green]")
            else:
                rich.print(" - Pomodoro sauce [bold green][COOKED][/bold green]")
    else:
        if italian_mode:
            rich.print(" - Using [bold green][STORE-BOUGHT][/bold green] tomato sauce")

    if not italian_mode:
        rich.print("[cyan]\nRunning verification campaign...[/cyan]")
    else:
        rich.print("[cyan]\nThrowing in the pasta...[/cyan]")

    testEnv.seed_campaign()

    with Progress(
        TextColumn("[bold cyan]{task.description}"),
        BarColumn(),
        TimeRemainingColumn(),
        SpinnerColumn(),
        transient=True,
        # One sweep iteration often outlasts rich's default 30 s window, which
        # would leave a single sample and no ETA; average over the whole run.
        speed_estimate_period=float("inf"),
    ) as progress:

        # Compute the total test iterations
        if not sweep_mode:
            test_iterations = data["target"]["iterations"]
        else:
            sweep_test_iterations = run_util._get_tot_sweep_iterations(data)

            test_index = 0
            for test in data["tests"]:
                test["totIterations"] = sweep_test_iterations[test_index]
                test["currentIteration"] = 0
                test_index += 1

            if isinstance(sweep_test_iterations, list):
                test_iterations = max(sweep_test_iterations)
            else:
                test_iterations = sweep_test_iterations

            rich.print(
                "[yellow]WARNING[/yellow]: sweep mode is active, TestIt will cycle through each possible combination of parameters for each test"
            )

        if not italian_mode:
            task_message = " - Running tests..."
        else:
            task_message = " - Cooking..."

        task = progress.add_task(task_message, total=test_iterations, start=False)
        progress.start_task(task)

        test_counter = 0

        test_duration_report = {}

        for test_iteration in range(test_iterations):
            progress.update(
                task,
                description=(
                    f" - [cyan]{test_iteration + 1}/{test_iterations}: "
                    "preparing datasets"
                ),
                refresh=True,
            )

            if not testEnv.gen_datasets(sweep_mode, test_iteration):
                rich.print(f" - [bold red]ERROR: Dataset generation failed![/bold red]")
                exit(1)

            update_list_of_tests = False

            # Prepare a list for the current iteration's test durations
            test_duration_report[test_iteration] = []

            for test in data["tests"]:
                progress.update(
                    task,
                    description=(
                        f" - [cyan]{test_iteration + 1}/{test_iterations}: "
                        f"{test['appName']}"
                    ),
                    refresh=True,
                )

                start_time = time.time()

                # Re-setup debugger every 10 tests if using FPGA
                if test_counter == 5 and data["target"]["type"] == "fpga":
                    test_counter = 0
                    testEnv.stop_gdb()
                    testEnv.stop_deb()

                    deb_setup_success = testEnv.setup_deb()
                    if not deb_setup_success:
                        deb_setup_again_success = testEnv.setup_deb()
                        if not deb_setup_again_success:
                            rich.print(
                                f" - [bold red]ERROR: Failed to re-setup debugger[/bold red]"
                            )
                            exit(1)

                    gdb_setup_success = testEnv.setup_gdb()
                    if not gdb_setup_success:
                        gdb_setup_again_success = testEnv.setup_gdb()
                        if not gdb_setup_again_success:
                            rich.print(
                                f" - [bold red]ERROR: Failed to re-setup GDB[/bold red]"
                            )
                            exit(1)
                else:
                    test_counter += 1

                launch_result = testEnv.launch_test(
                    app_name=test["appName"],
                    iteration=test_iteration,
                    pattern=rf"{test['outputFormat']}",
                    output_tags=test["outputTags"],
                    timeout_t=1000,
                )
                if launch_result != testit.LaunchTestResult.SUCCESS:
                    error_message = _launch_test_error_message(
                        launch_result, test["appName"], data
                    )
                    rich.print(
                        f" - [bold red]ERROR code {int(launch_result)}: "
                        f"{error_message}[/bold red]"
                    )
                    exit(int(launch_result))

                if sweep_mode:
                    test["currentIteration"] += 1
                    if test["currentIteration"] == test["totIterations"]:
                        test_to_be_removed_name = test["appName"]
                        new_data = [
                            p
                            for p in data["tests"]
                            if p["appName"] != test_to_be_removed_name
                        ]
                        update_list_of_tests = True

                end_time = time.time()
                duration = end_time - start_time

                test_duration_report[test_iteration].append(
                    {"name": test["appName"], "duration": duration}
                )

            if update_list_of_tests:
                data["tests"] = new_data

            # Advance once per complete iteration so the ETA is iteration-based.
            progress.update(task, advance=1, refresh=True)

        if data["target"]["type"] == "fpga":
            testEnv.stop_deb()

        # Output the time duration of the tests
        json_path = os.path.join(report_dir, "test_durations.json")
        with open(json_path, "w") as f:
            json.dump(test_duration_report, f, indent=2)

        if not italian_mode:
            rich.print(" - All tests [bold green][RAN][/bold green]")
            rich.print("\nTestIt campaign [bold green]completed![/bold green]")
        else:
            rich.print(" - Pasta [bold green][COOKED][/bold green]!")
            rich.print("\n[bold green]A tavola![/bold green]")


def _generate_from_template(template, destination):
    """Copy a package template to destination unless a file already exists there."""
    relative_destination = os.path.relpath(destination)
    if os.path.exists(destination):
        rich.print(
            f"[yellow]WARNING: '{relative_destination}' already exists.[/yellow]"
        )
        return

    run_util._copy_package_file(template, destination)
    rich.print(f"Generation of '{relative_destination}' [bold green][OK][/bold green]")


# Creates the testit/ project directory with a golden module and a default configuration
def testit_setup():
    os.makedirs(testit_util.CONFIG_DIR, exist_ok=True)
    _generate_from_template(
        "templates/testit_golden.py", testit_util.golden_module_path()
    )
    _generate_from_template(
        "templates/config.test",
        testit_util.config_path(testit_util.DEFAULT_CONFIG_NAME),
    )


# Generates a report of the last verification campaign
def testit_report(sort_key, ascending, config_name=testit_util.DEFAULT_CONFIG_NAME):
    data = _load_config_or_exit(config_name)

    # Create the TestIt object
    testEnv = testit.TestItEnv(data)

    testEnv.gen_report(sort_key, ascending)
