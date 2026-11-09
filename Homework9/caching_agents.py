import os, json, time, hashlib, math
from typing import Optional

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import uvicorn
from openai import OpenAI

# use ollama here
_client: Optional[OpenAI] = None

def get_client() -> OpenAI:
    global _client
    if _client is None:
        key = os.environ.get("OPENAI_API_KEY", "")
        if not key:
            raise EnvironmentError("Set OPENAI_API_KEY environment variable.")
        _client = OpenAI(api_key=key)
    return _client


# replace using redis or similar for actual use in homework
class ExactCache:
    def __init__(self, max_size=256, ttl=900):
        self.store: dict[str, dict] = {}
        self.max_size = max_size
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def _key(self, prompt: str, model: str) -> str:
        return hashlib.sha256(f"{model}::{prompt}".encode()).hexdigest()[:16]

    def get(self, prompt: str, model: str = "gpt-4o-mini") -> Optional[str]:
        k = self._key(prompt, model)
        e = self.store.get(k)
        if e and (time.time() - e["ts"] < self.ttl):
            self.hits += 1
            e["ts"] = time.time()
            return e["value"]
        if e:
            del self.store[k]
        self.misses += 1
        return None

    def put(self, prompt: str, value: str, model: str = "gpt-4o-mini"):
        k = self._key(prompt, model)
        if len(self.store) >= self.max_size:
            oldest = min(self.store, key=lambda x: self.store[x]["ts"])
            del self.store[oldest]
        self.store[k] = {"value": value, "ts": time.time(), "prompt": prompt[:100]}

    @property
    def stats(self):
        t = self.hits + self.misses
        return {"entries": len(self.store), "hits": self.hits, "misses": self.misses,
                "hit_rate": f"{self.hits/t*100:.1f}%" if t else "0%"}


# in your homework please use better matching
def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    return dot / (na * nb) if na and nb else 0.0


class SemanticCache:
    """Returns a hit when a new query's embedding cosine similarity
    to a cached query is >= threshold."""

    def __init__(self, threshold: float = 0.92, max_size: int = 128, ttl: int = 900):
        self.entries: list[dict] = []
        self.threshold = threshold
        self.max_size = max_size
        self.ttl = ttl
        self.hits = 0
        self.misses = 0

    def _embed(self, text: str) -> list[float]:
        resp = get_client().embeddings.create(input=text, model="text-embedding-3-small")
        return resp.data[0].embedding

    def get(self, prompt: str) -> tuple[Optional[str], float]:
        """Returns (cached_value | None, best_similarity)."""
        now = time.time()
        self.entries = [e for e in self.entries if now - e["ts"] < self.ttl]
        if not self.entries:
            self.misses += 1
            return None, 0.0
        emb = self._embed(prompt)
        best_sim, best_val = 0.0, None
        for e in self.entries:
            sim = _cosine(emb, e["embedding"])
            if sim > best_sim:
                best_sim = sim
                best_val = e["value"]
        if best_sim >= self.threshold:
            self.hits += 1
            return best_val, best_sim
        self.misses += 1
        return None, best_sim

    def put(self, prompt: str, value: str):
        if len(self.entries) >= self.max_size:
            self.entries.sort(key=lambda e: e["ts"])
            self.entries = self.entries[len(self.entries)//4:]
        emb = self._embed(prompt)
        self.entries.append({"embedding": emb, "prompt": prompt[:120],
                             "value": value, "ts": time.time()})

    @property
    def stats(self):
        t = self.hits + self.misses
        return {"entries": len(self.entries), "hits": self.hits, "misses": self.misses,
                "hit_rate": f"{self.hits/t*100:.1f}%" if t else "0%",
                "threshold": self.threshold}


exact_cache = ExactCache()
semantic_cache = SemanticCache(threshold=0.92)


# LLM call with layered caching: check exact cache  check semantic cache  call LLM. Returns (text, cache_status).
def llm_call(prompt: str, system: str = "", model: str = "gpt-4o-mini",
             temperature: float = 0.7, use_cache: bool = True) -> tuple[str, str]:
    """Returns (text, cache_status).  status ∈ {exact, semantic (NN%), live}."""
    full = f"{system}\n\n{prompt}" if system else prompt

    if use_cache:
        hit = exact_cache.get(full, model)
        if hit:
            return hit, "exact"
        sem_hit, sim = semantic_cache.get(full)
        if sem_hit:
            exact_cache.put(full, sem_hit, model)
            return sem_hit, f"semantic ({sim:.0%})"

    client = get_client()
    msgs = []
    if system:
        msgs.append({"role": "system", "content": system})
    msgs.append({"role": "user", "content": prompt})
    resp = client.chat.completions.create(model=model, messages=msgs,
                                          temperature=temperature, max_tokens=1024)
    text = resp.choices[0].message.content.strip()

    if use_cache:
        exact_cache.put(full, text, model)
        semantic_cache.put(full, text)
    return text, "live"


# ──────────────────────────────────────────────
# 5. AGENT PATTERNS
# ──────────────────────────────────────────────
def _safe_json(raw: str) -> dict:
    c = raw.strip()
    if c.startswith("```"):
        c = "\n".join(c.split("\n")[1:])
    if c.endswith("```"):
        c = c.rsplit("```", 1)[0]
    return json.loads(c.strip())


def plan(goal: str) -> dict:
    sys = ("You are a planning agent. Decompose the goal into 3-5 ordered sub-tasks. "
           "Return ONLY valid JSON: {\"plan\":[{\"step\":1,\"task\":\"...\",\"reasoning\":\"...\"}]}")
    raw, st = llm_call(goal, system=sys, temperature=0.4)
    try:
        data = _safe_json(raw)
    except Exception:
        data = {"plan": [{"step": 1, "task": raw, "reasoning": "Unparseable."}]}
    data["_cache"] = st
    return data


def execute_step(task: str, context: str = "") -> dict:
    sys = "You are an execution agent. Complete the task concisely. Build on prior context if given."
    prompt = f"Task: {task}"
    if context:
        prompt += f"\n\nPrior context:\n{context}"
    result, st = llm_call(prompt, system=sys, temperature=0.5)
    return {"result": result, "_cache": st}


def reflect(goal: str, results: list[str]) -> dict:
    sys = ("You are a reflection agent. Evaluate the work vs the goal. "
           "Return ONLY valid JSON: {\"score\":1-10,\"strengths\":[...],\"gaps\":[...],\"suggestions\":[...]}")
    prompt = f"Goal: {goal}\n\nWork:\n" + "\n---\n".join(results)
    raw, st = llm_call(prompt, system=sys, temperature=0.3)
    try:
        data = _safe_json(raw)
    except Exception:
        data = {"score": "?", "strengths": [], "gaps": [], "suggestions": [raw]}
    data["_cache"] = st
    return data


# ──────────────────────────────────────────────
# 6. STREAMING AGENT  (SSE generator)
# ──────────────────────────────────────────────
def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


def stream_agent(goal: str):
    t0 = time.time()

    # ── PLAN
    yield _sse("phase", {"phase": "plan", "message": "Decomposing goal into sub-tasks…"})
    tp = time.time()
    plan_data = plan(goal)
    yield _sse("plan", {**plan_data, "_time": round(time.time() - tp, 2)})

    # ── EXECUTE
    ctx = ""
    results = []
    steps = plan_data.get("plan", [])
    for i, item in enumerate(steps):
        task = item.get("task", str(item))
        yield _sse("phase", {"phase": "execute",
                              "message": f"Step {i+1}/{len(steps)}: {task[:90]}…",
                              "step": i+1, "total": len(steps)})
        te = time.time()
        res = execute_step(task, ctx)
        results.append(res["result"])
        ctx += f"\n• {task}: {res['result'][:200]}"
        yield _sse("step", {"index": i, "task": task, "result": res["result"],
                            "_cache": res["_cache"], "_time": round(time.time() - te, 2)})

    # ── REFLECT
    yield _sse("phase", {"phase": "reflect", "message": "Reflecting on work quality…"})
    tr = time.time()
    ref = reflect(goal, results)
    yield _sse("reflect", {**ref, "_time": round(time.time() - tr, 2)})

    # ── DONE
    yield _sse("done", {
        "total_time": round(time.time() - t0, 2),
        "exact_cache": exact_cache.stats,
        "semantic_cache": semantic_cache.stats,
    })


# ──────────────────────────────────────────────
# 7. FASTAPI
# ──────────────────────────────────────────────
app = FastAPI(title="Agenti v2")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.get("/api/stream")
async def api_stream(goal: str = ""):
    if not goal:
        return {"error": "No goal"}
    def gen():
        try:
            yield from stream_agent(goal)
        except Exception as e:
            yield _sse("error", {"message": str(e)})
    return StreamingResponse(gen(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})


@app.get("/api/cache")
async def api_cache():
    return {"exact": exact_cache.stats, "semantic": semantic_cache.stats}


@app.get("/", response_class=HTMLResponse)
async def index():
    return THE_HTML


# in your homework please use cli based testing instead of this
THE_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Agent Caching</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=DM+Sans:ital,wght@0,300;0,400;0,500;0,600;0,700&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
*,*::before,*::after{box-sizing:border-box;margin:0;padding:0}
:root{
  --bg:#08080a;--s1:#101013;--s2:#17171b;--s3:#1f1f25;--s4:#28282f;
  --b1:#27272e;--b2:#35353d;
  --t1:#ededf0;--t2:#9e9eab;--t3:#66666f;
  --acc:#c4ee60;--acc2:#9fd030;--accd:rgba(196,238,96,.06);
  --blue:#5b9cf5;--amber:#f5be3a;--red:#f07068;--teal:#4fd1c5;--purple:#a78bfa;
  --r:14px;--rs:9px;
  --f:'DM Sans',system-ui,sans-serif;--m:'JetBrains Mono',monospace;
  --ease:cubic-bezier(.4,0,.2,1);
}
html{font-size:15px}
body{background:var(--bg);color:var(--t1);font-family:var(--f);line-height:1.6;overflow-x:hidden}
::selection{background:var(--acc);color:var(--bg)}
::-webkit-scrollbar{width:5px}::-webkit-scrollbar-track{background:transparent}::-webkit-scrollbar-thumb{background:var(--b1);border-radius:3px}

.shell{max-width:900px;margin:0 auto;padding:2rem 1.5rem 5rem}

/* ── HEADER ── */
header{text-align:center;padding:4.5rem 0 2rem;position:relative}
header::before{content:'';position:absolute;top:-100px;left:50%;transform:translateX(-50%);width:700px;height:700px;background:radial-gradient(circle,rgba(196,238,96,.045) 0%,transparent 60%);pointer-events:none}
.logo{display:inline-flex;align-items:center;gap:.5rem;margin-bottom:1.4rem;position:relative;z-index:1}
.logo-m{width:32px;height:32px;border-radius:8px;background:linear-gradient(135deg,var(--acc),var(--acc2));display:grid;place-items:center;font-size:16px;font-weight:800;color:var(--bg)}
.logo span{font-size:1.25rem;font-weight:700;letter-spacing:-.03em}
h1{font-size:clamp(1.9rem,5vw,3.3rem);font-weight:700;letter-spacing:-.045em;line-height:1.08;margin-bottom:.65rem;position:relative;z-index:1}
h1 em{font-style:normal;color:var(--acc)}
.sub{color:var(--t2);font-size:.95rem;max-width:560px;margin:0 auto;position:relative;z-index:1;line-height:1.55}
.tags{display:flex;justify-content:center;flex-wrap:wrap;gap:.35rem;margin-top:1.5rem;position:relative;z-index:1}
.tag{font-size:.67rem;font-weight:500;padding:.25rem .62rem;border-radius:99px;border:1px solid var(--b1);color:var(--t3);background:var(--s1)}
.tag.on{border-color:color-mix(in srgb,var(--acc) 40%,transparent);color:var(--acc);background:var(--accd)}

/* ── INPUT ── */
.iw{background:var(--s1);border:1px solid var(--b1);border-radius:var(--r);padding:.9rem 1rem;margin:2.2rem 0 1rem;transition:border-color .2s var(--ease)}
.iw:focus-within{border-color:var(--acc)}
.iw textarea{width:100%;background:none;border:none;outline:none;resize:none;color:var(--t1);font-family:var(--f);font-size:.95rem;line-height:1.5;min-height:44px;max-height:160px}
.iw textarea::placeholder{color:var(--t3)}
.iw-f{display:flex;align-items:center;justify-content:space-between;margin-top:.6rem;gap:.5rem}
.iw-f .ht{font-size:.7rem;color:var(--t3)}
.go{display:inline-flex;align-items:center;gap:.4rem;padding:.5rem 1.2rem;border-radius:99px;border:none;cursor:pointer;background:var(--acc);color:var(--bg);font-family:var(--f);font-size:.8rem;font-weight:600;transition:all .15s var(--ease);flex-shrink:0}
.go:hover{transform:translateY(-1px);box-shadow:0 6px 24px rgba(196,238,96,.2)}
.go:active{transform:scale(.97)}
.go:disabled{opacity:.35;cursor:not-allowed;transform:none;box-shadow:none}
.go svg{width:14px;height:14px}

/* ── THINKING LOG ── */
.tlog{
  border:1px solid var(--b1);border-radius:var(--rs);background:var(--s1);
  max-height:160px;overflow-y:auto;padding:.55rem .75rem;margin-bottom:1rem;
  font-family:var(--m);font-size:.66rem;line-height:1.75;color:var(--t3);
  display:none;
}
.tlog.show{display:block}
.tlog .row{animation:rowIn .2s var(--ease) both}
@keyframes rowIn{from{opacity:0;transform:translateY(3px)}to{opacity:1;transform:none}}
.tlog .ts{color:var(--b2);margin-right:.4rem;user-select:none}
.tlog .c-exact{color:var(--teal)}.tlog .c-sem{color:var(--acc)}.tlog .c-live{color:var(--blue)}.tlog .c-phase{color:var(--purple)}

/* ── PHASE BAR ── */
.pbar{
  display:flex;align-items:center;gap:.6rem;padding:.6rem .9rem;border-radius:var(--r);
  background:var(--s1);border:1px solid var(--b1);margin-bottom:.75rem;
  animation:cardIn .25s var(--ease) both;
}
.pbar .dot{width:7px;height:7px;border-radius:50%;flex-shrink:0;animation:blink 1s ease-in-out infinite}
@keyframes blink{0%,100%{opacity:1}50%{opacity:.25}}
.pbar.plan .dot{background:var(--blue)}.pbar.execute .dot{background:var(--acc)}.pbar.reflect .dot{background:var(--amber)}
.pbar .msg{font-size:.78rem;color:var(--t2);flex:1}
.prog-t{width:100px;height:3px;background:var(--s3);border-radius:2px;overflow:hidden;flex-shrink:0}
.prog-f{height:100%;background:var(--acc);border-radius:2px;transition:width .35s var(--ease);width:0%}

/* ── CARDS ── */
#feed{display:flex;flex-direction:column;gap:.85rem}
.card{background:var(--s1);border:1px solid var(--b1);border-radius:var(--r);overflow:hidden;animation:cardIn .3s var(--ease) both}
@keyframes cardIn{from{opacity:0;transform:translateY(8px)}to{opacity:1;transform:none}}
.ch{display:flex;align-items:center;gap:.55rem;padding:.7rem .95rem;border-bottom:1px solid var(--b1);background:var(--s2)}
.ch .ic{width:23px;height:23px;border-radius:7px;display:grid;place-items:center;font-size:.65rem;font-weight:800;flex-shrink:0;font-family:var(--m)}
.ic.pl{background:rgba(91,156,245,.12);color:var(--blue)}.ic.ex{background:var(--accd);color:var(--acc)}.ic.rf{background:rgba(245,190,58,.1);color:var(--amber)}.ic.ca{background:rgba(79,209,197,.1);color:var(--teal)}
.ch .lbl{font-size:.76rem;font-weight:600;flex:1}
.bg{font-size:.6rem;padding:.16rem .45rem;border-radius:99px;font-weight:500;font-family:var(--m);white-space:nowrap}
.bg.exact{background:rgba(79,209,197,.1);color:var(--teal)}.bg.semantic{background:rgba(196,238,96,.08);color:var(--acc)}.bg.live{background:rgba(91,156,245,.1);color:var(--blue)}.bg.tm{background:var(--s3);color:var(--t3);font-variant-numeric:tabular-nums}
.cb{padding:.8rem .95rem;color:var(--t2);font-size:.82rem;line-height:1.65}
.cb strong{color:var(--t1);font-weight:600}
.cb p+p{margin-top:.45rem}
.cb ul{list-style:none;display:flex;flex-direction:column;gap:.25rem;margin-top:.35rem}
.cb li{padding-left:.9rem;position:relative;font-size:.8rem}
.cb li::before{content:'›';position:absolute;left:0;color:var(--acc);font-weight:700}

.stp{background:var(--s2);border:1px solid var(--b1);border-radius:var(--rs);padding:.7rem .85rem;margin-top:.45rem}
.stp:first-child{margin-top:0}
.stp-h{display:flex;align-items:center;gap:.4rem;margin-bottom:.25rem}
.stp-n{font-size:.6rem;font-weight:700;color:var(--acc);font-family:var(--m)}
.stp-t{font-size:.76rem;font-weight:600;color:var(--t1)}
.stp-r{font-size:.78rem;color:var(--t2);line-height:1.6}

.ref-g{display:flex;gap:1rem;align-items:flex-start}
.sc-ring{width:48px;height:48px;border-radius:50%;display:grid;place-items:center;font-size:1.2rem;font-weight:700;flex-shrink:0;border:3px solid var(--acc);color:var(--acc)}

.sg{display:grid;grid-template-columns:repeat(auto-fit,minmax(105px,1fr));gap:.35rem;margin-top:.4rem}
.si{background:var(--s2);border-radius:var(--rs);padding:.55rem .7rem;border:1px solid var(--b1)}
.si .v{font-size:1.05rem;font-weight:700;color:var(--t1);font-variant-numeric:tabular-nums}
.si .l{font-size:.58rem;color:var(--t3);margin-top:.1rem;text-transform:uppercase;letter-spacing:.06em}

footer{text-align:center;padding:2.5rem 0 1rem;color:var(--t3);font-size:.68rem}

@media(max-width:600px){.shell{padding:1rem 1rem 4rem}header{padding:2.5rem 0 1.5rem}h1{font-size:1.7rem}.sg{grid-template-columns:1fr 1fr}.ref-g{flex-direction:column;align-items:center;text-align:center}}
</style>
</head>
<body>
<div class="shell">
  <header>
    <div class="logo"><div class="logo-m">A</div><span>Agent Caching</span></div>
    <h1>Plan. Execute. <em>Reflect.</em></h1>
    <p class="sub">Agentic AI with planning, execution, and self-reflection — layered exact + semantic caching — every thought streamed live.</p>
    <div class="tags">
      <span class="tag on">Planning</span><span class="tag on">Execution</span>
      <span class="tag on">Reflection</span><span class="tag on">Exact Cache</span>
      <span class="tag on">Semantic Cache</span><span class="tag on">SSE Streaming</span>
      <span class="tag">gpt-4o-mini</span>
    </div>
  </header>

  <div class="iw">
    <textarea id="goal" rows="2" placeholder="Describe a goal — e.g. &quot;Design a developer relations program for an open-source database&quot;"></textarea>
    <div class="iw-f">
      <span class="ht">Streams plan → execute → reflect. Rephrase to test semantic cache.</span>
      <button class="go" id="goBtn" onclick="run()">
        <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><polygon points="5 3 19 12 5 21 5 3"/></svg>
        Run
      </button>
    </div>
  </div>

  <div class="tlog" id="tlog"></div>
  <div id="pbarWrap"></div>
  <div id="feed"></div>

  <footer>Agent Caching — FastAPI · OpenAI · Embeddings · SSE</footer>
</div>

<script>
const $ = id => document.getElementById(id);
let elapsed=0, timer=null;

function esc(s){const d=document.createElement('div');d.textContent=s;return d.innerHTML}

function badgeFor(c){
  if(!c)return'';
  if(c==='exact')return'<span class="bg exact">EXACT HIT</span>';
  if(c.startsWith('semantic'))return`<span class="bg semantic">${esc(c.toUpperCase())}</span>`;
  return'<span class="bg live">LIVE CALL</span>';
}

function tlog(msg,cls=''){
  const log=$('tlog');
  log.classList.add('show');
  const t=elapsed.toFixed(1);
  log.insertAdjacentHTML('beforeend',`<div class="row"><span class="ts">${t}s</span><span class="${cls}">${esc(msg)}</span></div>`);
  log.scrollTop=log.scrollHeight;
}

function run(){
  const goal=$('goal').value.trim();
  if(!goal)return;

  $('goBtn').disabled=true;
  $('feed').innerHTML='';
  $('tlog').innerHTML='';
  $('tlog').classList.add('show');
  $('pbarWrap').innerHTML='';
  elapsed=0;
  timer=setInterval(()=>{elapsed+=.1},100);
  tlog('Agent initialized','c-phase');

  const src=new EventSource('/api/stream?goal='+encodeURIComponent(goal));
  let totalSteps=1;

  src.addEventListener('phase',e=>{
    const d=JSON.parse(e.data);
    let bar=`<div class="pbar ${d.phase}"><div class="dot"></div><span class="msg">${esc(d.message)}</span>`;
    if(d.phase==='execute'&&d.total){
      totalSteps=d.total;
      const pct=Math.round((d.step-1)/d.total*100);
      bar+=`<div class="prog-t"><div class="prog-f" id="progFill" style="width:${pct}%"></div></div>`;
    }
    bar+=`</div>`;
    $('pbarWrap').innerHTML=bar;
    tlog(d.message,'c-phase');
  });

  src.addEventListener('plan',e=>{
    const d=JSON.parse(e.data);
    const inner=(d.plan||[]).map(s=>
      `<div class="stp"><div class="stp-h"><span class="stp-n">0${s.step}</span><span class="stp-t">${esc(s.task)}</span></div><p class="stp-r">${esc(s.reasoning||'')}</p></div>`
    ).join('');
    $('feed').insertAdjacentHTML('beforeend',`
      <div class="card">
        <div class="ch"><span class="ic pl">P</span><span class="lbl">Planning</span>${badgeFor(d._cache)}<span class="bg tm">${d._time}s</span></div>
        <div class="cb">${inner}</div>
      </div>`);
    const ct=d._cache==='exact'?'c-exact':d._cache.startsWith('semantic')?'c-sem':'c-live';
    tlog(`Plan ready — ${(d.plan||[]).length} steps [${d._cache}]`,ct);
  });

  src.addEventListener('step',e=>{
    const d=JSON.parse(e.data);
    const pf=$('progFill');
    if(pf) pf.style.width=Math.round((d.index+1)/totalSteps*100)+'%';
    $('feed').insertAdjacentHTML('beforeend',`
      <div class="card">
        <div class="ch"><span class="ic ex">${d.index+1}</span><span class="lbl">${esc(d.task)}</span>${badgeFor(d._cache)}<span class="bg tm">${d._time}s</span></div>
        <div class="cb"><p>${esc(d.result)}</p></div>
      </div>`);
    const ct=d._cache==='exact'?'c-exact':d._cache.startsWith('semantic')?'c-sem':'c-live';
    tlog(`Step ${d.index+1} complete [${d._cache}]`,ct);
  });

  src.addEventListener('reflect',e=>{
    const d=JSON.parse(e.data);
    const str=(d.strengths||[]).map(s=>`<li>${esc(s)}</li>`).join('');
    const gap=(d.gaps||[]).map(s=>`<li>${esc(s)}</li>`).join('');
    const sug=(d.suggestions||[]).map(s=>`<li>${esc(s)}</li>`).join('');
    $('feed').insertAdjacentHTML('beforeend',`
      <div class="card">
        <div class="ch"><span class="ic rf">R</span><span class="lbl">Reflection</span>${badgeFor(d._cache)}<span class="bg tm">${d._time}s</span></div>
        <div class="cb"><div class="ref-g">
          <div class="sc-ring">${d.score??'?'}</div>
          <div style="flex:1">
            ${str?`<p><strong>Strengths</strong></p><ul>${str}</ul>`:''}
            ${gap?`<p style="margin-top:.4rem"><strong>Gaps</strong></p><ul>${gap}</ul>`:''}
            ${sug?`<p style="margin-top:.4rem"><strong>Suggestions</strong></p><ul>${sug}</ul>`:''}
          </div>
        </div></div>
      </div>`);
    const ct=d._cache==='exact'?'c-exact':d._cache.startsWith('semantic')?'c-sem':'c-live';
    tlog(`Reflection — score ${d.score}/10 [${d._cache}]`,ct);
  });

  src.addEventListener('done',e=>{
    const d=JSON.parse(e.data);
    clearInterval(timer);
    $('pbarWrap').innerHTML='';
    const ec=d.exact_cache||{},sc=d.semantic_cache||{};
    $('feed').insertAdjacentHTML('beforeend',`
      <div class="card">
        <div class="ch"><span class="ic ca"></span><span class="lbl">Performance</span><span class="bg tm">${d.total_time}s total</span></div>
        <div class="cb">
          <p><strong>Exact Cache</strong></p>
          <div class="sg">
            <div class="si"><div class="v">${ec.entries??0}</div><div class="l">Entries</div></div>
            <div class="si"><div class="v">${ec.hits??0}</div><div class="l">Hits</div></div>
            <div class="si"><div class="v">${ec.misses??0}</div><div class="l">Misses</div></div>
            <div class="si"><div class="v">${ec.hit_rate??'0%'}</div><div class="l">Hit Rate</div></div>
          </div>
          <p style="margin-top:.65rem"><strong>Semantic Cache</strong> <span style="font-size:.68rem;color:var(--t3)">cosine ≥ ${sc.threshold??0.92}</span></p>
          <div class="sg">
            <div class="si"><div class="v">${sc.entries??0}</div><div class="l">Embeddings</div></div>
            <div class="si"><div class="v">${sc.hits??0}</div><div class="l">Sem Hits</div></div>
            <div class="si"><div class="v">${sc.misses??0}</div><div class="l">Sem Misses</div></div>
            <div class="si"><div class="v">${sc.hit_rate??'0%'}</div><div class="l">Sem Hit Rate</div></div>
          </div>
          <p style="margin-top:.6rem;font-size:.72rem;color:var(--t3)">Exact same query → exact hit (instant). Rephrased query → semantic hit via embedding similarity. Try it.</p>
        </div>
      </div>`);
    tlog(` Done in ${d.total_time}s`,'c-phase');
    $('goBtn').disabled=false;
    src.close();
  });

  src.addEventListener('error',e=>{
    try{const d=JSON.parse(e.data);tlog('Error: '+d.message,'c-live');
      $('feed').insertAdjacentHTML('beforeend',`<div class="card"><div class="ch"><span class="ic pl">!</span><span class="lbl">Error</span></div><div class="cb"><p>${esc(d.message)}</p></div></div>`);
    }catch(_){}
    clearInterval(timer);$('pbarWrap').innerHTML='';$('goBtn').disabled=false;src.close();
  });
  src.onerror=()=>{clearInterval(timer);$('goBtn').disabled=false;src.close()};
}

$('goal').addEventListener('input',function(){this.style.height='auto';this.style.height=this.scrollHeight+'px'});
$('goal').addEventListener('keydown',function(e){if(e.key==='Enter'&&!e.shiftKey){e.preventDefault();run()}});
</script>
</body>
</html>
"""

if __name__ == "__main__":
    print("\n   Agentic  — http://localhost:8000\n")
    uvicorn.run(app, host="0.0.0.0", port=8000)