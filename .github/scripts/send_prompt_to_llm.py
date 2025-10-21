#!/usr/bin/env python3
"""Optional helper to send `llm_prompt.txt` to OpenAI and print the response.

This script is intentionally minimal and only runs if `OPENAI_API_KEY` is
available in the environment. It uses the `requests` library if present, but
falls back to printing instructions when not.
"""
import os
import sys
import time
import json
from pathlib import Path


def _write_response(repo_root: Path, content: str) -> None:
    out_path = repo_root / "llm_response.txt"
    out_path.write_text(content, encoding="utf-8")
    print(f"Wrote LLM response to {out_path}")


def main():
    repo_root = Path(__file__).resolve().parents[2]
    prompt_path = repo_root / "llm_prompt.txt"
    dry_run = False
    if len(sys.argv) > 1 and sys.argv[1] in ("--dry-run", "-n"):
        dry_run = True
        print("Running in dry-run mode: no external API will be called.")
    if not prompt_path.exists():
        print("No llm_prompt.txt found — nothing to send.")
        return 0

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        if not dry_run:
            print("OPENAI_API_KEY not set — skipping LLM call. To enable, set the secret and re-run.")
            print(f"To manually inspect prompt: {prompt_path}")
            return 0

    try:
        import requests
    except Exception:
        msg = "The 'requests' library is not installed. Install it or run this script in an environment with requests."
        print(msg)
        _write_response(repo_root, msg)
        return 1

    prompt = prompt_path.read_text(encoding="utf-8")

    # Dry-run: produce a canned suggestion without calling the API
    if dry_run:
        canned_reply = "[dry-run] Simulated LLM response: tests passed and no fix required, but suggesting a minor README note." 
        _write_response(repo_root, canned_reply)
        suggestion = {
            "summary": "Dry-run: no failing tests; suggested minor README note.",
            "patch": "--- a/README.md\n+++ b/README.md\n@@\n # CI/CD LLM Auto Debugging Demo\n+\n+> Suggested note: This was generated in dry-run mode.\n"
        }
        (repo_root / "llm_suggestion.json").write_text(json.dumps(suggestion, indent=2), encoding="utf-8")
        (repo_root / "llm_suggestion.patch").write_text(suggestion["patch"], encoding="utf-8")
        print(f"Dry-run suggestion written to {repo_root / 'llm_suggestion.json'} and patch to {repo_root / 'llm_suggestion.patch'}")
        return 0

    url = "https://api.openai.com/v1/chat/completions"
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    # Ask the LLM to respond with a strict JSON object containing a short
    # `summary` field and an optional `patch` field with a unified diff
    # (applyable via `git apply`). We will also keep the raw response.
    json_instructions = (
        "Please respond with a JSON object only (no extra text) with the schema:\n"
        "{\"summary\": \"short human-readable summary\", \"patch\": \"unified-diff-or-empty\"}\n"
        "If no patch is suggested, set `patch` to an empty string."
    )

    data = {
        "model": "gpt-4o-mini",
        "messages": [
            {"role": "system", "content": "You are a helpful coding assistant that outputs strictly valid JSON."},
            {"role": "user", "content": json_instructions + "\nPrompt:\n" + prompt},
        ],
        "max_tokens": 800,
        "temperature": 0.0,
    }

    max_retries = 3
    backoff = 1.0
    last_exception = None
    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(url, headers=headers, json=data, timeout=30)
        except Exception as e:
            last_exception = e
            print(f"Request exception (attempt {attempt}): {e}")
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            body = f"LLM request failed: exception: {e}"
            _write_response(repo_root, body)
            return 1

        # If throttled or server error, retry with backoff
        if resp.status_code in (429, 500, 502, 503, 504):
            print(f"LLM API returned {resp.status_code}; attempt {attempt} of {max_retries}")
            if attempt < max_retries:
                time.sleep(backoff)
                backoff *= 2
                continue
            # final attempt; fall through to write error

        if resp.status_code != 200:
            body = f"LLM API returned non-200 status: {resp.status_code}\n\n{resp.text}"
            print(body)
            _write_response(repo_root, body)
            return 1

        # Successful response
        try:
            j = resp.json()
            reply = j.get("choices", [])[0].get("message", {}).get("content")
        except Exception:
            reply = resp.text

        # Save raw reply
        _write_response(repo_root, reply)

        # Try to parse the reply as JSON per our schema
        suggestion_path = repo_root / "llm_suggestion.json"
        patch_path = repo_root / "llm_suggestion.patch"
        try:
            parsed = json.loads(reply)
            # Write structured suggestion
            suggestion_path.write_text(json.dumps(parsed, indent=2), encoding="utf-8")
            # If patch present and non-empty, write the patch file
            patch = parsed.get("patch") or ""
            if isinstance(patch, str) and patch.strip():
                patch_path.write_text(patch, encoding="utf-8")
        except Exception as e:
            # Couldn't parse JSON — write an explanatory file
            err = {"error": "could not parse LLM JSON", "exception": str(e)}
            suggestion_path.write_text(json.dumps(err, indent=2), encoding="utf-8")

        return 0


if __name__ == "__main__":
    raise SystemExit(main())
