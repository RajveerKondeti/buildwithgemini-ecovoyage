from vertexai.preview import rag
from vertexai.preview.rag.utils import resources as rr
import vertexai

PROJECT_ID = "qwiklabs-gcp-01-ee290fd2683c"
LOCATION   = "us-central1"
GCS_PATH   = "gs://gemini-ecovoyage-images-2b8f9a/rag/"

vertexai.init(project=PROJECT_ID, location=LOCATION)

# Switch to serverless mode
cfg = f"projects/{PROJECT_ID}/locations/{LOCATION}/ragEngineConfig"
rag.update_rag_engine_config(rag_engine_config=rag.RagEngineConfig(
    name=cfg,
    rag_managed_db_config=rag.RagManagedDbConfig(mode=rr.Serverless()),
))

# Create the corpus
corpus = rag.create_corpus(
    display_name="ecovoyage-docs",
    embedding_model_config=rag.EmbeddingModelConfig(
        publisher_model="publishers/google/models/text-embedding-005"),
)
print("CORPUS_NAME:", corpus.name)

# Import files
resp = rag.import_files(
    corpus_name=corpus.name,
    paths=[GCS_PATH],
    transformation_config=rag.TransformationConfig(
        chunking_config=rag.ChunkingConfig(chunk_size=512, chunk_overlap=100)),
)
print("imported:", resp.imported_rag_files_count)
