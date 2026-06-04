from app.app import app, db
import os
from flask import render_template, request, jsonify
from elasticsearch import Elasticsearch, NotFoundError
from Utils.elastic_search import sync_to_elasticsearch


def _es_client():
    """Build an Elasticsearch client from the ELASTIC_HOST/ELASTIC_PORT env vars."""
    elastic_host = os.getenv('ELASTIC_HOST')
    elastic_port = os.getenv('ELASTIC_PORT')
    return Elasticsearch(hosts=[f"http://{elastic_host}:{elastic_port}"], request_timeout=60)


def _es_search(es, index, body, size):
    """Run an ES search and return the raw list of hits.

    A missing index — the normal state on a fresh deploy, or after Elasticsearch was
    reset, before the first ``/elastic_update`` — yields ``[]`` instead of bubbling up
    as a 500. For an autocomplete box that just means "no matches yet". The condition
    is logged so an operator knows to (re)build the indices via ``/elastic_update``.
    """
    try:
        response = es.search(index=index, body=body, size=size)
        return response["hits"]["hits"]
    except NotFoundError:
        app.logger.warning(
            "Elasticsearch index '%s' not found — returning empty results. "
            "Run /elastic_update to (re)build the indices from ArangoDB.", index)
        return []


# Trigger Elasticsearch sync manually
@app.route('/elastic_update')
def elastic_update():
    sync_to_elasticsearch(db)
    return "Elastic executed manually!"

@app.route('/search')
def search_html():
    return render_template('pages/search.html')

@app.route('/api/search_software')
def search():
    es = _es_client()
    query_str = request.args.get("q")
    if not query_str:
        return jsonify({"error": "Missing 'q' query parameter"}), 400

    query_str = query_str.lower()  # lowercase the input for case-insensitive prefix

    query = {
        "query": {
            "prefix": {
                "name.lowercase": query_str
            }
        }
    }

    hits = _es_search(es, "softwares", query, size=100)
    results = [hit["_source"] for hit in hits]

    return jsonify(results)


@app.route('/api/search_document')
def search_document():
    es = _es_client()
    query_str = request.args.get("q")
    if not query_str:
        return jsonify({"error": "Missing 'q' query parameter"}), 400

    query = {
        "query": {
            "match": {
                "title": query_str
            }
        }
    }

    hits = _es_search(es, "titles", query, size=100)
    results = [hit["_source"] for hit in hits]

    return jsonify(results)

@app.route('/api/search_author')
def search_author():
    es = _es_client()
    query_str = request.args.get("q")
    if not query_str:
        return jsonify({"error": "Missing 'q' query parameter"}), 400

    query_str = query_str.lower()

    query = {
        "query": {
            "bool": {
                "should": [
                    {"prefix": {"first_name": query_str}},
                    {"prefix": {"last_name": query_str}}
                ]
            }
        }
    }

    hits = _es_search(es, "authors", query, size=100)
    results = [
        {
            "first_name": hit["_source"]["first_name"],
            "last_name": hit["_source"]["last_name"],
            "author_id": hit["_source"].get("author_id")
        }
        for hit in hits
    ]
    return jsonify(results)

@app.route('/api/search_structure')
def search_structures():
    es = _es_client()
    query_str = request.args.get("q", "").lower().strip()
    if not query_str:
        return jsonify({"error": "Missing 'q' query parameter"}), 400

    query = {
        "query": {
            "bool": {
                "should": [
                    {
                        "prefix": {
                            "struct_acronym": {
                                "value": query_str,
                                "boost": 2.0  # Boost acronym matches
                            }
                        }
                    },
                    {
                        "match": {
                            "structure": {
                                "query": query_str,
                                "operator": "and"
                            }
                        }
                    }
                ],
                "minimum_should_match": 1
            }
        }
    }

    hits = _es_search(es, "structures", query, size=100)

    # Deduplicate by structure_id
    seen_ids = set()
    results = []
    for hit in hits:
        source = hit["_source"]
        structure_id = source.get("structure_id")
        if structure_id and structure_id not in seen_ids:
            seen_ids.add(structure_id)
            results.append({
                "structure": source["structure"],
                "struct_acronym": source.get("struct_acronym", ""),
                "structure_id": structure_id
            })

    return jsonify(results)

@app.route('/api/search_url')
def search_url():
    es = _es_client()
    query_str = request.args.get("q", "").lower().strip()
    if not query_str:
        return jsonify([])

    query = {
        "query": {
            "multi_match": {
                "query": query_str,
                "fields": [
                    "url^3",          # autocomplete field (boosted)
                    "url_exact^5"     # exact match strongly boosted
                ],
                "type": "best_fields",
                "fuzziness": "AUTO"
            }
        }
    }

    hits = _es_search(es, "urls", query, size=50)

    results = [
        {
            "doc_id": hit["_source"]["doc_id"],
            "url": hit["_source"].get("url_exact", hit["_source"].get("url"))
        }
        for hit in hits
    ]

    return jsonify(results)
