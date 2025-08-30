# BSD 3-Clause License
#
# Copyright (c) 2020 - 2024, ddelange, <ddelange@delange.dev>
#
# All rights reserved.
#
# Redistribution and use in source and binary forms, with or without
# modification, are permitted provided that the following conditions are met:
#
# 1. Redistributions of source code must retain the above copyright notice, this
#    list of conditions and the following disclaimer.
#
# 2. Redistributions in binary form must reproduce the above copyright notice,
#    this list of conditions and the following disclaimer in the documentation
#    and/or other materials provided with the distribution.
#
# 3. Neither the name of the copyright holder nor the names of its
#    contributors may be used to endorse or promote products derived from
#    this software without specific prior written permission.
#
# THIS SOFTWARE IS PROVIDED BY THE COPYRIGHT HOLDERS AND CONTRIBUTORS "AS IS"
# AND ANY EXPRESS OR IMPLIED WARRANTIES, INCLUDING, BUT NOT LIMITED TO, THE
# IMPLIED WARRANTIES OF MERCHANTABILITY AND FITNESS FOR A PARTICULAR PURPOSE ARE
# DISCLAIMED. IN NO EVENT SHALL THE COPYRIGHT HOLDER OR CONTRIBUTORS BE LIABLE
# FOR ANY DIRECT, INDIRECT, INCIDENTAL, SPECIAL, EXEMPLARY, OR CONSEQUENTIAL
# DAMAGES (INCLUDING, BUT NOT LIMITED TO, PROCUREMENT OF SUBSTITUTE GOODS OR
# SERVICES; LOSS OF USE, DATA, OR PROFITS; OR BUSINESS INTERRUPTION) HOWEVER
# CAUSED AND ON ANY THEORY OF LIABILITY, WHETHER IN CONTRACT, STRICT LIABILITY,
# OR TORT (INCLUDING NEGLIGENCE OR OTHERWISE) ARISING IN ANY WAY OUT OF THE USE
# OF THIS SOFTWARE, EVEN IF ADVISED OF THE POSSIBILITY OF SUCH DAMAGE.
#
# SPDX-License-Identifier: BSD-3-Clause

"""
Test for --no-compile functionality with packages that require compilation.
"""

import json
import subprocess

import pytest
from click.testing import CliRunner

from pipgrip.cli import main
from pipgrip.compat import PIP_VERSION


def test_no_compile_gevent_integration():
    """Integration test for --no-compile flag with gevent==20.9.0"""
    runner = CliRunner()

    # Test without --no-compile - this might fail due to compilation issues
    result_without_flag = runner.invoke(main, ["gevent==20.9.0", "--verbose"])

    # Test with --no-compile - this should work by using only pre-compiled wheels
    result_with_flag = runner.invoke(
        main, ["--no-compile", "gevent==20.9.0", "--verbose"]
    )

    # The key test is that --no-compile should not fail due to compilation errors
    # Even if there are no pre-compiled wheels available, it should fail gracefully
    # rather than with compilation errors

    if result_without_flag.exit_code != 0:
        # If the version without --no-compile fails, check it's due to compilation
        compilation_error_indicators = [
            "CompileError",
            "error: subprocess-exited-with-error",
            "Getting requirements to build wheel did not run successfully",
            "undeclared name not builtin: long",
        ]

        has_compilation_error = any(
            indicator in result_without_flag.output
            for indicator in compilation_error_indicators
        )

        if has_compilation_error:
            # If we have compilation errors without the flag, the --no-compile version
            # should either succeed or fail with a different (non-compilation) error
            if result_with_flag.exit_code != 0:
                # Should not have compilation errors when --no-compile is used
                no_compilation_error = not any(
                    indicator in result_with_flag.output
                    for indicator in compilation_error_indicators
                )
                assert (
                    no_compilation_error
                ), f"--no-compile still has compilation errors: {result_with_flag.output}"

                # It's OK if it fails due to no binary wheels being available
                pass
            else:
                # Great! --no-compile succeeded where normal mode failed
                assert result_with_flag.exit_code == 0
    else:
        # If normal mode succeeds, --no-compile should also succeed
        assert result_with_flag.exit_code == 0


def test_no_compile_flag_in_help():
    """Test that --no-compile flag appears in help output."""
    runner = CliRunner()
    result = runner.invoke(main, ["--help"])

    assert result.exit_code == 0
    assert "--no-compile" in result.output
    assert "Avoid building/compiling packages from source" in result.output


@pytest.mark.skipif(
    PIP_VERSION < [22, 2],
    reason="get_package_report not available on old pip, plus weird output behavior",
)
def test_skip_invalid_input_with_no_compile_flat_output():
    """Test flat output with --skip-invalid-input and --no-compile."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--skip-invalid-input",
            "--no-compile",
            "requests==2.22.0",
            "gevent==20.9.0",  # This version does not have wheels for all platforms
        ],
    )
    assert result.exit_code == 0
    output = result.output.strip().split("\n")
    assert "requests==2.22.0" in output
    assert "gevent==20.9.0" in output
    # Check for a transitive dependency of requests
    assert any(dep.startswith("certifi==") for dep in output)


@pytest.mark.skipif(
    PIP_VERSION < [22, 2],
    reason="get_package_report not available on old pip, plus weird output behavior",
)
def test_skip_invalid_input_with_no_compile_tree_output():
    """Test tree JSON output with --skip-invalid-input and --no-compile."""
    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--skip-invalid-input",
            "--no-compile",
            "requests==2.22.0",
            "gevent==20.9.0",
            "--tree",
            "--json",
        ],
    )
    assert result.exit_code == 0
    output = json.loads(result.output)

    requests_pkg = next((p for p in output if p["name"] == "requests"), None)
    gevent_pkg = next((p for p in output if p["name"] == "gevent"), None)

    assert requests_pkg is not None
    assert gevent_pkg is not None

    assert requests_pkg["version"] == "2.22.0"
    assert "dependencies" in requests_pkg and len(requests_pkg["dependencies"]) > 0

    assert gevent_pkg["version"] == "20.9.0"
    assert "dependencies" not in gevent_pkg or len(gevent_pkg["dependencies"]) == 0


@pytest.mark.skipif(
    PIP_VERSION < [22, 2],
    reason="get_package_report not available on old pip, plus weird output behavior",
)
def test_no_compile_fails_without_skip_flag():
    """Test that --no-compile fails without --skip-invalid-input for an invalid package."""
    runner = CliRunner()
    result = runner.invoke(main, ["--no-compile", "gevent==20.9.0"])
    assert result.exit_code != 0
    assert "Failed to get report for" in result.output


@pytest.mark.skipif(
    PIP_VERSION < [22, 2],
    reason="get_package_report not available on old pip, plus weird output behavior",
)
def test_requirements_file_skip_invalid_no_compile_flat(tmp_path):
    """Flat pins from -r requirements.txt containing a valid and an invalid package."""
    req_path = tmp_path / "requirements.txt"
    req_path.write_text("requests==2.22.0\ngevent==20.9.0\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--skip-invalid-input",
            "--no-compile",
            "-r",
            str(req_path),
        ],
    )

    assert result.exit_code == 0
    output = result.output.strip().split("\n")
    assert "requests==2.22.0" in output
    assert any(line.startswith("certifi==") for line in output)
    assert "gevent==20.9.0" in output


@pytest.mark.skipif(
    PIP_VERSION < [22, 2],
    reason="get_package_report not available on old pip, plus weird output behavior",
)
def test_requirements_file_skip_invalid_no_compile_tree_json(tmp_path):
    """Tree JSON from -r requirements.txt containing a valid and an invalid package."""
    req_path = tmp_path / "requirements.txt"
    req_path.write_text("requests==2.22.0\ngevent==20.9.0\n", encoding="utf-8")

    runner = CliRunner()
    result = runner.invoke(
        main,
        [
            "--skip-invalid-input",
            "--no-compile",
            "-r",
            str(req_path),
            "--tree",
            "--json",
        ],
    )

    assert result.exit_code == 0
    data = json.loads(result.output)

    requests_pkg = next((p for p in data if p["name"] == "requests"), None)
    gevent_pkg = next((p for p in data if p["name"] == "gevent"), None)

    assert requests_pkg is not None and requests_pkg["version"] == "2.22.0"
    assert "dependencies" in requests_pkg and len(requests_pkg["dependencies"]) > 0

    assert gevent_pkg is not None and gevent_pkg["version"] == "20.9.0"
    assert "dependencies" not in gevent_pkg or len(gevent_pkg["dependencies"]) == 0
