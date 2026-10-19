# AI Use - HW6

**1. What I used an AI assistant for, and what I did myself.**

I used an AI assistant (Claude Code) to go through the HW6 PDF together with my HW5 repository and the two
professor reference projects, and to plan how to add HW6 without making a second copy of the app. It helped me
write the MongoDB connection and validators, the listing-document CRUD router, the chat memory logic (short-term
window, summaries, fact extraction, cosine retrieval), the file-based memory and consolidation code, the
experiment, scoring and cost scripts, the tests and the README. I also used it to understand error messages and
to organize this report.

I started MongoDB with the professor's Docker Compose file, ran the backend, Ollama and every script from my own
terminal, sent the chat messages, ran the four experiment settings, took all the screenshots in Compass and VS
Code, and checked the numbers in the report against the files in `reports/hw06/raw/`.

**2. One AI-produced output that was wrong or unsuitable.**

The CRUD demo commands the assistant gave me contained the line `ID=<paste an "id" from above>`. When I pasted
the block into my terminal, zsh stopped with `parse error near '\n'` and none of the requests after it ran. Some
of the other commands also had `# comments` at the end, which zsh does not accept by default when you type
commands interactively.

A second thing that did not work was the function my local model generated for the AGENT.md check. llama3.2:3b
wrote `days_until_available()` without type hints or a docstring, and it subtracted a `date` from a `datetime`,
which raised a TypeError in two of the four test cases.

**3. How the problem was detected.**

For the commands, the terminal error showed it right away. I worked out that zsh reads `<` and `>` as file
redirection, so the placeholder was treated as a broken command. For the generated function, my
`agent_md_check.py` script caught it: rules R6 (type hints) and R7 (docstring) failed, and the behavior tests
showed the TypeError (Part 4.4 of the report).

**4. What was changed and why it works now.**

I changed the CRUD commands so the id is read from the POST response automatically (`ID=$(... | python3 -c ...)`)
and removed the inline comments. After that, the full create, read, update, delete and 404 sequence ran in one go
(Part 1 of the report). I kept the generated function as it was and reported the failures, because the point of that check is
to show whether the model actually follows AGENT.md. My own implemented function `count_memory_lines` passes
all the rules. I also checked the token numbers myself: Ollama's real prompt token counts were about 94% of my
characters/4 estimate in every setting, so the estimated per-part breakdown in Part 3 is reasonable.
