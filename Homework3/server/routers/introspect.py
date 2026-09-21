from fastapi import APIRouter
from ..models import MemoryView, AggregateView
from ..dbimpl import sql as db

router = APIRouter()

@router.get("/memory/{user_id}", response_model=MemoryView)
def memory_view(user_id: str):
    # naive: assume session_key = user_id for default demo
    session_key = user_id
    st = db.fetch_recent_messages(session_key, limit=16)
    lt_sess = db.latest_summary(user_id, session_key, scope="session")
    lt_user = db.latest_summary(user_id, None, scope="user")
    epis = [e["fact"] for e in db.fetch_all_episodes(user_id)][:20]
    return MemoryView(short_term=[{"role":m["role"],"content":m["content"]} for m in st],
                      long_term_session_summary=lt_sess,
                      long_term_user_summary=lt_user,
                      episodic=epis)

@router.get("/aggregate/{user_id}", response_model=AggregateView)
def aggregate_view(user_id: str):
    by_day = db.aggregate_counts_by_day(user_id)
    summaries = []
    s_user = db.latest_summary(user_id, None, scope="user")
    if s_user:
        summaries.append(s_user)
    s_sess = db.latest_summary(user_id, user_id, scope="session")
    if s_sess:
        summaries.append(s_sess)
    return AggregateView(by_day=by_day, recent_summaries=summaries)
