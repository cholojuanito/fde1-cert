"""The server.

`gradio.Server` is a FastAPI app with Gradio's API engine bolted in. You get
queueing, streaming, and MCP for free, but you bring your own frontend. That
split is the point: the API is the product, the UI is disposable.
"""

import os

import gradio as gr
from gradio import Server

from llm import stream_reply
from schema import Request, Response, solve
from ui import build_demo

app = Server()

# --- The API -----------------------------------------------------------------
# The `-> str` return annotation is REQUIRED. Without it Gradio infers zero
# output components and silently returns nothing. Ask us how we know.


@app.api(name="chat")
def chat(message: str, history: list | None = None) -> str:
    """Stream a reply to one user message."""
    yield from stream_reply(message, history)


@app.api(name="extract_document_info")
def extract_document_info(request: Request) -> Response:
    """Process uploaded tax documents according to the shared contract."""
    return solve(request)


@app.get("/health")
def health() -> dict:
    """Your future ops team will thank you. Load balancers need this."""
    return {"status": "ok", "model": os.getenv("LLM_MODEL", "gpt-4.1-mini")}


demo = build_demo(extract=extract_document_info, chat=chat)
# The root mount handles Gradio requests before the API engine created by
# Server.launch, so expose the same functions in the mounted Blocks app.
with demo:
    gr.api(chat, api_name="chat")
    gr.api(extract_document_info, api_name="extract_document_info")

# Keep routes such as /health ahead of the root mount.
gr.mount_gradio_app(
    app,
    demo,
    path="/",
    max_file_size="50mb",
    show_error=True,
)


if __name__ == "__main__":
    # 0.0.0.0 so the container is reachable from the host. On your laptop this
    # is fine. On a firm network, "reachable from where, exactly?" is the
    # question this challenge wants you to go ask.
    #
    # Read the port rather than hardcoding it, so a machine that already has
    # something on 7860 can move this one without editing code.
    port = int(os.getenv("GRADIO_SERVER_PORT", "7860"))

    # Gradio announces the address it BOUND to, which is 0.0.0.0 -- not an
    # address a browser can open. Windows rejects it outright; macOS and Linux
    # quietly redirect it to localhost, which is why it looks fine on some
    # machines and broken on others. Print the one that always works.
    print(f"\n  Open http://localhost:{port} in your browser\n", flush=True)
    app.launch(server_name="0.0.0.0", server_port=port, show_error=True)
