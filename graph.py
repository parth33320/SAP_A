import json
import sqlite3
import random
from typing import Annotated, Any, Dict, List, Sequence, TypedDict
from langchain_core.messages import BaseMessage, HumanMessage, AIMessage
from langgraph.graph import StateGraph, END
from langgraph.checkpoint.memory import MemorySaver
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
    inventory = state.get("inventory_data", [])

    if not inventory:
        plan = "No inventory found to process."
    else:
        total_quantity = sum(item.get("quantity", 0) for item in inventory)
        plan = f"Plan: Reallocate {total_quantity} units across {len(inventory)} categories for optimal distribution."

    messages = list(state.get("messages", []))
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

builder.set_entry_point("global_oracle")
builder.add_edge("global_oracle", "fetch_inventory")
builder.add_edge("fetch_inventory", "draft_plan")
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

memory = MemorySaver()
graph = builder.compile(
    checkpointer=memory,
    interrupt_before=["human_review"]
)
