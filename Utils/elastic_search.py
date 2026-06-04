import os
from elasticsearch import Elasticsearch, helpers


def _rebuild_index(es, name, index_body, fetch_documents):
    """(Re)build a single Elasticsearch index in isolation.

    Drops the index if present, recreates it with ``index_body``, then bulk-indexes
    whatever ``fetch_documents()`` yields. Any failure is caught and returned as a
    report entry instead of propagating, so one broken index (a bad record, an AQL
    error) can no longer abort the rebuild of the *other* indices — previously a
    failure before the ``authors`` step left that index uncreated entirely.

    Indexing uses the streaming ``bulk`` helper (batched round-trips) instead of one
    HTTP request per document, which is orders of magnitude faster on a real corpus —
    the per-document loop made /elastic_update appear to hang. Progress is printed so
    the rebuild is observable in the container logs.

    ``fetch_documents`` is a zero-arg callable (deferred so its AQL query also runs
    inside the try/except). Returns a dict suitable for the /elastic_update report.
    """
    try:
        print(f"[elastic_update] rebuilding index '{name}' ...", flush=True)
        if es.indices.exists(index=name):
            es.indices.delete(index=name)
        es.indices.create(index=name, body=index_body)

        documents = fetch_documents()
        print(f"[elastic_update] '{name}': {len(documents)} docs fetched from ArangoDB, bulk indexing ...",
              flush=True)

        indexed = 0
        errors = []
        if documents:
            actions = ({"_index": name, "_source": doc} for doc in documents)
            # raise_on_error=False -> a few bad docs are reported, not fatal.
            indexed, errors = helpers.bulk(es, actions, raise_on_error=False, chunk_size=1000)

        print(f"[elastic_update] '{name}': indexed {indexed}, errors {len(errors)}", flush=True)
        result = {"index": name, "indexed": indexed}
        if errors:
            result["doc_errors"] = len(errors)
        return result
    except Exception as e:
        print(f"[elastic_update] '{name}' FAILED: {type(e).__name__}: {e}", flush=True)
        return {"index": name, "error": f"{type(e).__name__}: {e}"}


def sync_to_elasticsearch(db):
    """Drop and rebuild every search index from current ArangoDB contents.

    Returns a list of per-index report dicts (``{"index", "indexed"}`` on success,
    ``{"index", "error"}`` on failure) so callers — e.g. the /elastic_update route —
    can surface exactly what was built and what failed.
    """

    elastic_host = os.getenv('ELASTIC_HOST')
    elastic_port = os.getenv('ELASTIC_PORT')

    es = Elasticsearch(hosts=[f"http://{elastic_host}:{elastic_port}"], request_timeout=60)

    report = []

    # SOFTWARE ---------------------------------
    software_body = {
        "settings": {
            "analysis": {
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "name": {
                    "type": "text",
                    "fields": {
                        "lowercase": {
                            "type": "keyword",
                            "normalizer": "lowercase_normalizer"
                        }
                    }
                }
            }
        }
    }

    def fetch_software():
        cursor = db.AQLQuery(
            'FOR software IN softwares RETURN DISTINCT {name : software.software_name.normalizedForm}',
            rawResults=True)
        return [doc for doc in cursor]

    report.append(_rebuild_index(es, "softwares", software_body, fetch_software))

    # DOCUMENT -----------------------------
    titles_body = {
        "settings": {
            "index": {
                "max_ngram_diff": 20  # must be >= max_gram - min_gram
            },
            "analysis": {
                "analyzer": {
                    "ngram_analyzer": {
                        "tokenizer": "ngram_tokenizer",
                        "filter": ["lowercase"]
                    },
                    "standard_lower": {
                        "tokenizer": "standard",
                        "filter": ["lowercase"]
                    }
                },
                "tokenizer": {
                    "ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 1,
                        "max_gram": 20,
                        "token_chars": ["letter", "digit"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "title": {
                    "type": "text",
                    "analyzer": "ngram_analyzer",
                    "search_analyzer": "standard_lower"
                },
                "doc_id": {"type": "keyword"}
            }
        }
    }

    def fetch_titles():
        cursor = db.AQLQuery(
            'FOR doc IN documents RETURN DISTINCT { title: doc.title, hal_id: doc.file_hal_id}',
            rawResults=True)
        return [{"title": doc['title'], "doc_id": doc['hal_id']} for doc in cursor]

    report.append(_rebuild_index(es, "titles", titles_body, fetch_titles))

    # AUTHOR ---------------------------------
    authors_body = {
        "settings": {
            "analysis": {
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "first_name": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "last_name": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "author_id": {
                    "type": "keyword"
                }
            }
        }
    }

    def fetch_authors():
        cursor = db.AQLQuery('''
               FOR author IN authors
               RETURN DISTINCT {
                   first_name: author.name.forename,
                   last_name: author.name.surname,
                   author_id: author.id.halauthorid
               }
           ''', rawResults=True)
        return [
            {
                'first_name': author['first_name'],
                'last_name': author['last_name'],
                'author_id': author['author_id']
            }
            for author in cursor
        ]

    report.append(_rebuild_index(es, "authors", authors_body, fetch_authors))

    # STRUCTURE ---------------------------------------------
    structures_body = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "ngram_analyzer": {
                        "tokenizer": "ngram_tokenizer",
                        "filter": ["lowercase"]
                    },
                    "lowercase_keyword_analyzer": {
                        "tokenizer": "keyword",
                        "filter": ["lowercase"]
                    }
                },
                "tokenizer": {
                    "ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 3,
                        "token_chars": [
                            "letter",
                            "digit"
                        ]
                    }
                },
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "structure": {
                    "type": "text",
                    "analyzer": "ngram_analyzer",
                    "search_analyzer": "ngram_analyzer"
                },
                "struct_acronym": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                },
                "structure_id": {
                    "type": "keyword"
                }
            }
        }
    }

    def fetch_structures():
        cursor = db.AQLQuery('''
               FOR struc IN structures
               RETURN DISTINCT {
                   struct_title: struc.name,
                   struct_acronym: struc.acronym,
                   struct_id: struc.id_haureal
               }
           ''', rawResults=True)
        return [
            {
                "structure": struc['struct_title'],
                "struct_acronym": struc['struct_acronym'],
                "structure_id": struc['struct_id']
            }
            for struc in cursor
        ]

    report.append(_rebuild_index(es, "structures", structures_body, fetch_structures))

    # URLS ---------------------------------------------
    urls_body = {
        "settings": {
            "analysis": {
                "analyzer": {
                    "url_autocomplete_analyzer": {
                        "tokenizer": "url_autocomplete_tokenizer",
                        "filter": ["lowercase"]
                    }
                },
                "tokenizer": {
                    "url_autocomplete_tokenizer": {
                        "type": "edge_ngram",
                        "min_gram": 2,
                        "max_gram": 30,
                        "token_chars": ["letter", "digit", "punctuation", "symbol"]
                    }
                },
                "normalizer": {
                    "lowercase_normalizer": {
                        "type": "custom",
                        "filter": ["lowercase"]
                    }
                }
            }
        },
        "mappings": {
            "properties": {
                "doc_id": {"type": "keyword"},
                "url": {
                    "type": "text",
                    "analyzer": "url_autocomplete_analyzer",
                    "search_analyzer": "standard"
                },
                "url_exact": {
                    "type": "keyword",
                    "normalizer": "lowercase_normalizer"
                }
            }
        }
    }

    def fetch_urls():
        cursor = db.AQLQuery('''
            FOR url_soft IN softwares
                FILTER url_soft.url != null
                FOR edge in edge_doc_to_software
                    FILTER edge._to == url_soft._id
                    LET doc = DOCUMENT(edge._from)
                    RETURN DISTINCT {
                        doc_id: doc.file_hal_id,
                        url: url_soft.url.normalizedForm
                    }
        ''', rawResults=True)
        return [
            {"doc_id": url_doc["doc_id"], "url": url_doc["url"]}
            for url_doc in cursor
        ]

    report.append(_rebuild_index(es, "urls", urls_body, fetch_urls))

    return report
