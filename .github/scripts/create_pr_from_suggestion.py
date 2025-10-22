#!/usr/bin/env python3
"""Apply LLM suggestion (patch) or create an explanatory PR.

This script is intended to run inside the Action runner after the LLM
helper has produced `llm_suggestion.patch` or `llm_suggestion.json` and
`llm_response.txt`.

Behavior:
- If `llm_suggestion.patch` exists and applying it produces changes,
  create branch `autofix/<short-sha>`, commit and push, then open a PR.
- Else if `llm_suggestion.json` exists (summary present), create branch
  `autofix-note/<short-sha>` and add a short markdown file with the
  suggestion, commit, push and open a PR describing the issue.

The script reads `GITHUB_TOKEN`, `GITHUB_REPOSITORY`, and `BASE_BRANCH`
from the environment.
"""
import json
import os
import subprocess
import sys
from pathlib import Path

import requests


def run(cmd, check=True, **kwargs):
    print("$", " ".join(cmd))
    return subprocess.run(cmd, check=check, text=True, capture_output=True, **kwargs)


def push_branch(branch):
    run(["git", "push", "--set-upstream", "origin", branch])


def create_pr(title, body, head, base, token, repo):
    url = f"https://api.github.com/repos/{repo}/pulls"
    headers = {"Authorization": f"token {token}", "Accept": "application/vnd.github+json"}
    payload = {"title": title, "head": head, "base": base, "body": body}
    r = requests.post(url, headers=headers, json=payload, timeout=30)
    print("Create PR response:", r.status_code)
    print(r.text)
    r.raise_for_status()
    return r.json()


def main():
    repo_root = Path(__file__).resolve().parents[2]
    os.chdir(repo_root)

    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("GITHUB_REPOSITORY")
    base_branch = os.environ.get("BASE_BRANCH", "main")
    if not token or not repo:
        print("GITHUB_TOKEN or GITHUB_REPOSITORY not set; cannot create PR")
        return 0

    sha = run(["git", "rev-parse", "--short", "HEAD"], check=True).stdout.strip()

    suggestion_patch = repo_root / "llm_suggestion.patch"
    suggestion_json = repo_root / "llm_suggestion.json"
    raw_response = repo_root / "llm_response.txt"

    # Ensure git user is set
    run(["git", "config", "user.name", "github-actions[bot]"])
    run(["git", "config", "user.email", "github-actions[bot]@users.noreply.github.com"])

    # Try to apply patch if present
    if suggestion_patch.exists() and suggestion_patch.stat().st_size > 0:
        branch = f"autofix/{sha}"
        try:
            run(["git", "checkout", "-b", branch])
        except subprocess.CalledProcessError:
            # branch exists; checkout it
            run(["git", "checkout", branch])

        # Try applying the patch
        try:
            # Check first
            res = run(["git", "apply", "--check", str(suggestion_patch)], check=False)
            if res.returncode != 0:
                print("Patch may not apply cleanly; continuing to attempt apply")
            run(["git", "apply", str(suggestion_patch)])
        except subprocess.CalledProcessError as e:
            print("Failed to apply patch:", e)
            # fallthrough: if no changes, create note PR instead

        # If there are changes, commit and open a PR
        diff = run(["git", "status", "--porcelain"], check=True).stdout.strip()
        if diff:
            run(["git", "add", "-A"])
            run(["git", "commit", "-m", "chore: apply LLM suggested patch"])
            push_branch(branch)

            summary = "LLM suggested code changes"
            if suggestion_json.exists():
                try:
                    parsed = json.loads(suggestion_json.read_text(encoding="utf-8"))
                    summary = parsed.get("summary", summary)
                except Exception:
                    pass
            raw = raw_response.read_text(encoding="utf-8") if raw_response.exists() else ""
            body = summary + "\n\n---\n\nRaw LLM response:\n\n" + raw
            pr = create_pr(f"LLM autofix: {sha}", body, branch, base_branch, token, repo)
            print("Created PR:", pr.get("html_url"))
            return 0
        else:
            print("Patch existed but did not change tree; will not create a code PR")

    # No usable patch; if there's a structured summary, create a note PR
    if suggestion_json.exists():
        branch = f"autofix-note/{sha}"
        try:
            run(["git", "checkout", "-b", branch])
        except subprocess.CalledProcessError:
            run(["git", "checkout", branch])

        # create a small markdown file describing the suggestion
        try:
            parsed = json.loads(suggestion_json.read_text(encoding="utf-8"))
            summary = parsed.get("summary", "LLM suggested an issue; see details")
        except Exception:
            summary = suggestion_json.read_text(encoding="utf-8")

        note_dir = repo_root / ".github" / "llm-summaries"
        note_dir.mkdir(parents=True, exist_ok=True)
        note_file = note_dir / f"llm_note_{sha}.md"
        raw = raw_response.read_text(encoding="utf-8") if raw_response.exists() else ""
        note_file.write_text(f"# LLM suggestion for {sha}\n\n{summary}\n\n---\n\nRaw LLM response:\n\n{raw}\n", encoding="utf-8")

        run(["git", "add", str(note_file)])
        run(["git", "commit", "-m", "chore: add LLM suggestion note"])
        push_branch(branch)

        body = summary + "\n\nAttached file contains full LLM response."
        pr = create_pr(f"LLM note: {sha}", body, branch, base_branch, token, repo)
        print("Created PR:", pr.get("html_url"))
        return 0

    # If no suggestion exists, create a diagnostics PR using auto_debug_report.json
    report_path = repo_root / "auto_debug_report.json"
    if report_path.exists():
        branch = f"ci-report/{sha}"
        try:
            run(["git", "checkout", "-b", branch])
        except subprocess.CalledProcessError:
            run(["git", "checkout", branch])

        # add the report file to a known folder so the PR contains the diagnostics
        out_dir = repo_root / ".github" / "ci-reports"
        out_dir.mkdir(parents=True, exist_ok=True)
        dest = out_dir / f"auto_debug_report_{sha}.json"
        try:
            dest.write_text(report_path.read_text(encoding="utf-8"), encoding="utf-8")
        except Exception as e:
            print("Failed to copy report file:", e)

        run(["git", "add", str(dest)])
        run(["git", "commit", "-m", "chore: add CI auto-debug report"]) 
        push_branch(branch)

        # Build PR body summarizing test result if available
        try:
            report = json.loads(report_path.read_text(encoding="utf-8"))
            npm_test = report.get("npm_test")
            if isinstance(npm_test, dict):
                rc = npm_test.get("returncode")
                if rc == 0:
                    title = f"CI report: tests passed ({sha})"
                    body = "Automated CI report: tests passed. See attached auto-debug report for details."
                else:
                    title = f"CI report: tests failed ({sha})"
                    stdout = npm_test.get("stdout", "") or ""
                    stderr = npm_test.get("stderr", "") or ""
                    body = (
                        "Automated CI report: tests failed.\n\n"
                        "Attached auto-debug report contains stdout/stderr and files present.\n\n"
                        "```\n" + stdout + "\n\n" + stderr + "\n```"
                    )
            else:
                title = f"CI report: diagnostics ({sha})"
                body = "Automated CI diagnostics. See attached auto-debug report."
        except Exception:
            title = f"CI report: diagnostics ({sha})"
            body = "Automated CI diagnostics. See attached auto-debug report."

        pr = create_pr(title, body, branch, base_branch, token, repo)
        print("Created PR:", pr.get("html_url"))
        return 0

    print("No suggestion patch, JSON, or auto_debug_report found; nothing to do.")
    return 0


if __name__ == '__main__':
    sys.exit(main())
