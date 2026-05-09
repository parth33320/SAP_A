import os
import sys
import uuid
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ChaosTest")

# Add parent dir to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from graph import graph

def run_chaos_test():
    # Enable chaos monkey
    os.environ["CHAOS_DROP_CONNECTION"] = "1"

    thread_id = str(uuid.uuid4())
    config = {"configurable": {"thread_id": thread_id}}

    state = {
        "messages": [],
        "tenant_id": "Tenant_A",
        "request_id": str(uuid.uuid4()),
        "status": "init"
    }

    logger.info("Starting graph with Chaos Monkey enabled. Expect retries.")

    try:
        for event in graph.stream(state, config):
            for node_name, value in event.items():
                if isinstance(value, dict) and "messages" in value:
                     logger.info(f"Graph step complete [{node_name}]. Messages: {[m.content for m in value.get('messages', [])]}")

        logger.info("Graph reached interrupt.")
        # approve it to test the route
        graph.update_state(config, {"status": "approved"})
        for event in graph.stream(None, config):
             for node_name, value in event.items():
                 if isinstance(value, dict) and "messages" in value:
                     logger.info(f"Graph step complete [{node_name}]. Messages: {[m.content for m in value.get('messages', [])]}")
        logger.info("Graph completed successfully despite chaos.")
    except Exception as e:
        logger.error(f"Graph failed: {e}")
    finally:
        del os.environ["CHAOS_DROP_CONNECTION"]

if __name__ == "__main__":
    run_chaos_test()
