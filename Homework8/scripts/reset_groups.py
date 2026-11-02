#!/usr/bin/env python3
"""Move the normal Part 2 consumer groups (s9486_planners/writers/reviewers) to the end of their topics.

Use it when old messages are waiting that you do not want the real agents to process again (for example after
the failure tests, or after an agent crashed before committing a message that was already finished).
Usage (repo root):  make reset-groups
"""

from hw8_common import banner, skip_test_messages

if __name__ == "__main__":
    banner("move the Part 2 groups to the end of their topics")
    skip_test_messages()
