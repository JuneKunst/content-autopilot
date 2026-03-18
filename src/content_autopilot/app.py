from fastapi import FastAPI

app = FastAPI(
    title="Content Autopilot",
    description="Automated content collection, processing, and publishing platform",
    version="0.1.0",
)


@app.get("/health")
async def health() -> dict:
    return {"status": "ok"}
