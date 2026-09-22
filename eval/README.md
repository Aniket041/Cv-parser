# CV parser evaluation

Measures how accurate the parser actually is, so changes can be judged by
evidence rather than impression. Runs fully offline.

## Usage

```powershell
python eval/make_labels.py                       # build labels.json from ground truth
python eval/run_eval.py --variant rules          # deterministic rules only
python eval/run_eval.py --variant llm            # rules + local Ollama model
python eval/run_eval.py --variant rules --source files   # include PDF/DOCX extraction
```

## What is ground truth

`eval/labels_manual.json` — one entry per CV, keyed by the file's SHA-256, holding
the correct value for each of the nine exported fields plus a note explaining the
judgement calls (which role is "latest", which qualification is highest, whether a
stated total overrides computed dates).

`draft_answers` in `data/training/batch_0001/examples.jsonl` is **the parser's own
output**. It is never used as ground truth. Scoring a parser against its own
output measures nothing and reports near-perfect accuracy however wrong it is.

Current labels are assistant-reviewed from the extracted CV text, not
human-certified. They are good enough to catch gross failures and to compare two
variants; they are not a certification of accuracy.

## Field definitions that need one

Most fields are self-evident. Two are not, and a label set is worthless if it is
inconsistent about them.

**`locations` means the candidate's own location** — their contact address,
stated current location, or the city of their current role. It is *not* every
place named in the CV. A project manager who lists twenty site cities across a
30-year career is located in one of them, and the other nineteen are project
history. This matters because the field exists so a recruiter can filter on where
someone is, and a list of every city ever mentioned cannot answer that.

**`qualifications` means the highest completed qualification**, one entry, with
its own passing year. Courses marked pursuing, expected or discontinued are
excluded, as are certificates and short courses. Ties go to the most recent.
Under the project's documented ranking a post-graduate diploma still sorts as a
diploma, i.e. below a bachelor's degree.

## How scoring works

Each field is scored twice:

- **strict** — normalised exact match
- **lenient** — field-appropriate tolerance: `+/- 0.5` years on experience, last
  10 digits on phone, legal suffixes ignored on company (`Capacite Infraprojects`
  == `CAPACITE INFRAPROJECTS LTD`), degree level ignoring stream (`Diploma` ==
  `Diploma in Civil Engineering`), F1 over members for `locations`.

Lenient is the headline number. `Sr VP Project` vs `Sr. VP Project` is not a bug
worth chasing; `Page of` vs a candidate name is.

Both blank counts as agreement — the parser correctly found nothing.

## Reading the output

`macro field accuracy` is the average across fields. `CVs with every field right`
is the strict per-document bar; with nine fields it compounds fast and stays low
long after individual fields look healthy.

The **auto-accept table** is the one that decides shipped accuracy. It answers:
if records at or above a confidence threshold are exported without review, how
many are actually correct, and how many go to a human? 99% shipped accuracy comes
from this gate, not from the model. A high auto-accept share with low accuracy in
that bucket means the confidence score is not protective.

Per-CV detail and a per-error list are written to `eval/results/`.

## Sample size

Below ~25 labelled CVs the per-field percentages have a margin of error near
+/-20 points. Failure *patterns* are visible much earlier than reliable numbers.
Target 100+ before trusting a comparison between two variants.
