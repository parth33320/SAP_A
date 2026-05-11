import json
import sqlite3
import random
from typing import Annotated, Any, Dict, List, Sequence, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from psycopg_pool import ConnectionPool
from langgraph.checkpoint.postgres import PostgresSaver
import os
import tenacity

# Ensure task logging function
def log_task(request_id: str, status: str, payload: str):
    conn = sqlite3.connect('mock_sap.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS task_queue (id INTEGER PRIMARY KEY AUTOINCREMENT, request_id TEXT, status TEXT, payload TEXT, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute(
        "INSERT INTO task_queue (request_id, status, payload) VALUES (?, ?, ?)",
        (request_id, status, payload)
    )
    conn.commit()
    conn.close()

# DPO Logger
def log_dpo(prompt: str, chosen: str, rejected: str):
    data = {
        "prompt": prompt,
        "chosen": chosen,
        "rejected": rejected
    }
    with open("dpo_training_data.json", "a") as f:
        f.write(json.dumps(data) + "\n")

# State definition
class AgentState(TypedDict):
    messages: Annotated[Sequence[BaseMessage], "add"]
    tenant_id: str
    request_id: str
    inventory_data: List[Dict[str, Any]]
    drafted_plan: str
    status: str
    # Sprint-3 additions
    a2a_transcript: List[Dict[str, Any]] # running negotiation log
    pending_po: Dict[str, Any] # final Purchase Order

# Node 1: Global Oracle (Prescriptive Analytics Stub)
def global_oracle(state: AgentState) -> Dict:
    messages = list(state.get("messages", []))

    # Simulate a macroeconomic alert (20% chance)
    if random.random() < 0.2:
        alert = "WARNING: Port strike detected in Taiwan. Transit times may increase by 14 days."
        messages.append(AIMessage(content=f"[GLOBAL ORACLE ALERT]: {alert}"))

    return {"messages": messages}

# Node 2: MCP Inventory Query (with Exponential Backoff)
@tenacity.retry(
    wait=tenacity.wait_exponential(multiplier=1, min=2, max=10),
    stop=tenacity.stop_after_attempt(3),
    retry=tenacity.retry_if_exception_type(Exception)
)
def fetch_inventory(state: AgentState) -> Dict:
    from mcp_server import read_inventory
    import time

    import os
    if os.environ.get("CHAOS_DROP_CONNECTION") == "1":
        if random.random() < 0.7:
            raise ConnectionError("MCP Connection unexpectedly dropped! (Chaos Test)")

    result_json = read_inventory(state["tenant_id"])
    try:
        inventory = json.loads(result_json)
    except Exception:
        inventory = []

    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=f"Fetched inventory for {state['tenant_id']}: {len(inventory)} items found."))
    return {"inventory_data": inventory, "messages": messages}

# Node 3: Plan Drafter
def draft_plan(state: AgentState) -> Dict:
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate

    inventory = state.get("inventory_data", [])
    messages = list(state.get("messages", []))

    # Extract the user's specific request
    user_request = next((m.content for m in messages if isinstance(m, HumanMessage)), "")

    if not inventory:
        plan = "No inventory found to process."
    else:
        # Instantiate ChatModel
        llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)

        # Construct dynamic system prompt
        system_prompt = """You are an intelligent Supply Chain Orchestrator.
Your goal is to draft a logistics reallocation plan based on the provided inventory data and the user's specific request.

Inventory Data:
{inventory_data}

User Request:
{user_request}

Based on this, draft a specific, actionable, and logical reallocation plan. Only output the plan.
"""
        prompt = ChatPromptTemplate.from_template(system_prompt)
        chain = prompt | llm

        inventory_str = json.dumps(inventory, indent=2)

        response = chain.invoke({
            "inventory_data": inventory_str,
            "user_request": user_request
        })

        plan = f"Plan: {response.content}"

    messages.append(AIMessage(content=f"Drafted Plan: {plan}"))

    log_task(state["request_id"], "DRAFTED", json.dumps({"plan": plan}))

    return {"drafted_plan": plan, "messages": messages, "status": "drafted"}

# HITL Dummy Node
def human_review(state: AgentState) -> Dict:
    return {}

# Node 4: Executor (Post-HITL)
def execute_plan(state: AgentState) -> Dict:
    messages = list(state.get("messages", []))
    messages.append(AIMessage(content="Plan executed successfully."))
    log_task(state["request_id"], "EXECUTED", "Plan executed.")
    return {"messages": messages, "status": "executed"}

import asyncio
async def a2a_negotiate(state: AgentState) -> Dict:
    """
    Simulates an external Supplier-Agent handshake and returns a JSON quote.
    The LLM call is wrapped with asyncio.to_thread() so we never block the
    event loop.
    """
    from langchain_openai import ChatOpenAI
    from langchain_core.prompts import ChatPromptTemplate

    inventory      = state.get("inventory_data", [])
    messages       = list(state.get("messages", []))
    a2a_transcript = list(state.get("a2a_transcript", []))

    # Identify SKUs that are stocked-out
    stockouts = [item for item in inventory if item.get("quantity", 0) == 0]
    if not stockouts:
        return {}            # nothing to negotiate

    # Build Supplier-Agent prompt
    prompt_tmpl = ChatPromptTemplate.from_template("""
You are a Supplier Agent. Provide a quote ONLY as valid JSON with the keys:
"restock_quantity", "price_per_unit", "lead_time_days".
SKUs needing restock:
{stockouts}
""")
    llm = ChatOpenAI(model="gpt-3.5-turbo", temperature=0)
    chain = prompt_tmpl | llm
    stockouts_str = json.dumps(stockouts, indent=2)

    # Long-running external call – run in thread
    quote_str = await asyncio.to_thread(
        lambda: chain.invoke({"stockouts": stockouts_str}).content
    )

    try:
        quote_json = json.loads(quote_str)
    except Exception:
        quote_json = {}

    # Record the exchange
    a2a_transcript.append({
        "role":      "supplier_agent",
        "request":   stockouts,
        "response":  quote_json
    })
    messages.append(AIMessage(content=f"Supplier Agent quote received: {quote_json}"))
    return {"a2a_transcript": a2a_transcript, "messages": messages}

def draft_po(state: AgentState) -> Dict:
    """
    Converts the Supplier quote into a formal PO dictionary and stores it.
    """
    import random
    a2a_transcript = state.get("a2a_transcript", [])
    if not a2a_transcript:
        return {}

    latest = a2a_transcript[-1]
    quote  = latest.get("response", {})
    po = {
        "po_id":           f"PO-{random.randint(100000, 999999)}",
        "items":           latest.get("request", []),
        "restock_quantity": quote.get("restock_quantity"),
        "price_per_unit":   quote.get("price_per_unit"),
        "lead_time_days":   quote.get("lead_time_days"),
        "supplier":         "External Supplier Agent"
    }

    messages = list(state.get("messages", []))
    messages.append(AIMessage(content=f"Drafted Purchase Order: {json.dumps(po)}"))
    return {"pending_po": po, "messages": messages, "status": "drafted"}

# Router for Intent
def route_intent(state: AgentState):
    """
    Decide next hop after fetch_inventory.

    • If any SKU has quantity==0  ➜ a2a_negotiate
    • Else use the prior heuristic to decide between draft_plan or end
    """
    inventory = state.get("inventory_data", [])
    if any(item.get("quantity", 0) == 0 for item in inventory):
        return "a2a_negotiate"

    messages = state.get("messages", [])
    user_message = next((m.content for m in messages if isinstance(m, HumanMessage)), "").lower()

    informational_keywords = ["show", "list", "what", "how many", "level", "stock", "inventory"]
    action_keywords        = ["draft", "plan", "reallocate", "optimize", "move", "ship", "send", "update"]

    has_action = any(word in user_message for word in action_keywords)
    has_info   = any(word in user_message for word in informational_keywords)

    if has_action:
        return "draft_plan"
    elif has_info:
        return "end"
    else:
        return "draft_plan"

# Router for HITL
def route_approval(state: AgentState):
    status = state.get("status")
    if status == "approved":
        return "execute_plan"
    else:
        return "end"

# Build Graph
builder = StateGraph(AgentState)

builder.add_node("global_oracle", global_oracle)
builder.add_node("fetch_inventory", fetch_inventory)
builder.add_node("draft_plan", draft_plan)
builder.add_node("human_review", human_review)
builder.add_node("execute_plan", execute_plan)
builder.add_node("a2a_negotiate", a2a_negotiate)
builder.add_node("draft_po", draft_po)

builder.set_entry_point("global_oracle")
builder.add_edge("global_oracle", "fetch_inventory")

builder.add_conditional_edges(
"fetch_inventory",
route_intent,
{
"a2a_negotiate": "a2a_negotiate",
"draft_plan": "draft_plan",
"end": END
}
)

builder.add_edge("a2a_negotiate", "draft_po")
builder.add_edge("draft_po", "human_review")

builder.add_edge("draft_plan", "human_review")

builder.add_conditional_edges(
    "human_review",
    route_approval,
    {
        "execute_plan": "execute_plan",
        "end": END
    }
)

builder.add_edge("execute_plan", END)

def get_graph():
    return builder.compile(interrupt_before=["human_review"])

def get_graph_with_postgres():
    connection_kwargs = {
        "autocommit": True,
        "prepare_threshold": 0,
    }

    DB_URI = os.environ.get("POSTGRES_DB_URI", "postgresql://postgres:postgres@localhost:5432/postgres")
    pool = ConnectionPool(conninfo=DB_URI, max_size=20, kwargs=connection_kwargs)
    checkpointer = PostgresSaver(pool)
    checkpointer.setup()

    return builder.compile(
        checkpointer=checkpointer,
        interrupt_before=["human_review"]
    )

if __name__ == "__main__":
    graph = get_graph_with_postgres()
