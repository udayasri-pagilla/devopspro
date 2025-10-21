# CI/CD LLM Auto Debugging Demo

Repository scaffold used for demonstrating an automated debug workflow.

Layout
- `.github/workflows/auto_debug.yml` - GitHub Actions workflow that runs tests and invokes a small Python auto-debug script.
- `.github/scripts/auto_debug.py` - Simple script that inspects the repo and writes a JSON report.
- `ci-cd-llm-auto-debugging/` - Small Node project with a sample function and tests.

Run tests locally (PowerShell)

```powershell
cd .\ci-cd-llm-auto-debugging
npm ci
npm test
```

Run the auto-debug script locally (PowerShell)

```powershell
python .\.github\scripts\auto_debug.py
```

What the script produces
- `auto_debug_report.json` — a JSON file with the environment and test run details.
- `llm_prompt.txt` — a short summary prompt created when tests fail, suitable for feeding to an LLM-based diagnoser.

CI behavior
- The GitHub Actions workflow runs tests and then runs the auto-debug script. The workflow uploads `auto_debug_report.json` as an artifact named `auto_debug_report` for later inspection or processing.

Optional LLM reply and PR comments
- If you set the `OPENAI_API_KEY` repository secret, the workflow will:
	- Run the optional LLM helper which posts `llm_prompt.txt` to OpenAI.
	- Save the LLM reply to `llm_response.txt` and upload it as an artifact.
	- If the run is for a pull request, the workflow will post the LLM reply as a PR comment (so reviewers can see automated suggestions).

Security note: Do not put secrets or sensitive information into prompts. Limit what the script sends to the LLM and audit the prompts if the repo contains private data.

CI dependencies
- The workflow now installs Python dependencies for the LLM helper from `.github/scripts/requirements.txt` (currently contains `requests`). If you prefer a different client (like the `openai` SDK), I can update the helper and requirements.

Suggested fixes from LLM
- The helper now asks for a structured JSON response with `summary` and `patch` fields and writes two files when available:
	- `llm_suggestion.json` — the parsed JSON suggestion (summary + patch).
	- `llm_suggestion.patch` — a unified-diff patch you can apply with `git apply`.

How to apply a suggested patch locally:

```powershell
# From repo root
git apply llm_suggestion.patch
# Or inspect before applying
git apply --check llm_suggestion.patch
git apply --stat llm_suggestion.patch
```

The workflow will upload these files as artifacts and include the suggested patch in the PR comment when present.
