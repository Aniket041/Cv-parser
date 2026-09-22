# Local CV Parser

An offline Windows CV parser for PDF and DOCX resumes. It produces editable, exportable candidate data without a cloud API key or hosted AI service.

Three ways to use it:

| | entry point | install |
|---|---|---|
| **Python library** | `from cv_parser import parse_cv` | `requirements.txt` |
| **HTTP API** | `python -m api` | `requirements-api.txt` |
| **Review UI** | `streamlit run app.py` | `requirements-app.txt` |

## Layout

```
cv_parser/     the parser - import this from another project
api/           FastAPI service wrapping the parser
app.py         Streamlit review and export UI
eval/          accuracy measurement against labelled CVs
tests/         66 tests
training/      LoRA fine-tuning scaffold (dormant; see training/README.md)
data/          local SQLite results and labelled training batches
```

## Use from another project

### As a library

```python
from cv_parser import parse_cv

record = parse_cv("candidate.pdf", pdf_bytes, use_llm=True)

record.name, record.latest_company, record.confidence
record.processing_status      # "Ready" or "Needs review"
record.export_dict()          # the thirteen exported columns
record.evidence               # per-field source, supporting text and confidence
```

`parse_text(filename, text, ...)` takes already-extracted text when the caller
holds it and does not want the file read again.

### As an HTTP service

```powershell
pip install -r requirements-api.txt
python -m api                 # http://127.0.0.1:8000, interactive docs at /docs
```

| endpoint | purpose |
|---|---|
| `GET /health` | service status, whether Ollama and Tesseract are reachable, exported field list |
| `POST /parse` | one PDF or DOCX (multipart `file`) |
| `POST /parse/batch` | up to 100 files (multipart `files`); one bad document does not fail the batch |
| `POST /parse/text` | already-extracted text (JSON `text`) |

Form options on the parse endpoints: `use_llm`, `enable_ocr`, `model`, `endpoint`.

```python
import requests

with open("candidate.pdf", "rb") as handle:
    record = requests.post("http://127.0.0.1:8000/parse",
                           files={"file": handle},
                           data={"use_llm": "true"}).json()
print(record["latest_company"], record["confidence"], record["processing_status"])
```

The server binds to `127.0.0.1`. Binding elsewhere (`--host 0.0.0.0`) exposes
candidate personal data to your network and prints a warning; the parser's own
privacy guarantee still holds, since the Ollama client refuses any non-localhost
endpoint, but the HTTP surface itself has no authentication.

## Output

`source_file`, `processing_status`, `name`, `email`, `phone`, `total_experience_years`, `latest_designation`, `latest_company`, `locations`, `qualifications`, `qualification_years`, `confidence`, and `review_notes`.

## Local setup

1. Install **Python 3.11, 3.12 or 3.13** and create a virtual environment:

   ```powershell
   py -3.13 -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements-dev.txt    # everything; or pick one:
   #   requirements.txt       parser only, for importing from another project
   #   requirements-api.txt   parser + HTTP service
   #   requirements-app.txt   parser + Streamlit UI
   ```

   PyMuPDF needs the Microsoft Visual C++ 2015-2022 x64 runtime. Without it,
   PDF parsing fails with `DLL load failed while importing _extra`. Either
   install the redistributable system-wide
   (`winget install Microsoft.VCRedist.2015+.x64`, requires administrator), or
   keep the runtime inside the virtual environment:

   ```powershell
   pip install msvc-runtime
   'import os, sys; os.add_dll_directory(sys.prefix)' | Out-File -Encoding ascii .venv\Lib\site-packages\zz_vcruntime_path.pth
   ```

   The `.pth` line puts the virtual environment root on the DLL search path so
   PyMuPDF finds `msvcp140.dll`; it survives reinstalling PyMuPDF.

2. Install [Ollama](https://ollama.com/) and download the local model once:

   ```powershell
   ollama pull qwen2.5:3b
   ```

   Ollama runs locally at `http://127.0.0.1:11434`; it needs no API key. When switched off or unavailable, the parser uses employment date ranges, role/company headers and explicitly labelled current details to extract the latest designation/company. Unusual layouts may still need manual review.

3. To support scanned PDFs, install [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki) and ensure `tesseract` is available on `PATH`.

4. Launch the local app:

   ```powershell
   streamlit run app.py
   ```

Use **Upload files** for a selected batch of up to 100 files. For a large collection, choose **Process local folder**: the app finds files recursively and presents consecutive batches of 100. Select one batch, parse and review/export it, then select the next batch. Results are stored in `data/cv_parser.db`; uploaded originals are processed in memory and are not copied into that database.

Folders whose name starts with `_` are skipped by the recursive scan. Use them to
set aside files that are not CVs (`_not_cv/`) or that need a manual look
(`_needs_review/`) without deleting anything or having the next scan pick them
back up.

## Confidence and review

`confidence` measures how the values were obtained, not how many fields are
filled — a record full of confident-looking guesses scores low, by design.
Per-field scores are written to the record's evidence under `field_confidence`
and shown in the app's field evidence panel.

The strongest signal is agreement: the deterministic rules and the local model
extract the latest designation and employer independently, so when they land on
the same employer that is real evidence (0.95), and when they conflict the record
is marked down (0.3) and the disagreement is named in `review_notes`. A value
that is stated outright in the CV beats one merged from date ranges; a
qualification carrying its own passing year beats one without.

A record reaches `Ready` only when every critical field — name, email,
experience, designation, employer, qualification — clears the floor. OCR text and
documents that do not look like CVs can never be `Ready`. Expect most records to
need review: that share is the honest measure of extraction quality, and it falls
as extraction improves.

## Privacy and limitations

- The app reads local files only and sends no candidate data to external services.
- The Ollama client rejects non-localhost endpoints, so candidate data cannot be sent to a remote model by configuration.
- OCR and local LLM output can be imperfect; use the review table and field evidence before exporting.

## Extraction rules

Education output contains one highest completed degree; ties use the latest
passing year. A missing passing year remains blank. Employment experience uses a
stated total first; otherwise employment month ranges are merged, excluding gaps
and counting overlapping months once. Year-only ranges are approximate full years.
Existing saved rows are not rewritten: reparse a batch to apply these rules.

The candidate name is taken from the filename when that name can also be found in
the document text, because PDF extraction often places page headers and sidebars
above the name. The filename only locates the name; the document's own spelling is
what gets exported, and a filename matching nothing in the text is ignored.

These rules and the local model prompt are tuned by hand; they do not train model
weights. Actual fine-tuning requires reviewed CV-text/target pairs and a held-out
evaluation set. Raw CV files alone do not supply correct target labels.

## Tests

```powershell
pytest
```

## Measuring accuracy

`eval/` scores the parser against labelled CVs so changes can be judged by
evidence rather than impression. It runs fully offline.

```powershell
python eval/make_labels.py
python eval/run_eval.py --variant rules    # deterministic rules only
python eval/run_eval.py --variant llm      # rules + local Ollama model
```

It reports per-field accuracy and, more importantly, the auto-accept table: if
records at a given confidence are exported unreviewed, how many are actually
correct and how many reach a human. See `eval/README.md` for how ground truth is
built and why the parser's own output is never used as a label.
