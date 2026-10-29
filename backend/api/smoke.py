from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from backend.llm.client import LLMClient, LLMNotConfigured

router = APIRouter(tags=["smoke"])


class SmokeRequest(BaseModel):
    prompt: str = "Reply with exactly: AgentOS is connected."


@router.post("/smoke")
def smoke(payload: SmokeRequest) -> dict[str, str]:
    try:
        response = LLMClient().generate(payload.prompt)
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Groq request failed: {exc}") from exc
    return {"provider": "groq", "response": response}
