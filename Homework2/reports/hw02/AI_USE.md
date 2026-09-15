# AI Use

## 1. What did you use an AI assistant for, and what did you do yourself?

I used the Codex AI assistant to help organize the Homework 2 report, arrange the screenshots according to the professor’s required format, prepare the reproducible run instructions, organize the verification checklist, and document the implementation and experiment results.

I also used AI to help review the repository structure and identify which files and outputs were required for submission. I personally ran the application, executed the verification and experiment commands, reviewed the generated outputs, checked the screenshots, and confirmed that the final evidence matched the implemented work.

## 2. What AI-produced output was wrong or unsuitable, or what did you independently verify?

An earlier version of the Part 4 experiment files was unsuitable because the results were generated using a `FakeModel` fixture instead of the real local `qwen3:4b` model. The recorded latencies were only a few milliseconds and therefore did not represent actual local LLM execution.

I also independently verified that the final report included the required HW2 sections, screenshots, run instructions, raw experiment files, metrics, and verification output.

## 3. How did you detect the problem or verify the result?

I detected the fixture problem by inspecting the raw JSON files, the recorded latency values, and the corresponding screenshots. The unusually small latency values indicated that the files had not been produced by real LLM calls.

I verified the final work by running the FastAPI application, executing the verification script, checking the JSON files, reviewing the report contents, and confirming that the screenshots corresponded to the required application and graph behavior.

## 4. What did you change, and why does it work now?

I updated the experiment and documentation workflow so that the final report is based on actual local `qwen3:4b` runs rather than placeholder fixture data. I also organized the report, verification information, reproducible commands, screenshots, and raw outputs according to the professor’s HW2 requirements.

These changes make the submission traceable because the report is supported by the recorded run logs, machine-readable experiment files, screenshots, and verification results.