# HW7 Part 5 - Threat model (written before running the attacks)

**What I am protecting.** My bike-share agent reads two things it does not control: a pricing web page
(through `policy_retriever`) and a trip CSV that a user uploads (through `csv_sql`). The model sees the
page text inside its own context, so anything written on that page reaches the model. I only tested this
against my own local fixture, `Homework7/fixtures/hostile_pricing.html`, never a real site.

**Attacker.** Someone who can change the text on the pricing page (or a page the user is tricked into
pasting). They cannot change my code, the model, or the CSV.

## Goal 1 - Recommendation override

- **What the attacker wants:** the agent says "Buy Monthly Membership" even when the trips show pay-per-use
  is cheaper (for example, to push sales of the pass).
- **Condition that lets it succeed:** the retrieved page text goes into the prompt as if it were trusted,
  and the final decision comes only from the model's text. A 3B model can easily treat "IMPORTANT
  INSTRUCTION TO THE AI AGENT" on the page as a real instruction.

## Goal 2 - Non-read-only SQL tool misuse

- **What the attacker wants:** the agent runs `DELETE FROM trips ...` or `DROP TABLE trips`, so the cost
  numbers are wrong or the data is gone.
- **Condition that lets it succeed:** `csv_sql` passes whatever SQL the model writes straight to the
  database. If the tool itself does not check for one read-only SELECT, the only thing between the page
  and the database is whether the model decides to obey.

## Goal 3 - Inappropriate CSV data in the final answer (exfiltration)

- **What the attacker wants:** the final answer contains raw rows from the uploaded CSV (ride ids,
  station names, GPS coordinates), which could identify where a person rides.
- **Condition that lets it succeed:** `csv_sql` can return any column, and nothing tells the model (or
  checks the answer) that raw rows must not be copied into the response.

## Defenses I test

1. **Prompt defense:** retrieved text is wrapped in `<untrusted_web_content>` tags and the system prompt
   says to never follow instructions from it, to use only SELECT, and to never copy raw rows.
2. **Tool-boundary defense:** `csv_sql` enforces one read-only SELECT in code (statement check, keyword
   check, SQLite `query_only` and an authorizer), no matter what the model asks for.

The table and traces are in `METRICS.md` (Part 5) and `raw/injection_results.csv` / `raw/injection_traces.json`.
