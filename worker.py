import os
import json
import uuid
import psycopg
from celery import Celery
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Initialize Celery app
celery_app = Celery(
    'worker',
    broker=os.environ.get('CELERY_BROKER_URL', 'redis://localhost:6379/0'),
    backend=os.environ.get('CELERY_RESULT_BACKEND', 'redis://localhost:6379/0')
)

@celery_app.task(name='process_agent_task', bind=True)
def process_agent_task(self, tenant_id: str, request_id: str, user_prompt: str):
    from graph import get_graph_with_postgres
    from langchain_core.messages import HumanMessage

    # Get graph connected to postgres checkpointer
    graph = get_graph_with_postgres()

    # Define state
    state = {
        "messages": [HumanMessage(content=user_prompt)],
        "tenant_id": tenant_id,
        "request_id": request_id,
        "status": "init"
    }

    # Thread config for memory checkpointer
    config = {"configurable": {"thread_id": request_id}}

    try:
        # Run graph until HITL checkpoint
        for event in graph.stream(state, config):
            # Check for pause condition in stream output
            for k, v in event.items():
                if k == 'human_review':
                    # Reached pause - mark state as paused
                    self.update_state(state='PAUSED', meta={'message': 'Execution paused for human review'})
                    return "PAUSED_FOR_REVIEW"

        # Graph execution complete
        return "COMPLETED"
    except Exception as e:
        self.update_state(state='FAILURE', meta={'exc_type': type(e).__name__, 'exc_message': str(e)})
        raise e
