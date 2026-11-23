# AI Use - HW11

**How I used AI on this homework.**

I used an AI assistant (Claude Code) for most of the preparation and for the report, and Meta Muse as the agent being tested.

What the assistant did:
- It read the HW11 PDF and the starter kit and wrote the policy, the fictional fixtures and a draft of the 12 labels.
- It extended `watch.py` so missing price data and source errors are visible, and wrote the import, verification and report scripts.
- It ran local checks on copies of the kit, moved my screenshots into the repository, checked them, and wrote the report text.

What I did:
- I committed the policy, fixtures and labels before the first agent run (the commit time is in Part 3).
- I set up Muse, saved the standing instructions, created the scheduled task, sent every Muse prompt and took all screenshots.
- I downloaded the snapshot from Muse that the metrics are computed from.

**One AI-produced output that was wrong or unsuitable, and how it was fixed.**

The assistant gave me a Muse message to paste that contained the placeholder `MY_EMAIL`. I pasted it as it was, so the first live run identified itself to the SEC with the literal text MY_EMAIL, and EDGAR answered 403 Forbidden. Muse pointed it out in both the setup chat and the live run. I then had Muse put my real contact address in the file on its computer and ran it again. EDGAR still answered 403. Muse's confirmation of the change is shown after that run, so I cannot say whether the run used the new address, or whether the address was the only cause. The address is not in the public repository.
