import { Client } from "https://cdn.jsdelivr.net/npm/@gradio/client/dist/index.min.js";

const client = await Client.connect(window.location.origin);
const form = document.getElementById("form");
const fileInput = document.getElementById("files");
const selection = document.getElementById("selection");
const status = document.getElementById("status");
const results = document.getElementById("results");
const submit = document.getElementById("submit");

fileInput.addEventListener("change", () => {
  const names = [...fileInput.files].map((file) => file.name);
  selection.textContent = names.length
    ? `${names.length} file${names.length === 1 ? "" : "s"} selected: ${names.join(", ")}`
    : "No files selected.";
});

async function encodeFile(file) {
  const buffer = await file.arrayBuffer();
  const bytes = new Uint8Array(buffer);
  let binary = "";
  const chunkSize = 0x8000;

  for (let offset = 0; offset < bytes.length; offset += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(offset, offset + chunkSize));
  }

  return {
    filename: file.name,
    content_base64: btoa(binary),
    mime_type: file.type || "application/pdf",
  };
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  if (!fileInput.files.length) return;

  submit.disabled = true;
  status.textContent = "Encoding and processing documents...";
  results.textContent = "";

  try {
    const files = await Promise.all([...fileInput.files].map(encodeFile));
    const job = client.submit("/process", [{ files }]);
    let receivedResult = false;

    for await (const event of job) {
      if (event.type === "data") {
        receivedResult = true;
        const result = event.data[0];
        results.textContent = typeof result === "string"
          ? result
          : JSON.stringify(result, null, 2);
      }
      if (event.type === "error") {
        throw new Error(JSON.stringify(event.data));
      }
    }

    if (!receivedResult) throw new Error("The processing endpoint returned no result.");
    status.textContent = "Processing complete.";
  } catch (error) {
    status.textContent = "Processing failed.";
    results.textContent = error instanceof Error ? error.message : String(error);
  } finally {
    submit.disabled = false;
  }
});
