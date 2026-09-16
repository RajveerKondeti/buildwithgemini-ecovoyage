# Gemini EcoVoyage 🌿✈️

> An autonomous AI travel concierge built with Google's Agent Development Kit (ADK), Vertex AI, and Cloud Run.

![demo](demo.gif)

## Overview

**Gemini EcoVoyage** plans eco-friendly travel itineraries, manages budgets, generates destination preview images, stores user travel preferences, and saves trips to Firestore. It features a responsive chat UI built with **A2UI** component rendering and streams structured UI cards directly to the web client.

## Core Capabilities & Architecture

- **Vertex AI Memory Bank**: Persists user travel preferences (dietary needs, preferred activities, budget limits) across sessions.
- **Firestore Itinerary Persistence**: Saves and retrieves planned trip itineraries to/from a Google Cloud Firestore collection (`trips`).
- **Google Cloud Storage (GCS)**: Stores generated destination images and exposes public HTTPS URLs for embedding directly in A2UI components.
- **Vertex AI RAG Engine**: Grounded RAG retrieval system indexing eco-travel guidebooks to answer destination-specific queries.
- **Imagen Media Generation (`gemini-3.1-flash-lite-image`)**: Dynamically generates high-quality destination preview images.
- **AgentEngine Sandbox Code Execution**: Secure Python code execution sandbox for calculating daily itinerary budget splits, currency conversions, and expense estimates.
- **A2UI Schema Manager (v0.8)**: Generates structured, responsive UI cards (tables, itineraries, image previews) directly in the web chat stream.

## Setup & Local Development

### Prerequisites

- Python 3.11+
- `uv` package manager
- Google Cloud SDK (`gcloud`) with active GCP authentication

### Installation

1. Install project dependencies:
   ```bash
   uv sync
   ```

2. Seed the Firestore database with sample trips:
   ```bash
   uv run scripts/seed_firestore.py
   ```

3. Run the local development server:
   ```bash
   uv run adk web
   ```

## Deployment

### Agent Engine (Vertex AI Reasoning Engine)

Deploy the agent logic to Agent Runtime:
```bash
agents-cli deploy
```

### Frontend Proxy (Cloud Run)

Deploy the FastAPI A2A proxy and chat UI to Cloud Run:
```bash
gcloud run deploy gemini-ecovoyage-frontend \
  --source ./frontend \
  --region us-east1 \
  --set-env-vars AGENT_ENGINE_RESOURCE_NAME=<RESOURCE_NAME>,AGENT_DIRECTORY=app \
  --allow-unauthenticated
```
