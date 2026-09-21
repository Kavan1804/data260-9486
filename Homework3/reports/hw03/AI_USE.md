# AI Use - HW3

**1. What I used an AI assistant for, and what I did myself.**
I used Claude Code mainly for reporting/documentation and error debugging,
plus inline code comments as I built out the auth router and the retrieval
pipeline. It scaffolded `routers/auth.py`, `rag/pipelines.py`, and the
supporting scripts, and wrote the first drafts of `README.md`,
`report_template.md`, and this file. What I actually did myself: picked and
downloaded the real domain corpus, ran `rag/corpus_prep.py`,
`rag/build_manifest.py`, `rag/run_experiments.py`, and
`rag/compute_metrics.py` in my own terminal, tested every route in the
browser, captured the screenshots and the Set-Cookie header, and reviewed
the generated numbers before they went into `METRICS.md`.

**2. One AI-produced output that was wrong/unsuitable.**
The first version of `routers/auth.py` called
`templates.TemplateResponse("index.html", {"request": request, ...})` -
the older Starlette calling convention. When I actually ran `python3
main.py` and opened `/`, it crashed with a 500 error:
`TypeError: unhashable type: 'dict'` inside Jinja2's template cache lookup.

**3. How I detected the problem.**
I ran the app myself and pasted the full uvicorn traceback back to Claude.
The traceback showed the failure happening inside
`Jinja2Templates.get_template()`, called with something unhashable - which
only made sense if the `name` argument had actually received the context
dict instead of the template filename.

**4. What I changed, and why it works now.**
The installed `requirements.txt` had no version pin, so pip installed a
recent Starlette release that requires the newer signature
`TemplateResponse(request, name, context)`, with `request` as the first
positional argument, and no longer auto-detects the old `(name, context)`
order. Calling it the old way silently assigned `"index.html"` to the
`request` parameter and the context dict to `name`, and Jinja2 then tried to
use that dict as a template-cache key, which isn't hashable. I fixed all
three `TemplateResponse` calls in `routers/auth.py` to pass `request` first,
`name` second, and dropped the now-redundant `"request"` key from each
context dict. After that fix, `/`, `/login`, and `/dashboard` all rendered
correctly on the first try.
