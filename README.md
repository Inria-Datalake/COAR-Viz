<p align="center">
    <h1 align="center">COAR-Viz</h1>
</p>
<div align="center">
  <img src="https://github.com/user-attachments/assets/43b01db2-450e-4d9d-a805-cb37f861bdb2" alt="logo_full_HUB" width="250" />
</div>

<p align="center">
		<em>A fork of <a href="https://github.com/Samuel-Scalbert/SOFTware-Viz">SOFTware-Viz</a>. Developed with the software and tools below.</em>
</p>
<p align="center">
	<img src="https://img.shields.io/badge/HTML5-E34F26.svg?style=default&logo=HTML5&logoColor=white" alt="HTML5">
	<img src="https://img.shields.io/badge/Python-3776AB.svg?style=default&logo=Python&logoColor=white" alt="Python">
	<img src="https://img.shields.io/badge/Flask-000000.svg?style=default&logo=Flask&logoColor=white" alt="Flask">
	<img src="https://img.shields.io/badge/ArangoDB-DDE072.svg?style=default&logo=ArangoDB&logoColor=black" alt="ArangoDB">
	<img src="https://img.shields.io/badge/Elasticsearch-005571.svg?style=default&logo=Elasticsearch&logoColor=white" alt="Elasticsearch">
</p>

![Capture d’écran du 2024-06-03 16-39-41](https://github.com/Samuel-Scalbert/SOFTware-Viz/assets/32683708/6be2a593-0508-4e52-a7cb-2cf28b768f00)

## Presentation of the project

COAR-Viz is a Flask web application that **visualizes software mentions** extracted from scholarly
papers. It is the visualization + storage stage of a larger pipeline. Data lives in **ArangoDB**
(a multi-model graph database) and is mirrored into **Elasticsearch** for search and autocomplete.

> 🛑 This application is currently coupled to **HAL** (`api.archives-ouvertes.fr`) for fetching TEI
> XML and citations.
>
> 🛑 A lighter version that runs without a HAL connection is under development.

### The pipeline

```
Scholarly PDFs → GROBID → SOFTCITE → SOFTware-Sync → COAR-Viz (this app)
                (TEI XML)   (JSON)    (merged doc)    ArangoDB + Elasticsearch + Flask
```

| Stage | Role |
|-------|------|
| **DB of PDF** | The corpus of scholarly PDFs to be extracted and processed. |
| **GROBID** | Extracts structured **TEI XML** (bibliographic metadata, body text) from each PDF. |
| **SOFTCITE** | Detects **software mentions** and references, emitting a `.software.json` per document. |
| **SOFTware-Sync** | Merges the TEI XML and SOFTCITE JSON into a single document. |
| **COAR-Viz** | Ingests the merged data into ArangoDB, mirrors it to Elasticsearch, and serves the dashboards, document views, and search. |

---
## Installation

This app needs **two services reachable**: an **ArangoDB** server and an **Elasticsearch** server.
ArangoDB stores the graph; Elasticsearch backs search/autocomplete and **ingestion is refused if it
is unreachable**.

<h4>From <code>source</code></h4>

> 1. Clone the repository and enter it:
> ```console
> git clone <repository-url>
> cd COAR-Viz
> ```
>
> 2. Create and activate a virtualenv:
> ```console
> python -m venv env
> source env/bin/activate
> ```
>
> 3. Install the dependencies:
> ```console
> pip install -r requirements.txt
> ```
>
> 4. Start an ArangoDB container (the app creates the `SOF-viz-COAR` database on first launch,
>    but not the server itself):
> ```console
> docker run -p 8529:8529 -e ARANGO_NO_AUTH=1 arangodb/arangodb:3.11.6
> ```
>
> 5. Start an Elasticsearch instance and make sure it is reachable.
>
> 6. Configure the environment (see [Configuration](#configuration)), then launch the app:
> ```console
> cp .env.example .env   # then edit .env for your setup
> python run.py
> ```

### Configuration

The app reads all configuration from environment variables, loaded from a `.env` file via
[`python-dotenv`](https://pypi.org/project/python-dotenv/) (see `.env.example`). Copy the template
and adjust it for your setup:

```console
cp .env.example .env
```

Real environment variables (e.g. those injected by Docker) take precedence over `.env`, so the same
image works in containers without a `.env` file.

| Variable | Purpose | Default |
|----------|---------|---------|
| `ARANGO_HOST`, `ARANGO_PORT` | ArangoDB connection | none — must be set |
| `ARANGO_LOGIN` | ArangoDB user | `root` |
| `ARANGO_PASSWORD` | ArangoDB password | `changeme` |
| `ELASTIC_HOST`, `ELASTIC_PORT` | Elasticsearch connection | none — must be set |

The database name (`SOF-viz-COAR`) is fixed in code and created automatically on first launch.

###  Usage

> Run with the command below — the `SOF-viz-COAR` database is created automatically on the first
> launch:
> ```console
> python run.py
> ```
>
> The app serves on **`http://0.0.0.0:8040`**. It assumes it runs behind a reverse proxy mounted at
> **`/software`** (every generated URL is prefixed with `/software`; see `run.py`).
