# Student A: how to finish your half (in order)

Everything marked FILL-IN in `docs/` needs a number from a run on your machine. Search for it:
`grep -rn "FILL-IN" docs eval`

## 0. Set up (10 min)
```bash
make install                      # .venv with api + indexer deps
pip install reportlab fakeredis   # dev-only, for the tests
make test && make lint            # 93 tests (63 api + 30 indexer) should pass offline
sudo apt install tesseract-ocr poppler-utils     # WSL/Ubuntu, for OCR locally
ollama pull nomic-embed-text && ollama pull llama3.2:3b
OLLAMA_HOST=0.0.0.0 ollama serve  # leave running
```

## 1. Corpus (30 min)
```bash
python corpus/fetch.py --list https://www.nu.edu.pk/Downloads   # find files; edit corpus/sources.yaml
make fetch                                                      # writes corpus/raw/ and MANIFEST.md
python corpus/fetch.py --verify
python corpus/inspect_corpus.py                                 # pages, scans, tables -> docs/CORPUS.md
pdffonts corpus/raw/<scanned>.pdf                               # empty list = scan; paste into CORPUS.md
```
Open the first PR now with the corpus choice (the case study asks for it).
Commit `corpus/MANIFEST.md` and `corpus/sources.yaml`, never `corpus/raw/`.
If the 2023 rules do not download, pick another genuine version pair and say so in CORPUS.md.

## 2. Look at what the indexer produces (no model, no Chroma)
```bash
cd indexer
CORPUS_DIR=../corpus/raw python -m pipeline.run --dry-run --dump chunks.jsonl
```
Read the `extracted` log lines (OCR pages, empty pages) and open `chunks.jsonl`. If a document
has bad sections, fix `chunk.py`/`clean.py` now; this is where the real corpus will surprise you.
Collect the before/after table example for `docs/PIPELINE.md`.

## 3. Golden set BEFORE tuning (60-90 min; do not skip)
Open `eval/golden.yaml`. For every `relevant: []` marked FILL, read the PDF, find the clause, then:
```bash
python eval/validate_golden.py --dump indexer/chunks.jsonl --grep "attendance"   # shows real section names
python eval/validate_golden.py --dump indexer/chunks.jsonl                        # must print "golden set OK"
```
Rewrite any question whose document you did not use. Confirm the two abstain questions are
truly absent from every kept document.

## 4. Chunking experiment (the graded table)
```bash
python eval/chunk_experiment.py --corpus corpus/raw --golden eval/golden.yaml --configs 200:25,400:50,800:100
```
Paste the table into `docs/PIPELINE.md`, ship the best one by setting `CHUNK_SIZE`/`CHUNK_OVERLAP`
(ConfigMap and `indexer/pipeline/config.py` defaults), fill the shipped value into ADR 0002.

## 5. Real index, real answers (local, before the cluster)
Run Chroma locally: `docker run -p 8001:8000 chromadb/chroma:1.0.12`, then
```bash
cd indexer && CORPUS_DIR=../corpus/raw CHROMA_HOST=localhost CHROMA_PORT=8001 \
  OLLAMA_URL=http://localhost:11434 python -m pipeline.run        # prints chunking summary + amplification
cd ../api && RETRIEVER=chroma LLM_PROVIDER=ollama-host CHROMA_HOST=localhost CHROMA_PORT=8001 \
  OLLAMA_URL=http://localhost:11434 SERVE_UI_DIR=../ui uvicorn app.main:app --port 8000
curl localhost:8000/readyz        # should be 200; try a wrong EMBED_MODEL to see the 503
make eval-fixtures                # or: python eval/run_eval.py --api http://localhost:8000
```
(Fixtures: run the indexer with `CORPUS_DIR=../eval/fixtures` first.) Then on your real corpus:
```bash
python eval/run_eval.py --api http://localhost:8000
```
Read `eval/results.json`. Choose `RELEVANCE_FLOOR` between `max_top1_score_must_abstain` and
`min_top1_score_answerable`. All must-abstain questions must be declined (100%).

## 6. Cache threshold
Edit `eval/cache_pairs.yaml` to your corpus (6+ pairs each), then
`python eval/cache_threshold.py`. Paste the table and the false-hit pair into PIPELINE.md.
Set `CACHE_THRESHOLD` to the lowest value with zero false hits.

## 7. Baseline and the cluster
When the numbers are good: `python eval/run_eval.py --api ... --update-baseline`, commit
`eval/results.json` and `eval/baseline.json`. Hand Student B the images' requirements
(`docs/A-TO-B-HANDOFF.md`) and run the Job in the cluster together.

## 8. Failure analysis (4 of 6 stages)
Follow `docs/FAILURE-ANALYSIS.md`: flip one switch, observe, restore, record. Write what you
SAW (log line, metric, eval numbers), not the hypothesis.

## 9. Final docs
FILL-IN everything left in PIPELINE.md, CORPUS.md, ENGINEERING-NOTES.md (Q5, Q6, and your Q7),
ADR 0002 (shipped size/overlap), AI-USAGE.md (your honest section). Read every module so you can explain it.
