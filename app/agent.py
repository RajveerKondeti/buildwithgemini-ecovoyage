# ruff: noqa
# Copyright 2026 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import datetime
from zoneinfo import ZoneInfo
from google.cloud import firestore
import uuid

from google.adk.agents import Agent
from google.adk.apps import App
from google.adk.models import Gemini
from google import genai
from google.genai import types
from google.adk.agents.callback_context import CallbackContext
from google.adk.tools.preload_memory_tool import PreloadMemoryTool
from google.adk.tools import ToolContext
from google.cloud import storage

from google.adk.code_executors.agent_engine_sandbox_code_executor import AgentEngineSandboxCodeExecutor
from google.adk.code_executors.code_execution_utils import CodeExecutionInput
from google.adk.agents.invocation_context import InvocationContext

from vertexai.preview import rag
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from .a2ui_utils import a2ui_callback


PROJECT_ID = "qwiklabs-gcp-01-ee290fd2683c"
db = firestore.Client(project=PROJECT_ID)

async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None

def save_trip(trip_name: str, details: str, cost: float) -> str:
    """Saves a planned trip to the user's itinerary in Firestore.

    Args:
        trip_name: The name of the trip.
        details: A description of the trip and the itinerary.
        cost: The estimated cost of the trip.

    Returns:
        A string indicating success or failure.
    """
    try:
        doc_id = trip_name.replace(" ", "_").lower()
        doc_ref = db.collection("trips").document(doc_id)
        doc_ref.set({
            "name": trip_name,
            "description": details,
            "cost": cost
        })
        return f"Successfully saved trip '{trip_name}' to itinerary."
    except Exception as e:
        return f"Error saving trip: {e}"

def get_saved_trips() -> str:
    """Retrieves all saved trips from Firestore.

    Returns:
        A string listing all saved trips and their details.
    """
    try:
        trips = db.collection("trips").stream()
        trip_list = []
        for trip in trips:
            trip_data = trip.to_dict()
            trip_list.append(f"- {trip_data.get('name')}: {trip_data.get('description')} (Cost: ${trip_data.get('cost')})")
        if not trip_list:
            return "No trips saved."
        return "Saved Trips:\n" + "\n".join(trip_list)
    except Exception as e:
        return f"Error retrieving trips: {e}"


def get_weather(query: str) -> str:
    """Simulates a web search. Use it get information on weather.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    return "It's 90 degrees and sunny."


def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    else:
        return f"Sorry, I don't have timezone information for query: {query}."

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query {query} is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


async def generate_destination_image(tool_context: ToolContext, destination: str) -> str:
    """Generates a beautiful preview image of a destination.

    Args:
        tool_context: Context for managing artifacts.
        destination: A detailed description of the destination to generate an image for.

    Returns:
        A string containing the public URL of the generated image.
    """
    try:
        client = genai.Client(vertexai=True, location="global", project="qwiklabs-gcp-01-ee290fd2683c")
        result = client.models.generate_images(
            model='gemini-3.1-flash-lite-image',
            prompt=destination,
            config=types.GenerateImagesConfig(
                number_of_images=1,
                aspect_ratio="16:9"
            )
        )
        
        if not result.generated_images:
            return "Failed to generate image."

        image_bytes = result.generated_images[0].image.image_bytes
        image_name = f"destination_{uuid.uuid4().hex[:8]}.png"

        # Save to Artifacts panel
        await tool_context.save_artifact(
            artifact_name=image_name,
            content=image_bytes,
            mime_type="image/png"
        )
        
        # Upload to GCS
        bucket_name = "gemini-ecovoyage-images-2b8f9a"
        storage_client = storage.Client(project="qwiklabs-gcp-01-ee290fd2683c")
        bucket = storage_client.bucket(bucket_name)
        blob = bucket.blob(image_name)
        blob.upload_from_string(image_bytes, content_type="image/png")
        
        public_url = f"https://storage.googleapis.com/{bucket_name}/{image_name}"
        return f"Successfully generated destination image. Public URL: {public_url}"

    except Exception as e:
        return f"Error generating destination image: {e}"


def execute_python_code(tool_context: ToolContext, code: str) -> str:
    """Safely executes Python code to perform computations, such as budget splits or currency conversion.
    
    Args:
        tool_context: Context for tool execution.
        code: The Python code to execute. Print statements should be used to capture output.
        
    Returns:
        The output of the executed Python code.
    """
    executor = AgentEngineSandboxCodeExecutor(agent_engine_resource_name=None)
    code_input = CodeExecutionInput(code=code)
    invocation_context = tool_context.get_invocation_context()
    result = executor.execute_code(invocation_context, code_input)
    
    if result.stderr:
        return f"Error: {result.stderr}"
    return result.stdout or "Code executed successfully with no output."


def consult_docs(query: str) -> str:
    """Consult the Gemini EcoVoyage documentation (RAG corpus) for information about travel destinations.
    
    Args:
        query: The question or query to search the documentation for.
        
    Returns:
        The retrieved information from the documentation.
    """
    corpus_name = "projects/362551659592/locations/us-central1/ragCorpora/8370318139468021760"
    response = rag.retrieval_query(
        rag_resources=[rag.RagResource(rag_corpus=corpus_name)],
        text=query,
    )
    return str(response)


schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description="You are Gemini EcoVoyage, a helpful travel concierge designed to plan eco-friendly itineraries, manage budgets, and save trips. You remember the user's stated preferences (like dietary needs, budget constraints, and favorite destinations) from previous conversations and use them to personalize your responses. You can also generate beautiful destination preview images to inspire travelers.",
    workflow_description="Analyze the request and return structured UI when appropriate. Format itineraries using cards and tables.",
    ui_description=(
        "Keep every surface tiny and flat: ONE Card > ONE Column > a few Text rows. "
        "Never nest a Card inside a Card. "
        "Use ONLY these components: Card, Column, Row, Text, and Image. Do not use "
        "Table or Heading (unsupported), or Buttons, actions, or forms (they do "
        "nothing in adk web). "
        "You may include one Image component, but only when you have a public https "
        "URL for the image (for example the URL an image tool returns after uploading "
        "to a public bucket). Set the Image url to that exact https link, for example "
        '{"Image": {"url": {"literalString": "https://..."}}}. Never point an '
        "Image at a bare filename, an artifact name, or a non-http(s) path. If you do "
        "not have a public URL, add a short Text line noting the image instead. "
        "No markdown in text; use the usageHint property ('h1', 'h2', 'body') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or 'kind'/'data'/'metadata' objects."
    ),
    include_schema=True,
    include_examples=True,
)

root_agent = Agent(
    name="root_agent",
    model=Gemini(
        model="gemini-flash-latest",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    tools=[get_weather, get_current_time, save_trip, get_saved_trips, generate_destination_image, PreloadMemoryTool(), execute_python_code, consult_docs],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

app = App(
    root_agent=root_agent,
    name="app",
)
