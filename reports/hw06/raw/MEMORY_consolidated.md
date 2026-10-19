# MEMORY.md - durable facts learned from previous conversations
<!-- last_consolidated: 2026-10-19T16:50:58+00:00 -->
<!-- Format: - [key] fact (seen: YYYY-MM-DD, source: user|inferred|dream) -->

## Facts
- [project.domain] The app manages rental housing listings (seen: 2026-09-27, source: user, merged: 3)
- [project.embedding] Episodes store embeddings as arrays of floats (seen: 2026-09-23, source: user, merged: 2)
- [project.frontend] The frontend is React with Redux Toolkit (seen: 2026-09-16, source: user, merged: 2)
- [project.model] The local model is served by Ollama (seen: 2026-09-15, source: user, merged: 2)
- [project.mongo_db] The MongoDB database is s9486_doc (seen: 2026-09-12, source: user, merged: 2)
- [project.mysql_db] The MySQL database is s9486_rel (seen: 2026-09-13, source: user, merged: 2)
- [project.no_hosted] No paid hosted model is used (seen: 2026-09-29, source: user, merged: 3)
- [project.port] The backend runs on port 8486 (seen: 2026-09-28, source: user, merged: 3)
- [project.short_term_n] The default SHORT_TERM_N is 12 (seen: 2026-09-20, source: user, merged: 2)
- [project.summary_every] A session summary is written every 5 user messages (seen: 2026-09-22, source: user, merged: 2)
- [project.tests] Offline tests use fake models and in-memory stores (seen: 2026-09-18, source: user, merged: 2)
- [project.verify] verify_hw06.py writes verification.json (seen: 2026-09-25, source: user, merged: 2)
- [user.bedrooms] Needs 1 bedroom (seen: 2026-10-12, source: inferred)
- [user.budget] Monthly budget is $2,800 (seen: 2026-10-05, source: user)
- [user.city] Wants listings in Santa Clara (seen: 2026-10-10, source: user)
- [user.commute] Commutes to SJSU by light rail (seen: 2026-09-06, source: user)
- [user.contact] Prefers email over phone calls (seen: 2026-09-16, source: user, merged: 2)
- [user.laundry] Wants in-unit laundry (seen: 2026-09-24, source: user, merged: 2)
- [user.lease] Wants a 6-month lease (seen: 2026-10-08, source: user)
- [user.move_in] Plans to move in on 2026-12-01 (seen: 2026-09-21, source: user, merged: 2)
- [user.parking] Needs one parking spot (seen: 2026-09-13, source: user, merged: 2)
- [user.pets] Has no pets (seen: 2026-10-01, source: user)

## Resolved contradictions
- [user.city] kept "Wants listings in Santa Clara" (2026-10-10, user) over "Wants listings in San Jose" (2026-09-20, user); rule: newest seen date wins
- [user.budget] kept "Monthly budget is $2,800" (2026-10-05, user) over "Monthly budget is $2,400" (2026-09-12, user); rule: newest seen date wins
- [user.bedrooms] kept "Needs 1 bedroom" (2026-10-12, inferred) over "Needs 2 bedrooms" (2026-09-15, user); rule: newest seen date wins
- [user.lease] kept "Wants a 6-month lease" (2026-10-08, user) over "Wants a 12-month lease" (2026-09-17, user); rule: newest seen date wins
- [user.pets] kept "Has no pets" (2026-10-01, user) over "Has a cat" (2026-10-01, user); rule: newest seen date wins

## Needs review
- [user.bedrooms] CHECK: kept "Needs 1 bedroom" over "Needs 2 bedrooms" - a user-stated fact lost to a inferred fact; newest-wins ignored where the fact came from
- [user.pets] CHECK: kept "Has no pets" over "Has a cat" - same seen date, so file order decided
