from collections.abc import Callable
from pathlib import Path

import gradio as gr

from schema import Request, Response


def build_demo(
    extract: Callable[[Request], Response]
) -> gr.Blocks:
    def process_files(paths: list[str] | None) -> dict:
        if not paths:
            raise gr.Error("Please upload at least one PDF")
        request = Request(
            files=[
                gr.FileData(
                    path=path,
                    orig_name=getattr(path, "orig_name", Path(path).name),
                    mime_type="application/pdf",
                    size=Path(path).stat().st_size,
                )
                for path in paths
            ]
        )
        return extract(request).model_dump(mode="json")

    with gr.Blocks(title="Bifrost K-1 Reviewer") as demo:
        files = gr.File(type="filepath", file_count="multiple", file_types=[".pdf"])
        output = gr.JSON(label="Extraction Result")

        gr.Button("Upload").click(
            fn=process_files,
            inputs=files,
            outputs=output,
            api_name=False,
            queue=False,
        )
    return demo
