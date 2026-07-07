import json
import os
from models.icp import ICP
from config import ICP_SYSTEM_PROMPT, SESSION_ICP_PATH
from main import generate_with_retry, clean_json_response

def _default_progress(msg: str):
    print(msg)

def generate_icp(user_input: str, progress=None) -> ICP:
    """
    Call AI with ICP_SYSTEM_PROMPT and user_input.
    Parse structured JSON response into ICP model.
    Cache result to session_icp.json.
    """
    if progress is None:
        progress = _default_progress
        
    prompt = ICP_SYSTEM_PROMPT.format(user_input=user_input)
    
    progress("Generating Ideal Customer Profile (ICP)...")
    text = generate_with_retry(prompt, progress=progress)
    
    if not text:
        raise ValueError("AI failed to generate ICP.")
        
    try:
        data = json.loads(clean_json_response(text))
        icp = ICP(**data)
        save_icp(icp)
        progress("ICP generated successfully.")
        return icp
    except Exception as e:
        progress(f"Error parsing ICP JSON: {e}")
        progress(f"Raw response: {text}")
        raise ValueError(f"Failed to parse ICP: {e}")

def load_cached_icp() -> ICP | None:
    """Load ICP from session_icp.json if it exists. Return None if not found."""
    try:
        with open(SESSION_ICP_PATH, "r") as f:
            return ICP(**json.load(f))
    except Exception:
        return None

def save_icp(icp: ICP):
    """Write ICP to session_icp.json."""
    with open(SESSION_ICP_PATH, "w") as f:
        json.dump(icp.model_dump(), f, indent=2)

def run_icp_generation(user_input: str, state) -> None:
    """
    Thread-executor wrapper for app.py.
    Emits SSE event: {"type": "icp_generated", "icp": icp.model_dump()}
    Sets state.status = "awaiting_icp_approval"
    """
    state.progress("Starting ICP generation...")
    try:
        icp = generate_icp(user_input, progress=state.progress)
        # Emit the ICP as a JSON message via SSE (state.progress bridges to async)
        state.progress(json.dumps({
            "type": "icp_generated",
            "icp": icp.model_dump()
        }))
        state.status = "awaiting_icp_approval"
        state.progress("ICP generated. Waiting for approval.")
    except Exception as e:
        state.progress(f"Error in ICP generation: {e}")
        state.status = "failed"
