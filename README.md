# Support Notes Email Builder

This Streamlit application turns monthly Support Notes request emails (`.eml` files) into ready-to-ship Template-Based Email assets in Salesforce Marketing Cloud. It covers the Korean edition of each product newsletter, with English, Japanese, Simplified Chinese, and Traditional Chinese produced using the same pipeline.

It is a sister project to the [Expert Series Webinar Invite Builder](https://github.com/rosdevries/expert-series-webinar-invite-builder), sharing the same SFMC client, slot-rendering approach, and Streamlit UI patterns.

## Core Functionality

The tool accepts a `.eml` request file forwarded from the monthly Support Notes coordinator and automates the end-to-end production workflow: parsing the email, extracting structured editorial content with AI, letting the editor review and correct every field, compositing speaker headshots, and finally creating a fully-rendered email asset in SFMC Content Builder — ready to test-send and schedule.

**Email parsing and AI extraction:** The `.eml` file is parsed to isolate the editor-facing preview HTML and any supplementary notes embedded in the email body. Both blocks are passed to Claude Haiku, which maps the content into a structured schema covering the header title and strapline, subscribe link, two editorial sections (each with a quote, speaker name and title, editorial paragraph, and left- and right-column article links), the upcoming-webinar schedule, the latest-release download links, the webinar series link, an archive footnote, and the CAN-SPAM-compliant footer. Metadata fields — product name, language, year, and month — are always derived from the email subject line and are never left to the model. If the Anthropic API key is not configured, or if the AI call fails, the parser falls back to a heuristic extraction that fills the unambiguous fields and leaves the rest blank for manual editing.

**Streamlit editing UI:** After parsing, every extracted field is presented as an editable widget — rich Quill editors for HTML fields, plain text inputs for labels and URLs, and a drag-to-reorder interface for article links. The footer field renders a live dark-background preview so editors can check link contrast before publishing. A reset button on each field restores the language-appropriate default. The UI supports five languages: Korean (`ko`), English (`en`), Japanese (`ja`), Simplified Chinese (`zh-CN`), and Traditional Chinese (`zh-TW`). Progress is auto-saved to a local draft store keyed by product, language, year, and month, so reopening the same email picks up where the editor left off.

**Speaker headshot compositor:** If a speaker headshot is attached to the `.eml`, the app crops and resizes the image onto the Siemens petrol teal background (`#00C1B6`) and uploads it to the configured SFMC images folder. Previously uploaded headshots for a known speaker name are looked up automatically so the upload step is skipped when the photo is unchanged. Editors can also upload a headshot manually via the UI.

**SFMC asset creation:** Clicking the Create button renders the full email HTML — by filling every slot div in the per-language template — and sends it to the SFMC Email API as a Template-Based Email asset in the configured Content Builder folder. The rendered HTML is also offered as a download for offline inspection. A dry-run mode renders without calling SFMC, which is useful for reviewing the output before publishing.

## Access & Authentication

The tool is intended for local use. When deployed to Streamlit Cloud it is protected by a password gate configured via the `APP_PASSWORD` secret. SFMC access requires a Server-to-Server OAuth application in the same tenant as the Expert Series tools, with Content Builder write permissions. An Anthropic API key is optional but strongly recommended — without it every field must be filled manually.

## Workflow

Editors upload the `.eml` forwarded by the Support Notes coordinator. The app parses the file, calls Claude Haiku to fill the slot schema, and presents the populated form. The editor reviews and corrects any fields the AI got wrong, uploads or confirms speaker headshots, and adjusts article links or webinar dates as needed. When satisfied, they click **Create email in SFMC** to publish the asset to Content Builder. The resulting asset ID and a link to SFMC are shown on screen.

Webinar registration URLs arriving in `.eml` files are typically wrapped in SFMC click-tracking and cannot be automatically recovered. The webinar titles and dates are extracted correctly; editors should paste the actual registration URLs into the contact-body field using the HTML editor before publishing.

## Technical Requirements

**Dependencies:** Python 3.11+, SFMC Server-to-Server credentials, and optionally an Anthropic API key. All Python dependencies are in `requirements.txt`. On corporate networks with TLS-inspection proxies, the `truststore` package injects the OS certificate store into Python's SSL context automatically; install it via `pip install truststore` if you encounter SSL errors.

**Local setup:** Clone the repository, create and activate a virtual environment, install dependencies with `pip install -r requirements.txt`, copy `.env.example` to `.env` and fill in your credentials, then run `streamlit run app.py`. On Windows you can also use `run.bat` if present.

**One-time template bootstrap:** Run `python -m builder.bootstrap_template <lang>` once per language before using the app. This script reads `templates/support-notes-template.html`, sets the `<html lang="...">` attribute for the target language, and either uploads a new Template-Based Email asset to SFMC or patches an existing one by the conventional name. It prints the resulting asset ID — add it to `.env` as `MC_TEMPLATE_ID_KO`, `MC_TEMPLATE_ID_EN`, and so on.

**Cloud deployment:** Add all variables from `.env.example` as secrets in the Streamlit Cloud dashboard under App settings, in TOML format. See `.streamlit/secrets.toml.example` for the expected shape. The `drafts/` folder is written to the ephemeral filesystem at runtime; saved drafts are lost when the pod restarts, so the tool is best run locally.

**Running tests:** `python -m pytest tests/ -v`. The test suite covers the `.eml` parser, slot renderer, and bootstrap-template logic offline without SFMC or Anthropic access.

## Key Constraints & Notes

- The email subject line is the authoritative source for product name, language, year, and month. These fields always override whatever the AI model returns.
- Outlook SafeLinks wrappers in `.eml` files are automatically unwrapped to their original URLs before the HTML is sent to the AI. SFMC click-tracking URLs — which redirect opaquely to the destination — are replaced with a `#sfmc-tracking` sentinel so the model does not hallucinate destinations. An exception is made for download links tagged `title="Latest Release"`, which carry the real URL in an `originalsrc` attribute and are recovered before the sentinel stripping pass.
- The Quill rich-text editor does not support `<table>` elements — it silently discards table tags and their content. All HTML passed to Quill is pre-processed to strip table structural tags while preserving inner content; editors who need table-based layouts should switch each field to HTML mode.
- Draft files in `drafts/` are excluded from version control via `.gitignore`. They contain user-editable corrections and production-ready field values that should not be overwritten by code changes.
- The headshot compositor samples the background colour from the shipped email images. Three independent samples of the April 2026 Functional Verification headshot gave `RGB(0, 193, 182)` = `#00C1B6`; neighbouring pixels vary by one or two counts due to JPEG compression artefacts.

## Repository Structure

The repository contains the Streamlit front-end (`app.py`) and a `builder/` package with the following modules: `eml_parser.py` extracts the preview HTML and editor notes from a `.eml` file; `ai_extractor.py` calls Claude Haiku with a structured prompt and maps the response to the internal data model; `slot_renderer.py` renders each data-model field into the HTML fragment expected by the SFMC template; `static_slots.py` holds the language-specific static HTML for the footer, contact-body, and archive-footnote slots; `email_builder.py` orchestrates parse, extract, render, and SFMC create; `sfmc_client.py` wraps the SFMC OAuth and Content/Asset REST APIs; `headshot_compositor.py` handles image cropping and upload; `language_config.py` is the registry of per-language settings; `bootstrap_template.py` is the one-time template-upload CLI; `draft_store.py` reads and writes the local draft JSON files; and `models.py` defines the `SupportNotesData` dataclass. The `builder/prompts/` directory holds the Claude extraction prompt. The `templates/` directory holds the master SFMC HTML template. The `tests/` directory covers the parser, renderer, and bootstrap logic.
