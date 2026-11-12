import time
import uuid
import json
import functools
from typing import Optional, Callable, Any
from core.adapters.postgres import PostgresAdapter
from core.retrieve.context_budget import ContextBudgetManager

class CallLogger:
    """Logs every MCP tool invocation with agent, tokens in/out, latency, and timestamp."""

    def __init__(self, postgres_adapter: Optional[PostgresAdapter] = None):
        self.pg = postgres_adapter or PostgresAdapter()
        self.budget_manager = ContextBudgetManager()

    def record_call(
        self,
        tool: str,
        agent: Optional[str],
        tokens_in: int,
        tokens_out: int,
        latency_ms: float
    ) -> None:
        call_id = str(uuid.uuid4())
        sql = """
            INSERT INTO call_log (id, agent, tool, tokens_in, tokens_out, latency_ms, created_at)
            VALUES (%s, %s, %s, %s, %s, %s, NOW());
        """
        try:
            self.pg.execute_query(sql, (call_id, agent or "unknown", tool, tokens_in, tokens_out, latency_ms))
        except Exception as e:
            # Never crash application if telemetry logging fails
            pass

def log_mcp_call(tool_name: str):
    """Decorator to log latency, tokens in/out, and agent identity for an MCP tool."""
    logger = CallLogger()
    budget_mgr = ContextBudgetManager()

    def decorator(func: Callable):
        @functools.wraps(func)
        def wrapper(*args, **kwargs):
            start_time = time.time()
            
            # Extract agent identity if passed in kwargs or dicts
            agent = kwargs.get("agent") or kwargs.get("source_actor") or kwargs.get("reported_by")
            if not agent and "state" in kwargs and isinstance(kwargs["state"], dict):
                agent = kwargs["state"].get("written_by")
            
            # Estimate input tokens
            input_str = json.dumps({"args": [str(a) for a in args], "kwargs": {k: str(v) for k, v in kwargs.items()}})
            tokens_in, _ = budget_mgr.estimate_tokens(input_str)

            try:
                result = func(*args, **kwargs)
                latency = round((time.time() - start_time) * 1000.0, 2)
                output_str = json.dumps(result, default=str) if result is not None else ""
                tokens_out, _ = budget_mgr.estimate_tokens(output_str)

                logger.record_call(
                    tool=tool_name,
                    agent=agent,
                    tokens_in=tokens_in,
                    tokens_out=tokens_out,
                    latency_ms=latency
                )
                return result
            except Exception as e:
                latency = round((time.time() - start_time) * 1000.0, 2)
                logger.record_call(
                    tool=tool_name,
                    agent=agent,
                    tokens_in=tokens_in,
                    tokens_out=0,
                    latency_ms=latency
                )
                raise e
        return wrapper
    return decorator

