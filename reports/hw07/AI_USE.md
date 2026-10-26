# AI Use - HW7

**1. What I used an AI assistant for, and what I did myself.**

I used an AI assistant (Claude Code) a lot in this homework. It went through the HW7 instructions, my
HW5/HW6 code and the Demo 7 project with me and helped me plan how to add JWT auth to my existing listings
API instead of making a new app. It generated most of the HW7 code from my instructions: the JWT and role
checks, the users-table migration, the repair path in my agent loop, the verifier and Reflexion code, the
bike-share tools and agent, the file tools and the safety gate, and the test and experiment scripts. It also
helped me organize the Markdown files and the report, explain error messages, and debug failing tests.

One thing it suggested that I agreed to: running `ruff format` once on the whole root app so later commits
only show real changes. That was the AI's idea; I said yes to it.

What I did myself: I made the design decisions (Bay Wheels, how to build the two scenarios, allowing
LangGraph only for Part 4), started MySQL and Ollama, ran the migration, the tests and every experiment, used
the app and the bike-share page in the browser, looked at the MySQL users table to check that only bcrypt
hashes are stored, took the screenshots, and checked the numbers in METRICS.md against the raw files.

**2. One AI-produced output that was wrong or unsuitable.**

The first version of the safety gate that the AI wrote for Part 6 had false allows. `cat a > ~/.bashrc`,
`echo x > ../../etc/hosts` and `echo x > $HOME/.zshrc` were all allowed. `cat` and `echo` are on my
SAFE_PREFIXES list, and the "redirect to a root path" rule only looked for targets starting with `/`, so a
`~`, `$HOME` or `../..` path slipped through even though it writes outside the sandbox.

**3. How the problem was detected.**

Before running the official 10-command test, I ran a longer list of tricky commands through `confirm_bash`
(things like `\rm -fr`, `ls && rm -rf x`, `find . -delete`, and redirects to different paths). Three of them
came back as allowed when they should have been blocked. I saved that real output in
`raw/safety_gate_v1_false_allows.json` before changing anything.

**4. What was changed and why it works now.**

The redirect check now also treats a target that starts with `~` or `$`, or that contains a `..` path part,
as writing outside the sandbox, because those expand to absolute paths or climb out of the folder. After the
fix, all three commands are blocked, the 10-command test is 10/10 (5 allowed, 5 blocked), and 17 extra tricky
commands are blocked too. This works because the rule now checks where the redirect actually ends up, instead
of only looking for a leading `/`. I also checked the gate is still not too strict: `echo hello > out.txt` and
`echo hi > /dev/null` are still allowed.
