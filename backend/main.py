from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv

load_dotenv()

from backend.api.projects import router as projects_router
from backend.api.smoke import router as smoke_router
from backend.api.tasks import router as tasks_router
from backend.api.runs import router as runs_router
from backend.api.approval import router as approval_router

app = FastAPI(title="AgentOS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000", "http://127.0.0.1:3000",
        "http://localhost:3001", "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.include_router(projects_router, prefix="/api")
app.include_router(smoke_router, prefix="/api")
app.include_router(tasks_router, prefix="/api")
app.include_router(runs_router, prefix="/api")
app.include_router(approval_router, prefix="/api")


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok", "service": "agentos-api"}
