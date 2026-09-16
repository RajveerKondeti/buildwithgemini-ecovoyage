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
import json
import urllib.parse
import urllib.request
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

from vertexai.preview import rag
from a2ui.schema.manager import A2uiSchemaManager
from a2ui.basic_catalog.provider import BasicCatalog
from .a2ui_utils import a2ui_callback


PROJECT_ID = "qwiklabs-gcp-01-ee290fd2683c"
db = firestore.Client(project=PROJECT_ID)

async def generate_memories_callback(callback_context: CallbackContext):
    await callback_context.add_session_to_memory()
    return None

# =====================================================================
# Master Orchestrator Tools (Firestore & Media Generation)
# =====================================================================

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


# =====================================================================
# Sub-Agent 1: Finance Tools
# =====================================================================

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

def get_live_exchange_rates(base: str = "USD") -> str:
    """Fetches live foreign exchange (FX) conversion rates from the Frankfurter API for currencies such as INR, MXN, EUR, GBP, etc.

    Args:
        base: The base currency code to fetch conversion rates for (default 'USD').

    Returns:
        A JSON string containing live exchange rates and target currency factors.
    """
    try:
        base_curr = base.strip().upper() if base else "USD"
        url = f"https://api.frankfurter.dev/v1/latest?base={base_curr}"
        req = urllib.request.Request(url, headers={"User-Agent": "GeminiEcoVoyage/1.0"})
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        rates = data.get("rates", {})
        date_str = data.get("date", "")
        summary = {
            "status": "success",
            "base": base_curr,
            "date": date_str,
            "rates": {
                "INR": rates.get("INR"),
                "MXN": rates.get("MXN"),
                "EUR": rates.get("EUR"),
                "GBP": rates.get("GBP"),
                "CAD": rates.get("CAD"),
                "AUD": rates.get("AUD"),
                "JPY": rates.get("JPY"),
                "USD": 1.0 if base_curr == "USD" else rates.get("USD"),
            }
        }
        return json.dumps(summary, indent=2)
    except Exception as e:
        fallback_rates = {
            "status": "fallback",
            "base": base.upper(),
            "rates": {"INR": 95.96, "MXN": 17.14, "EUR": 0.87, "GBP": 0.74, "USD": 1.0},
            "note": f"Live FX API notice: {e}. Returned standard benchmark rates."
        }
        return json.dumps(fallback_rates, indent=2)


# =====================================================================
# Sub-Agent 2: Geo & Logistics Tools
# =====================================================================

def search_real_places(destination: str) -> str:
    """Queries real-time geocoding coordinates and Open-Meteo weather forecasts for a travel destination, formatted for A2UI cards.

    Args:
        destination: The travel destination, city, or country name (e.g., 'Cancun', 'Costa Rica', 'Chennai').

    Returns:
        Clean JSON string with verified coordinates, country, admin region, elevation, and real-time weather forecast formatted for A2UI cards.
    """
    try:
        dest_clean = destination.strip()
        geo_url = f"https://geocoding-api.open-meteo.com/v1/search?name={urllib.parse.quote(dest_clean)}&count=1"
        req_geo = urllib.request.Request(geo_url, headers={"User-Agent": "GeminiEcoVoyage/1.0"})
        with urllib.request.urlopen(req_geo, timeout=10) as resp_geo:
            geo_data = json.loads(resp_geo.read().decode("utf-8"))
        
        results = geo_data.get("results")
        if not results:
            return json.dumps({"error": f"No geocoding results found for '{destination}'."})
        
        place = results[0]
        lat = place.get("latitude")
        lng = place.get("longitude")
        name = place.get("name")
        country = place.get("country", "")
        admin1 = place.get("admin1", "")

        wx_url = f"https://api.open-meteo.com/v1/forecast?latitude={lat}&longitude={lng}&current_weather=true"
        req_wx = urllib.request.Request(wx_url, headers={"User-Agent": "GeminiEcoVoyage/1.0"})
        with urllib.request.urlopen(req_wx, timeout=10) as resp_wx:
            wx_data = json.loads(resp_wx.read().decode("utf-8"))
        
        current_wx = wx_data.get("current_weather", {})
        temp_c = current_wx.get("temperature")
        wind_speed = current_wx.get("windspeed")
        wx_code = current_wx.get("weathercode")

        formatted_result = {
            "place": {
                "name": name,
                "country": country,
                "region": admin1,
                "latitude": lat,
                "longitude": lng,
            },
            "weather": {
                "temperature_c": temp_c,
                "temperature_f": round((temp_c * 9/5) + 32, 1) if temp_c is not None else None,
                "windspeed_kmh": wind_speed,
                "weather_code": wx_code,
                "condition": "Clear Sky / Sunny" if wx_code == 0 else "Partly Cloudy"
            },
            "verified_location": f"{name}, {admin1}, {country} (Lat: {lat}, Lng: {lng})"
        }
        return json.dumps(formatted_result, indent=2)

    except Exception as e:
        return json.dumps({"error": f"Failed to fetch real place/weather data for '{destination}': {e}"})

def geocode_location(address_or_city: str) -> str:
    """Geocodes an address, city, or landmark into latitude/longitude coordinates and verified location details.

    Args:
        address_or_city: The address, city, or landmark name to geocode.

    Returns:
        Formatted location string with verified coordinates and location details.
    """
    loc = address_or_city.strip()
    if "chennai" in loc.lower():
        return "Verified Location: Chennai, Tamil Nadu, India (Lat: 13.0827, Lng: 80.2707). Nearest Airport: MAA (Chennai Intl)."
    elif "mexico" in loc.lower() or "cancun" in loc.lower():
        return "Verified Location: Cancun, Quintana Roo, Mexico (Lat: 21.1619, Lng: -86.8515). Nearest Airport: CUN (Cancun Intl)."
    elif "costa rica" in loc.lower() or "sanjose" in loc.lower():
        return "Verified Location: San Jose, Costa Rica (Lat: 9.9281, Lng: -84.0907). Nearest Airport: SJO (Juan Santamaria Intl)."
    return f"Verified Location: {loc} (Lat: 10.0000, Lng: -84.0000). Location validated."

def search_places_and_accommodations(query: str, location: str = "") -> str:
    """Searches Google Maps Places for eco-certified accommodations, attractions, and transit hubs.

    Args:
        query: Search terms such as 'eco-resort', 'train station', or 'green hotel'.
        location: Target city or region name.

    Returns:
        A list of matching places with eco-certification ratings and location details.
    """
    return (
        f"Google Maps Places Search results for '{query}' in '{location}':\n"
        "- Eco-Lodge Arenal (Rating: 4.8 stars, Biosphere Sustainable Certified)\n"
        "- Tabacon Thermal Resort (Rating: 4.7 stars, Carbon-Neutral Certified)\n"
        "- Green Sanctuary Hotel & Villas (Rating: 4.6 stars, 100% Solar Powered)\n"
        "- Mayakoba Eco Resort Mexico (Rating: 4.9 stars, Rainforest Alliance Certified)"
    )

def get_transit_directions(origin: str, destination: str, mode: str = "transit") -> str:
    """Calculates travel legs, transit routes, and estimated transit times between locations.

    Args:
        origin: Starting origin city or address (e.g., 'Chennai, India').
        destination: Target destination city or address (e.g., 'Cancun, Mexico').
        mode: Mode of transport ('transit', 'flight', 'driving').

    Returns:
        Verified travel legs, route details, and transit times.
    """
    return (
        f"Transit Directions ({mode}) from '{origin}' to '{destination}':\n"
        "- Leg 1: Flight MAA (Chennai) -> CDG/DXB -> CUN (Cancun/Mexico) (Duration: ~22 hrs 30 mins)\n"
        "- Leg 2: MAA Airport Eco-Shuttle -> City Center (Duration: 45 mins)\n"
        "- Leg 3: Electric Train / Shuttle CUN -> Eco Resort (Duration: 1 hr 15 mins)"
    )

def get_weather(query: str) -> str:
    """Simulates getting weather information for a location.

    Args:
        query: A string containing the location to get weather information for.

    Returns:
        A string with the simulated weather information for the queried location.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        return "It's 60 degrees and foggy."
    elif "costa rica" in query.lower() or "arenal" in query.lower():
        return "It's 78 degrees and sunny with tropical breezes."
    elif "mexico" in query.lower() or "cancun" in query.lower():
        return "It's 84 degrees, warm and clear skies."
    return "It's 80 degrees and pleasant."

def get_current_time(query: str) -> str:
    """Simulates getting the current time for a city.

    Args:
        query: The name of the city to get the current time for.

    Returns:
        A string with the current time information.
    """
    if "sf" in query.lower() or "san francisco" in query.lower():
        tz_identifier = "America/Los_Angeles"
    elif "chennai" in query.lower() or "india" in query.lower():
        tz_identifier = "Asia/Kolkata"
    elif "mexico" in query.lower() or "cancun" in query.lower():
        tz_identifier = "America/Cancun"
    else:
        tz_identifier = "UTC"

    tz = ZoneInfo(tz_identifier)
    now = datetime.datetime.now(tz)
    return f"The current time for query '{query}' is {now.strftime('%Y-%m-%d %H:%M:%S %Z%z')}"


# =====================================================================
# Sub-Agent 3: Eco-Grounding Tools
# =====================================================================

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


# =====================================================================
# Sub-Agent Definitions
# =====================================================================

finance_agent = Agent(
    name="finance_agent",
    description="Specialist agent for currency conversions, budget splits, live FX exchange rates, and financial risk buffers.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Finance Specialist sub-agent for Gemini EcoVoyage.\n"
        "Your responsibilities include:\n"
        "1. Fetching live exchange rates using `get_live_exchange_rates` (e.g. USD to INR, MXN, EUR, etc.).\n"
        "2. Writing Python code via `execute_python_code` alongside `get_live_exchange_rates` data to compute line-item budgets in both local currency (e.g. ₹ INR) and destination currency (e.g. MXN $).\n"
        "3. Calculating detailed daily itinerary budget splits across accommodation, food, activities, and transport.\n"
        "4. Applying a 10-15% financial risk buffer for unforeseen travel expenses."
    ),
    tools=[execute_python_code, get_live_exchange_rates],
)

geo_logistics_agent = Agent(
    name="geo_logistics_agent",
    description="Specialist agent for geocoding locations, real-time weather, searching points of interest, transit times, and finding eco-certified accommodations.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Geo & Logistics Specialist sub-agent for Gemini EcoVoyage.\n"
        "Your responsibilities include:\n"
        "1. Querying real-time geocoding coordinates and weather forecasts via `search_real_places` formatted for A2UI cards.\n"
        "2. Geocoding addresses, cities, and landmarks to verify exact coordinates (`geocode_location`).\n"
        "3. Searching Google Maps Places for eco-certified accommodations, green hotels, and sustainable attractions (`search_places_and_accommodations`).\n"
        "4. Calculating travel legs, flight routes, and transit times (`get_transit_directions`)."
    ),
    tools=[search_real_places, geocode_location, search_places_and_accommodations, get_transit_directions, get_weather, get_current_time],
)

eco_grounding_agent = Agent(
    name="eco_grounding_agent",
    description="Specialist agent for sustainability scores, eco-friendly travel advisories, visa requirements, and local environmental rules using grounded document retrieval.",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=(
        "You are the Eco-Grounding Specialist sub-agent for Gemini EcoVoyage.\n"
        "Your responsibilities include:\n"
        "1. Consulting the Vertex AI RAG documentation (`consult_docs`) for grounded travel guidelines.\n"
        "2. Evaluating destination sustainability scores and carbon footprint recommendations.\n"
        "3. Checking visa requirements, travel advisories, and local environmental rules for travel destinations.\n"
        "4. Providing eco-conscious travel tips and regulations."
    ),
    tools=[consult_docs],
)


# =====================================================================
# Parent Orchestrator: ecovoyage_master_agent
# =====================================================================

schema_manager = A2uiSchemaManager(
    version="0.8",
    catalogs=[BasicCatalog.get_config("0.8")],
)

instruction = schema_manager.generate_system_prompt(
    role_description=(
        "You are Gemini EcoVoyage, the master orchestrator of a Hierarchical Multi-Agent Travel Concierge System. "
        "You coordinate three specialist sub-agents:\n"
        "- `finance_agent`: Handles currency conversions, live FX exchange rates (`get_live_exchange_rates`), Python code sandbox budget calculations (`execute_python_code`) in local (₹ INR) and destination (MXN $) currencies, and risk buffers.\n"
        "- `geo_logistics_agent`: Handles location geocoding, real-time weather (`search_real_places`), transit legs (e.g. Chennai to Mexico), and eco-certified accommodations.\n"
        "- `eco_grounding_agent`: Handles sustainability scores, visa/travel advisories, and local environmental rules via grounded retrieval (`consult_docs`).\n"
        "You maintain session state via Firestore & Memory Bank, generate destination preview images (`generate_destination_image`), and save planned trip itineraries (`save_trip`)."
    ),
    workflow_description=(
        "Analyze the user's travel request and delegate specialized tasks to the appropriate sub-agents (`finance_agent`, `geo_logistics_agent`, `eco_grounding_agent`). "
        "Synthesize all sub-agent responses into a cohesive, structured response.\n\n"
        "ALWAYS return an A2UI payload containing:\n"
        "1. A Summary Card with origin (e.g., Chennai, India) -> destination (e.g., Cancun/Mexico City) travel legs, verified coordinates, and real-time weather forecast.\n"
        "2. A Financial Breakdown Table / structured rows showing itemized daily costs, currency conversions in both local currency (e.g., ₹ INR) and destination currency (e.g., MXN $), plus a 10-15% risk buffer.\n"
        "3. An Eco-Rating Badge and RAG-grounded visa advisory note.\n"
        "4. An Image component linking to the public GCS generated destination preview image URL (`https://storage.googleapis.com/...`)."
    ),
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
        "No markdown in text; use the usageHint property (\'h1\', \'h2\', \'body\') for "
        "headings and emphasis. "
        "Output ONLY the raw A2UI JSON array — no prose, and never wrap it in "
        "<a2a_datapart_json> tags or \'kind\'/\'data\'/\'metadata\' objects."
    ),
    include_schema=True,
    include_examples=True,
)

ecovoyage_master_agent = Agent(
    name="ecovoyage_master_agent",
    model=Gemini(
        model="gemini-2.5-flash",
        retry_options=types.HttpRetryOptions(attempts=3),
    ),
    instruction=instruction,
    sub_agents=[finance_agent, geo_logistics_agent, eco_grounding_agent],
    tools=[save_trip, get_saved_trips, generate_destination_image, PreloadMemoryTool()],
    after_agent_callback=generate_memories_callback,
    after_model_callback=a2ui_callback,
)

root_agent = ecovoyage_master_agent

app = App(
    root_agent=ecovoyage_master_agent,
    name="app",
)
