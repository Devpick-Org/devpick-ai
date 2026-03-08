"""FastAPI app entrypoint for ingestion domain expansion."""

from fastapi import FastAPI

app = FastAPI(title="DevPick AI Ingestion App")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
