import React, { useState } from "react";
import { api, errorMessage } from "../api/listingsApi.js";

// HW7 Part 4: one CSV upload, one pricing URL, one Run button. The backend runs the LangGraph
// ReAct agent (csv_sql, policy_retriever, calculator) and returns the timeline and results.
const DEFAULT_URL = "https://www.lyft.com/bikes/bay-wheels/pricing";

function money(v) {
  return v == null ? "-" : `$${Number(v).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
}

export default function BikeShare() {
  const [file, setFile] = useState(null);
  const [url, setUrl] = useState(DEFAULT_URL);
  const [running, setRunning] = useState(false);
  const [error, setError] = useState("");
  const [res, setRes] = useState(null);

  async function run(e) {
    e.preventDefault();
    if (!file) return setError("Choose a trip CSV first.");
    setError("");
    setRes(null);
    setRunning(true);
    try {
      const form = new FormData();
      form.append("file", file);
      form.append("url", url);
      const r = await api.post("/api/bikeshare/run", form, { timeout: 600000 });
      setRes(r.data);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setRunning(false);
    }
  }

  const v = res?.verified;
  return (
    <div className="card">
      <div className="card-header">
        <div className="page-title">Bay Wheels: Month pass or pay per ride?</div>
        <div className="subtitle">LangGraph ReAct agent with csv_sql, policy_retriever and calculator (llama3.2:3b).</div>
      </div>
      <div className="card-body">
        <form className="form bs-form" onSubmit={run}>
          <label>
            Trip CSV
            <input type="file" accept=".csv,text/csv" onChange={(e) => setFile(e.target.files?.[0] || null)} />
          </label>
          <label>
            Pricing page URL
            <input type="url" value={url} onChange={(e) => setUrl(e.target.value)} required />
          </label>
          <button className="btn primary" type="submit" disabled={running}>
            {running ? "Running..." : "Run"}
          </button>
          {error && <div className="error-text">{error}</div>}
        </form>

        {res && (
          <>
            <div className="bs-metrics">
              <span><b>Steps:</b> {res.steps}</span>
              <span><b>Total time:</b> {res.total_time_s} s</span>
              <span><b>Stop reason:</b> {res.stop_reason}</span>
              <span><b>Rows:</b> {v?.rides ?? "-"}</span>
              <span><b>Settings:</b> {res.settings.model}, prompt defense {String(res.settings.prompt_defense)}, read-only SQL {String(res.settings.tool_defense)}</span>
            </div>

            <div className="bs-grid">
              <section>
                <h3>Tool-call timeline</h3>
                <ol className="bs-timeline">
                  {res.timeline.map((t) => (
                    <li key={t.step} className={t.by === "check" ? "bs-check" : ""}>
                      <b>{t.by === "check" ? "check" : "agent"}: {t.tool}</b>{" "}
                      <code>{JSON.stringify(t.input).slice(0, 160)}</code>
                      <div className={t.success ? "bs-ok" : "bs-err"}>
                        {t.success ? "-> " + t.observation.slice(0, 180) : "-> error: " + t.error}
                      </div>
                    </li>
                  ))}
                </ol>
              </section>

              <section>
                <h3>Results</h3>
                <div className="bs-decision">
                  Decision: <b>{res.agent_decision || "(agent gave no decision)"}</b>
                  {v && (
                    <div className={res.decision_matches_tools ? "bs-ok" : "bs-err"}>
                      Tool-computed costs say: {v.decision} ({res.decision_matches_tools ? "agrees" : "does NOT agree"})
                    </div>
                  )}
                  <div className="subtitle">
                    Draft decision before the cost table: {res.draft_decision || "none"}
                  </div>
                </div>
                <p className="bs-answer">{res.final_text}</p>
                {v && (
                  <table className="table">
                    <tbody>
                      <tr><td>Pay per ride/minute total</td><td>{money(v.pay_per_use_total)}</td></tr>
                      <tr><td>Month pass fees ({v.months} months)</td><td>{money(v.membership_fees)}</td></tr>
                      <tr><td>Residual member charges (per-minute/unlock)</td><td>{money(v.membership_residual_charges)}</td></tr>
                      <tr><td>Membership total</td><td>{money(v.membership_total)}</td></tr>
                      <tr><td>Break-even vs. actual</td><td>{v.break_even_rides_per_month ?? "-"} rides/month needed, actual {v.rides_per_month}</td></tr>
                      <tr><td>Data range</td><td>{v.first_ride} to {v.last_ride} ({v.rides} rides)</td></tr>
                    </tbody>
                  </table>
                )}
                {v && (
                  <>
                    <h4>Last 8 weeks</h4>
                    <table className="table">
                      <thead><tr><th>Week</th><th>Rides</th><th>Avg min</th><th>Pay-per-use spend</th></tr></thead>
                      <tbody>
                        {v.weekly_last_8.map((w) => (
                          <tr key={w.week}><td>{w.week}</td><td>{w.rides}</td><td>{w.avg_minutes}</td><td>{money(w.pay_per_use_spend)}</td></tr>
                        ))}
                      </tbody>
                    </table>
                  </>
                )}
                <h4>Pricing citations</h4>
                <ul className="bs-cites">
                  {res.citations.slice(0, 4).map((c) => (
                    <li key={c.id}>
                      <b>[{c.id}]</b> "{c.text.slice(0, 200)}" - <a href={c.source}>{c.source}</a>, captured {c.captured_at}
                    </li>
                  ))}
                </ul>
                {res.page && (
                  <div className="subtitle">
                    Page snapshot: {res.page.origin}, captured {res.page.captured_at}, SHA-256 {res.page.sha256.slice(0, 16)}...
                  </div>
                )}
                <h4>Assumptions and caveats</h4>
                <ul className="bs-cites">
                  <li>Trips are billed per started minute (duration rounded up).</li>
                  <li>The Month pass is counted for every month that has at least one ride.</li>
                  <li>The page lists no Month-pass unlock fee for classic bikes; member unlocks are treated as $0.</li>
                  <li>The data has no rider id; the CSV is treated as one rider's trips.</li>
                </ul>
              </section>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
