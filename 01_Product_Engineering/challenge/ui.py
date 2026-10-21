from collections.abc import Callable, Iterator
from pathlib import Path

import gradio as gr

from schema import Request, Response


def build_demo(
    extract: Callable[[Request], Response],
    chat: Callable[[str, list], Iterator[str]],
) -> gr.Blocks:
    def process_file(path: str | None) -> dict:
        if not path:
            raise gr.Error("Please upload one PDF")
        request = Request(
            files=[gr.FileData(
                path=path,
                orig_name=Path(path).name,
                mime_type="application/pdf",
                size=Path(path).stat().st_size,
            )]
        )
        try:
            return extract(request).model_dump(mode="json")
        except ValueError as exc:
            raise gr.Error(str(exc)) from exc

    def chat_with_history(message: str, history: list) -> Iterator[str]:
        # Gradio 6 can represent message content as text blocks; the existing
        # model wrapper expects ordinary strings for this text-only interface.
        messages = []
        for turn in history:
            content = turn["content"]
            if isinstance(content, list):
                content = "\n".join(
                    block["text"] for block in content if block.get("type") == "text"
                )
            messages.append({"role": turn["role"], "content": content})
        yield from chat(message, messages)

    with gr.Blocks(title="Bifrost K-1 Reviewer") as demo:
        with gr.Tab("K-1 Documents"):
            files = gr.File(type="filepath", file_count="single", file_types=[".pdf"])
            output = gr.JSON(label="Extraction Result")

            gr.Button("Upload").click(
                fn=process_file,
                inputs=files,
                outputs=output,
                api_name=False,
                queue=False,
            )
        with gr.Tab("Chat"):
            gr.ChatInterface(
                fn=chat_with_history,
                description="Use text prompts for the Step 11 general-capability checks.",
                api_name="chat_ui",
                api_visibility="private",
                autofocus=False,
            )
    return demo
