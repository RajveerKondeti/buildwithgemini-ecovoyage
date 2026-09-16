import vertexai

PROJECT_ID = "qwiklabs-gcp-01-ee290fd2683c"
LOCATION   = "us-central1"

client = vertexai.Client(project=PROJECT_ID, location=LOCATION)

# A Memory Bank instance IS an Agent Engine instance. Default config is fine
# for the lab; it extracts general user facts/preferences automatically.
memory_bank = client.agent_engines.create()

resource_name = memory_bank.api_resource.name       # projects/.../reasoningEngines/NNN
memory_bank_id = resource_name.split("/")[-1]        # NNN  ← use this everywhere
print("MEMORY_BANK_ID:", memory_bank_id)
print("resource name :", resource_name)
