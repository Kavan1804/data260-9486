# AI Use Disclosure

## 1. Which AI tools did you use?

I used the Codex assistant in this workspace to help inspect the repository, identify missing homework artifacts, draft the written report, and create the verification script.

## 2. What parts of the homework did AI help with?

AI helped organize the existing evidence into the required report structure, summarize the real experiment outputs, and draft repetitive documentation such as the reproducible commands and verification checklist.

## 3. What issue did AI help find and how was it corrected?

A real issue found during this work was the obsolete `ChatOllama` import in `agents_demo.py`. The file already routed model calls through `src/model_client.ModelClient`, so the extra import was stale and unnecessary. I confirmed that by reading the source and compiling the Python files, then removed the unused import so the demo uses the adapter cleanly.

## 4. How did you keep the submission honest and grounded in real evidence?

I did not regenerate the completed 40-run nondeterminism experiment, and I kept the existing raw outputs, logs, and screenshots. The report, README, and verification script were built from those existing artifacts and from local checks such as Python compilation and JSON validation.

## Date

2026-08-31
