import re
import sqlite3
import json
from mcp.server.fastmcp import FastMCP

mcp = FastMCP("ZeroTrustLogistics")

def is_safe_query(query: str) -> bool:
    unsafe_keywords = ["DROP", "DELETE", "UPDATE", "INSERT", "ALTER", "TRUNCATE"]
    upper_query = query.upper()
    for keyword in unsafe_keywords:
        if re.search(rf"\b{keyword}\b", upper_query):
            return False
    return True

def log_sql(query: str, tenant_id: str):
    conn = sqlite3.connect('mock_sap.db')
    cursor = conn.cursor()
    cursor.execute("CREATE TABLE IF NOT EXISTS mcp_sql_logs (id INTEGER PRIMARY KEY AUTOINCREMENT, query TEXT, tenant_id TEXT, timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP)")
    cursor.execute("INSERT INTO mcp_sql_logs (query, tenant_id) VALUES (?, ?)", (query, tenant_id))
    conn.commit()
    conn.close()

@mcp.tool()
def read_inventory(tenant_id: str) -> str:
    """Read inventory for a specific tenant.

    Args:
        tenant_id: The ID of the tenant (e.g., 'Tenant_A' or 'Tenant_B').
    """
    conn = sqlite3.connect('mock_sap.db')
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()

    query = f"SELECT * FROM inventory WHERE tenant_id = '{tenant_id}'"
    # Even though we use formatting for demo of capturing the exact string query,
    # we enforce guardrails:
    if not is_safe_query(query):
        return json.dumps({"error": "Unsafe query detected. Operation blocked."})

    log_sql(query, tenant_id)

    try:
        cursor.execute(query)
        rows = cursor.fetchall()
    except sqlite3.Error as e:
        conn.close()
        return json.dumps({"error": str(e)})

    conn.close()

    result = [dict(row) for row in rows]
    return json.dumps(result)

if __name__ == "__main__":
    mcp.run()
