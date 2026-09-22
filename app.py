"""Streamlit UI for the fully local CV parser."""
from __future__ import annotations

import io
import math
from datetime import datetime
from pathlib import Path

import pandas as pd
import streamlit as st

from cv_parser.pipeline import parse_cv
from cv_parser.schema import EXPORT_COLUMNS
from cv_parser.storage import Storage

st.set_page_config(page_title="Local CV Parser", page_icon="📄", layout="wide")
st.title("📄 Local CV Parser")
st.caption("PDF/DOCX parsing stays on this computer. Ollama is contacted only at localhost; no API key is used.")


@st.cache_resource
def get_storage() -> Storage:
    return Storage()


def local_folder_files(folder: str) -> list[Path]:
    root = Path(folder).expanduser()
    if not root.is_dir():
        raise ValueError("The supplied folder does not exist or cannot be opened.")
    files: list[Path] = []
    for path in root.rglob("*"):
        # Folders starting with "_" hold set-aside files (non-CVs, items pending a
        # manual look). Skip them so quarantining is not undone on the next scan.
        if any(part.startswith("_") for part in path.relative_to(root).parts[:-1]):
            continue
        if path.is_file() and path.suffix.lower() in {".pdf", ".docx"}:
            files.append(path)
    return files


def as_excel(rows: list[dict]) -> bytes:
    frame = pd.DataFrame([{column: row.get(column, "") for column in EXPORT_COLUMNS} for row in rows])
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        frame.to_excel(writer, index=False, sheet_name="Candidates")
    return output.getvalue()


storage = get_storage()
BATCH_SIZE = 100
with st.sidebar:
    st.header("Local processing")
    use_llm = st.toggle("Use local Ollama model", value=True)
    model = st.text_input("Ollama model", value="qwen2.5:3b")
    endpoint = st.text_input("Ollama endpoint", value="http://127.0.0.1:11434")
    enable_ocr = st.toggle("OCR scanned PDFs", value=True)
    st.divider()
    st.caption("Required for OCR: install Tesseract and add it to PATH. Required for LLM extraction: run `ollama pull qwen2.5:3b`.")

source_choice = st.radio("Input source", ["Upload files", "Process local folder"], horizontal=True)
inputs: list[tuple[str, bytes] | Path] = []
batch_label = ""
if source_choice == "Upload files":
    uploads = st.file_uploader("Drop up to 100 PDF or DOCX resumes", type=["pdf", "docx"], accept_multiple_files=True)
    if uploads:
        if len(uploads) > BATCH_SIZE:
            st.error("Please upload a maximum of 100 files at a time.")
        else:
            inputs = [(upload.name, upload.getvalue()) for upload in uploads]
            batch_label = f"Upload batch: {len(inputs)} files"
else:
    default_folder = str(Path.cwd() / "Transfered Cv Data")
    folder = st.text_input("Local folder (processed recursively)", value=default_folder)
    if st.button("Find supported files"):
        try:
            st.session_state["folder_inputs"] = local_folder_files(folder)
            st.session_state["folder_root"] = str(Path(folder).expanduser().resolve())
            st.success(f"Found {len(st.session_state['folder_inputs'])} PDF/DOCX files.")
        except ValueError as exc:
            st.error(str(exc))
    all_folder_inputs: list[Path] = st.session_state.get("folder_inputs", [])
    if all_folder_inputs:
        total_batches = math.ceil(len(all_folder_inputs) / BATCH_SIZE)
        selected_batch = st.selectbox(
            "Folder batch",
            options=range(total_batches),
            format_func=lambda index: f"Batch {index + 1} of {total_batches} "
            f"(files {index * BATCH_SIZE + 1:,}–{min((index + 1) * BATCH_SIZE, len(all_folder_inputs)):,})",
        )
        start = selected_batch * BATCH_SIZE
        inputs = all_folder_inputs[start:start + BATCH_SIZE]
        batch_label = f"Folder batch {selected_batch + 1} of {total_batches}: {len(inputs)} files"

if inputs:
    st.info(f"{batch_label}. Existing hashes within this batch are skipped as duplicates.")
    if st.button("Parse batch", type="primary"):
        batch_id = storage.create_batch(f"{batch_label} — {datetime.now():%Y-%m-%d %H:%M}")
        progress = st.progress(0, text="Starting local extraction…")
        status = st.empty()
        saved, failed, duplicates = 0, 0, 0
        for index, input_file in enumerate(inputs, start=1):
            if isinstance(input_file, Path):
                root = Path(st.session_state.get("folder_root", input_file.parent))
                filename = str(input_file.relative_to(root))
                content = input_file.read_bytes()
            else:
                filename, content = input_file
            status.caption(f"Processing {index:,}/{len(inputs):,}: {filename}")
            try:
                record = parse_cv(filename, content, enable_ocr=enable_ocr, use_llm=use_llm, model=model, endpoint=endpoint)
                if storage.add_record(batch_id, record):
                    saved += 1
                else:
                    duplicates += 1
            except Exception as exc:  # Preserve batch progress if one document is malformed.
                failed += 1
                st.warning(f"Could not process {filename}: {exc}")
            progress.progress(index / len(inputs), text=f"Processed {index:,} of {len(inputs):,} files")
        st.session_state["active_batch_id"] = batch_id
        status.success(f"Completed: {saved} saved, {duplicates} duplicates skipped, {failed} failed.")

batch_id = st.session_state.get("active_batch_id")
if batch_id:
    rows = storage.records(batch_id)
    st.subheader("Review and export")
    st.caption("Edit any uncertain fields, then save the reviewed results before export.")
    frame = pd.DataFrame(rows)
    if not frame.empty:
        configured = {
            "id": None,
            "file_hash": None,
            "evidence_json": None,
            "source_file": st.column_config.TextColumn("Source file", disabled=True, width="large"),
            "confidence": st.column_config.NumberColumn("Confidence", min_value=0.0, max_value=1.0, format="%.2f"),
            "processing_status": st.column_config.SelectboxColumn("Status", options=["Ready", "Needs review"]),
        }
        edited = st.data_editor(frame, hide_index=True, use_container_width=True, num_rows="fixed", column_config=configured, key=f"editor_{batch_id}")
        if st.button("Save reviewed edits"):
            storage.update_records(edited.to_dict("records"))
            rows = storage.records(batch_id)
            st.success("Edits saved locally.")
        st.download_button("Download Excel", data=as_excel(rows), file_name="candidate_export.xlsx",
                           mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
        csv = pd.DataFrame([{column: row.get(column, "") for column in EXPORT_COLUMNS} for row in rows]).to_csv(index=False).encode("utf-8")
        st.download_button("Download CSV", data=csv, file_name="candidate_export.csv", mime="text/csv")

        st.subheader("Field evidence")
        selected_file = st.selectbox("Candidate", rows, format_func=lambda row: row["source_file"])
        evidence = storage.evidence(selected_file["id"])
        field = st.selectbox("Field", list(evidence) or ["No evidence available"])
        if field in evidence:
            st.json(evidence[field])
