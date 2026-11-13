# Documentation claim auditor

An offline audit tool that compares documented promises with listed call patterns in Python source. It parses syntax without importing or executing the inspected project. It uses no network, telemetry, or output files.

## Install and run

Requires Python 3.9 or newer. No runtime dependencies.

```sh
python3 -m pip install .
id-document-extraction-claim-audit --version
id-document-extraction-claim-audit audit /path/to/project --json
python3 -m id_document_extraction_claim_audit audit . --verbose
id-document-extraction-claim-audit audit . --ignore tests --ignore vendor --fail-on medium
python3 -m unittest discover
```

The optional repository argument defaults to the current directory. Repeat each ignore option with one path prefix relative to the repository. The failure threshold accepts lowercase `high` (default) or `medium`. Exit status is 0 below the threshold, 2 for findings at or above it, and 1 for usage or I/O errors. A report can have a FAIL verdict yet exit 0 when all findings are below the threshold.

JSON contains a verdict, findings, production evidence paths, and test evidence paths. Each finding includes an identifier, severity, message, and documentation paths. The positive finding becomes MEDIUM when only tests contain evidence; otherwise it is HIGH. A contradicted denial is HIGH. Without source files, a positive promise fails and a denial passes.

```text
documented-id-document-extraction-claim-false
documented-no-id-document-extraction-claim-false
```

## Scope

Documentation includes the root README.md and Markdown files with a docs directory component. Fenced blocks using backticks or tildes with up to three leading spaces are skipped. Inline code counts. Paragraphs are lowercased; contractions expand; hyphens become spaces; whitespace collapses. Matching uses exact phrases with word boundaries, longest first and alphabetical ties. Listed denial spans are removed before positive matching.

Python files are parsed with the standard syntax tree parser. Symlinked files and directories are skipped. Files in fixtures, docs, and examples directories provide no evidence. Files in tests directories or with conventional test filenames count separately. Invalid syntax provides no evidence. Pair requirements must occur within one module. Imports and simple assignment aliases are resolved; local functions, methods, and classes shadow matching route names. Assignment, annotated assignment, and context manager bindings are tracked.

The checked routes and product arguments are:

```text
mindee: Client + parse(PassportV1 / TypePassportV1 /
 InternationalIdV2 / TypeInternationalIdV2 / DriverLicenseV1 /
 TypeDriverLicenseV1 / IdCardV1 / TypeIdCardV1 / IdCardV2 / TypeIdCardV2)
azure.ai.formrecognizer.DocumentAnalysisClient or
 azure.ai.documentintelligence.DocumentIntelligenceClient +
 begin_analyze_document / begin_analyze_document_from_url("prebuilt-idDocument")
boto3: analyze_id
passporteye: read_mrz
Generic names: see GENERIC_NAMES in phrases.py
```

## Limits

This is static pattern matching, with no semantic judgement. Dead code counts. Untraceable alias chains can be missed. Denial handling depends on a finite list. A detected cloud call establishes neither configured credentials nor successful execution. The local library below requires Tesseract.

```text
Cloud: Mindee, Azure Document Intelligence, Textract
Local: PassportEye
```

Some phrases are intentionally broad. They can describe cropping a photo for display, checking machine readable text, or parsing an already supplied string or file format into a data model. Those uses can produce false positives. The source patterns decide whether evidence exists; the tool cannot judge the intended meaning.

```text
passport extraction / extract passport / mrz extraction
passport parser / passport parsing / id document parser / mrz parsing
```

Generic calls can wrap an external binary or parse a string. They count when they match a listed call; locally defined functions with those names are shadowed. A direct subprocess invocation of an external command does not count. Handwritten regular expressions on OCR text with manual field assembly are missed because a listed call is required. Parsing an already supplied machine readable string alone does not count.

```text
extract_passport / extract_mrz
subprocess: mindee CLI, PassportEye mrz CLI, any other external ID CLI
re.search / re.findall
mrz: TD1Code / TD2Code / TD3Code
```

Constructing the pipeline below alone is not detected; only the listed reader counts. Nonmatching products and models are excluded, as are generic document and expense operations. Retrieving results alone does not start an analysis.

```text
PassportEye MRZPipeline: excluded; read_mrz: counted
Mindee parse: InvoiceV4 / ReceiptV5 / BankCheckV1 /
 FinancialDocumentV1 / CustomV1: excluded
Azure begin_analyze_document: prebuilt-invoice / prebuilt-receipt /
 prebuilt-layout / prebuilt-read: excluded
Textract analyze_document / detect_document_text / analyze_expense /
 start_document_analysis / get_expense_analysis: excluded
```

Plain text reading, OCR, spreadsheet loading, and table operations alone do not count. Imports alone, comments, strings, bare references, and evidence split between modules do not count. The adjacent claim families and person verification promises below are outside the phrase lists: verifying a person differs from retrieving document fields.

```text
invoice extraction / extract invoices
receipt extraction / extract receipts
verify identity / face match / liveness detection
```

MIT licensed.
