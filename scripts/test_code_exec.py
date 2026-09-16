import asyncio
from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.code_executors.code_execution_utils import CodeExecutionInput
from google.adk.agents.invocation_context import InvocationContext
from google.adk.sessions.in_memory_session_service import InMemorySessionService
from google.adk.sessions.session import Session

async def main():
    session_service = InMemorySessionService()
    session = await session_service.create_session("app", "user")
    
    context = InvocationContext(
        app_name="app",
        user_id="user",
        session=session,
        session_service=session_service,
        artifact_service=None,
        credential_service=None
    )
    
    executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=None)
    
    code_input = CodeExecutionInput(code="print('Hello from sandbox!')")
    result = executor.execute_code(context, code_input)
    print("STDOUT:", result.stdout)
    print("STDERR:", result.stderr)

if __name__ == "__main__":
    asyncio.run(main())
