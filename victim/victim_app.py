"""Víctima: chatbot de soporte con langchain 1.4.7 (config estándar de docs).

Espejo del lab n8n: webhook /chat {session_id, message} -> {output}.
Memoria = SqliteSaver (checkpointer) en SQLite, thread_id = session_id.
El análogo del vector n8n (leer executions?includeData=true en el proceso
main) es GET /history/{sid}: carga el estado COMPLETO del thread en el
proceso principal del server.
"""
import os
import sqlite3
import time

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from langchain_openai import ChatOpenAI
from langgraph.checkpoint.sqlite import SqliteSaver

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(REPO_ROOT, "data")
os.makedirs(DATA_DIR, exist_ok=True)
DB_PATH = os.environ.get("VICTIM_DB", os.path.join(DATA_DIR, "victim_chat.sqlite"))
API_KEY = os.environ.get("LLM_API_KEY") or open(
    os.environ["LLM_API_KEY_FILE"]).read().strip()
BASE_URL = os.environ.get("LLM_BASE_URL", "https://api.z.ai/api/coding/paas/v4")
MODEL = os.environ.get("VICTIM_MODEL", "glm-5.3-flash")

app = FastAPI()

# SqliteSaver a nivel de proceso (patrón estándar de los docs para un solo proceso)
_saver = SqliteSaver(sqlite3.connect(DB_PATH, check_same_thread=False))

_llm = ChatOpenAI(
    model=MODEL,
    api_key=API_KEY,
    base_url=BASE_URL,
    max_retries=1,
    timeout=90,
    max_tokens=4096,  # fix F-005 del lab n8n: default pequeño quema en reasoning
)


def build_agent():
    # create_agent con checkpointer: persiste el historial completo por thread
    from langchain.agents import create_agent

    return create_agent(_llm, tools=[], checkpointer=_saver)


_agent = build_agent()


class ChatIn(BaseModel):
    session_id: str
    message: str


@app.get("/healthz")
def healthz():
    return {"ok": True}


@app.post("/chat")
def chat(body: ChatIn):
    t0 = time.time()
    cfg = {"configurable": {"thread_id": body.session_id}}
    try:
        result = _agent.invoke(
            {"messages": [{"role": "user", "content": body.message}]}, cfg
        )
        msgs = result.get("messages", [])
        out = ""
        finish = None
        if msgs:
            last = msgs[-1]
            out = getattr(last, "content", "") or ""
            # finish_reason real de la API si está disponible
            meta = getattr(last, "response_metadata", {}) or {}
            finish = (meta.get("finish_reason")
                      or (meta.get("model_kwargs") or {}).get("finish_reason"))
        usage = None
        try:
            um = result.get("messages")[-1].usage_metadata
            usage = um
        except Exception:
            pass
        return {
            "output": out,
            "session_id": body.session_id,
            "finish_reason": finish,
            "usage": usage,
            "elapsed_s": round(time.time() - t0, 2),
        }
    except Exception as e:  # el error se registra pero el input YA fue persistido
        return {
            "output": "",
            "session_id": body.session_id,
            "error": f"{type(e).__name__}: {e}",
            "elapsed_s": round(time.time() - t0, 2),
        }


@app.get("/history/{session_id}")
def history(session_id: str):
    """Análogo de leer executions?includeData=true en el proceso main de n8n:
    carga TODO el checkpoint (lista completa de mensajes) en memoria."""
    cfg = {"configurable": {"thread_id": session_id}}
    try:
        state = _saver.get_tuple(cfg)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"{type(e).__name__}: {e}")
    if state is None:
        return {"session_id": session_id, "messages": 0, "chars": 0}
    msgs = state.checkpoint.get("channel_values", {}).get("messages", [])
    chars = sum(len(getattr(m, "content", "") or "") for m in msgs)
    return {"session_id": session_id, "messages": len(msgs), "chars": chars}


@app.delete("/history/{session_id}")
def delete_history(session_id: str):
    """Borrado por API (equivalente al delete de executions en n8n)."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()
    cur.execute(
        "DELETE FROM checkpoints WHERE thread_id = ?", (session_id,)
    )
    cur.execute(
        "DELETE FROM writes WHERE thread_id = ?", (session_id,)
    )
    conn.commit()
    cur.execute("PRAGMA freelist_count")
    free = cur.fetchone()[0]
    cur.execute("PRAGMA page_count")
    pages = cur.fetchone()[0]
    conn.close()
    return {"deleted": True, "freelist_pages": free, "page_count": pages}
