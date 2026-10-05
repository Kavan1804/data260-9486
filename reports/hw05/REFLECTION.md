# Reflection - HW5 Part 5

I picked run `e96c59eb9802` ("step ceiling" scenario, max_steps = 3) from `raw/agent_runs.jsonl`. I
asked the agent to compare landlords 1 to 5 by calling `landlord_portfolio_stats` once for each
landlord and to answer only after it had all five results.

Step 1: llama3.2:3b replied with five tool calls in one message (landlord_id "1" to "5"). My harness
runs one tool call per step, so it executed only the first call and logged the other four as
`ignored_tool_calls`. `execute_tool` turned the string "1" into the integer 1 and returned `ok:
true`: Farah Okafor, 269 listings, 270 available units.

Step 2: the model did not call a tool. Instead it wrote a JSON envelope in its text reply for
"Samantha Lee" with 0 listings. That landlord does not exist, so the model invented a tool result.
The text guard marked this as `fabricated_tool_result`, did not accept it as the final answer, and
sent the model a correction asking it to call the real tool.

Step 3: the model called `landlord_portfolio_stats` with landlord_id "2" and got a real result: Hana
Iyer, Rose Garden Realty, 279 listings.

The turn counter then reached 3, which equals max_steps, so the loop stopped with stop reason
`max_steps` and no final answer (3 steps, 2 tool calls). The safety rule was not involved because no
search query was sent, so `safety_blocked` is false on both tool calls.

This run showed me why the harness needs limits that do not depend on the model behaving well: the
3B model ignored "one at a time" and invented data. The step ceiling made sure the run still ended,
and the log shows where it went wrong. For this kind of comparison I would raise max_steps or add a
tool that compares landlords in one call.
