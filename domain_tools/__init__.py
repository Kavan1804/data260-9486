"""HW5 domain tool layer over the s9486_rel rental-listing data.

envelope   - the single {ok, data, error} response shape (Part 2B, reused in Part 4)
repository - storage access: MySQL for real runs, in-memory for offline tests
retry      - per-attempt timeout + bounded exponential backoff (Part 3)
faults     - VERIFY_SEED-driven fault injection (Part 3)
tools      - the three domain tools: search, detail lookup, aggregate
safety     - the fair-housing safety rule (Part 5)
execute    - execute_tool(name, inputs): the only entry point the agent uses (Part 4)
agent      - run_agent(user_input) with Ollama or MockModel (Part 5)
"""
