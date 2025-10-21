#!/usr/bin/env python3
"""Auto-debug helper script (placeholder).

This script is invoked by the GitHub Actions workflow. It demonstrates
basic environment checks and writes a short report. It's intentionally
simple so it runs without external dependencies.
"""
import json
import os
import sys
import subprocess
from pathlib import Path


def main():
    repo_root = Path(__file__).resolve().parents[2]
    report = {
        "python_executable": sys.executable,
        "cwd": str(Path.cwd()),
        "repo_root": str(repo_root),
        "files_present": []
    }

    # Check for a few expected files
    expected = [
        repo_root / "ci-cd-llm-auto-debugging" / "package.json",
        repo_root / "ci-cd-llm-auto-debugging" / "src" / "add.js",
        repo_root / "ci-cd-llm-auto-debugging" / "test" / "add.test.js",
    ]

    for p in expected:
        report["files_present"].append({"path": str(p), "exists": p.exists()})

    out = repo_root / "auto_debug_report.json"
    with out.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(json.dumps(report, indent=2))

    # Try to run npm test in the Node project to capture test output for auto-debugging
    project_dir = repo_root / "ci-cd-llm-auto-debugging"
    if (project_dir / "package.json").exists():
        # Prefer running `npm test` when available. If `npm` is not on PATH
        # (common on some Windows setups), fall back to `node --test` which
        # runs the same Node built-in test runner used by this project.
        test_summary = None
        try:
            npm_test = subprocess.run(["npm", "test", "--silent"], cwd=str(project_dir), capture_output=True, text=True)
            test_summary = {
                "runner": "npm",
                "returncode": npm_test.returncode,
                "stdout": npm_test.stdout,
                "stderr": npm_test.stderr,
            }
        except FileNotFoundError:
            # npm not found; try node --test directly
            try:
                node_test = subprocess.run(["node", "--test"], cwd=str(project_dir), capture_output=True, text=True)
                test_summary = {
                    "runner": "node",
                    "returncode": node_test.returncode,
                    "stdout": node_test.stdout,
                    "stderr": node_test.stderr,
                }
            except FileNotFoundError as e:
                test_summary = {"error": "neither npm nor node found in PATH", "exception": str(e)}
        except Exception as e:
            test_summary = {"error": "error running npm test", "exception": str(e)}
    else:
        test_summary = {"error": "package.json not found in project"}

    report["npm_test"] = test_summary

    # Create a short LLM prompt file that summarizes the failure (if any)
    prompt_path = repo_root / "llm_prompt.txt"
    if isinstance(test_summary, dict) and test_summary.get("returncode"):
        prompt_text = (
            "The CI tests failed. Here is the test stdout and stderr:\n\n"
            f"STDOUT:\n{test_summary.get('stdout', '')}\n\nSTDERR:\n{test_summary.get('stderr', '')}\n\n"
            "Please suggest likely causes and minimal fixes."
        )
    elif isinstance(test_summary, dict) and test_summary.get("returncode") == 0:
        prompt_text = "Tests passed. No debugging needed."
    else:
        prompt_text = "Could not run npm test: " + json.dumps(test_summary)

    with prompt_path.open("w", encoding="utf-8") as f:
        f.write(prompt_text)

    return 0


if __name__ == "__main__":
    main()
