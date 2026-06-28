import json
import logging
import asyncio
from backend.core.agent import OptimusAgent

logger = logging.getLogger("OptimusOrchestrator")

class AgentOrchestrator:
    def __init__(self, base_agent: OptimusAgent):
        self.base_agent = base_agent

    async def _llm_generate(self, prompt: str, engine: str) -> str:
        tokens = []
        async for token in self.base_agent.process_message_stream(prompt, engine, internal=True):
            tokens.append(token)
        return "".join(tokens)

    async def route_task_stream(self, user_msg: str, engine: str, image_data: str = None, approved: bool = False):
        """State machine for specialized agent delegation."""
        
        # 1. Planner Agent determines required roles
        planning_prompt = (
            f"Classify the following user task into one of these categories: CODE, RESEARCH, or GENERAL.\n"
            f"User task: {user_msg}\n"
            f"Respond ONLY with a JSON object: {{\"type\": \"CODE|RESEARCH|GENERAL\"}}"
        )
        
        try:
            plan = await self._llm_generate(planning_prompt, engine=engine)
            
            plan_clean = plan.strip()
            if plan_clean.startswith("```json"):
                plan_clean = plan_clean[7:-3].strip()
            elif plan_clean.startswith("```"):
                plan_clean = plan_clean[3:-3].strip()
                
            task_type = json.loads(plan_clean).get("type", "GENERAL").upper()
        except Exception as e:
            logger.error(f"Orchestrator classification failed: {e}. Falling back to GENERAL.")
            task_type = "GENERAL"

        logger.info(f"Orchestrator routed task to: {task_type} Agent")

        # 2. Concurrent Delegation
        if task_type == "CODE":
            await self.base_agent._append_history("user", user_msg, image_data)
            full_response = ""
            async for token in self._run_coder_agent_stream(user_msg, engine):
                full_response += token
                yield token
            await self.base_agent._append_history("model", full_response)
            
        elif task_type == "RESEARCH":
            await self.base_agent._append_history("user", user_msg, image_data)
            full_response = ""
            async for token in self._run_research_agent_stream(user_msg, engine):
                full_response += token
                yield token
            await self.base_agent._append_history("model", full_response)
            
        else:
            async for token in self.base_agent.process_message_stream(user_msg, engine=engine, image_data=image_data, approved=approved):
                yield token

    async def _run_coder_agent_stream(self, task: str, engine: str):
        yield "**[CODER AGENT SPAWNED]**\n"
        code_prompt = f"Act as an expert software engineer. Write the code to solve this task: {task}"
        code = await self._llm_generate(code_prompt, engine)
        yield code + "\n\n"
        
        yield "**[QA AGENT SPAWNED]**\n"
        review_prompt = f"Act as a QA Reviewer. Review this code for bugs or security flaws, and provide a short summary:\n\n{code}"
        async for token in self.base_agent.process_message_stream(review_prompt, engine, internal=True):
            yield token
            
    async def _run_research_agent_stream(self, task: str, engine: str):
        yield "**[RESEARCH AGENT SPAWNED]**\n"
        research_prompt = f"Act as an expert researcher. Gather facts and structure a detailed report on: {task}"
        async for token in self.base_agent.process_message_stream(research_prompt, engine, internal=True):
            yield token
