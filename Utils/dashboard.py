import threading
import time

from pyArango.theExceptions import AQLQueryError

from Utils.db import get_cache_version


# Aggregation tail shared by the global and structure-scoped variants: given a software
# mention edge `e`, keep mentions that carry a usable characterization, pick the dominant
# attribute (highest score; ties resolve used > created > shared), then group by
# (attribute, software) returning the distinct documents and the mention count.
_AGG_TAIL = """
    LET soft = DOCUMENT(e._to)
    LET a = soft.mentionContextAttributes
    FILTER a != null
    LET maxs = MAX([a.used.score, a.created.score, a.shared.score])
    FILTER maxs != null
    LET dom = a.used.score == maxs ? "used"
            : (a.created.score == maxs ? "created" : "shared")
    LET sw_name = soft.software_name.normalizedForm
    FILTER sw_name != null AND TRIM(sw_name) != ""
    LET hal = DOCUMENT(e._from).file_hal_id
    COLLECT attr = dom, name = sw_name INTO hals = hal
    RETURN { attr: attr, name: name, mentions: LENGTH(hals), hal_ids: UNIQUE(hals) }
"""

# Documents affiliated with a given structure (its HAL/HAuREAL id).
_DOCSET = """
    LET docset = (
        FOR struct IN structures
            FILTER struct.id_haureal == @structure
            FOR es IN edge_doc_to_struc
                FILTER es._to == struct._id
                RETURN DISTINCT es._from
    )
"""


# ---------------------------------------------------------------------------
# Result cache. The dashboard aggregation is a full scan of edge_doc_to_software
# (~1s+ at 190k softwares) whose result is identical for every visitor and only
# changes when new data is ingested — which here happens about once a day. So we
# cache the computed payload per worker and validate it against a *shared*
# ArangoDB version counter (get_cache_version): a successful ingest bumps the
# counter, every worker sees the change on its next request and recomputes once,
# then serves from memory the rest of the day. This is gunicorn-safe — the
# invalidation signal lives in the DB, not in one worker's memory, so a
# per-process flag's "only the ingesting worker gets cleared" bug can't happen.
#
# The backstop age is a defensive refresh in case some mutation that *should*
# bump the counter (accept/reject, blacklist, disambiguation) doesn't yet — it
# bounds staleness to an hour even then. Computing outside the lock keeps a ~1s
# aggregation from serializing other requests; a cold-cache race may compute
# twice, which is harmless. Only the successful 7-element list is cached.
# ---------------------------------------------------------------------------
_CACHE_BACKSTOP_SECONDS = 3600
_cache = {}  # key -> (version, computed_at, payload)
_cache_lock = threading.Lock()


def dashboard(db, structure):
    """Return the dashboard payload, served from cache while the data version is
    unchanged (see ``get_cache_version``) and within the backstop age."""
    key = structure or "__global__"
    version = get_cache_version(db)
    now = time.time()

    with _cache_lock:
        entry = _cache.get(key)
        if entry is not None:
            cached_version, computed_at, payload = entry
            if cached_version == version and now - computed_at < _CACHE_BACKSTOP_SECONDS:
                return payload

    result = _compute_dashboard(db, structure)

    if isinstance(result, list):
        with _cache_lock:
            _cache[key] = (version, now, result)

    return result


def _compute_dashboard(db, structure):
    """Aggregate software-mention characterizations for the dashboard.

    Everything is computed server-side in two AQL queries (one grouping, one totals)
    instead of fetching every document/edge/software individually. Returns the 7-element
    list consumed by ``app/templates/pages/dashboard.html``:

        [0] attributes_count : {"used": int, "created": int, "shared": int}
        [1] doc_with_mention : int
        [2] nb_mention       : int   (every software edge, incl. uncharacterized ones)
        [3] doc_wno_mention  : int
        [4] used_software    : {software_name: [[hal_id, ...], mention_count]}
        [5] shared_software  : same shape
        [6] created_software : same shape
    """
    try:
        if structure:
            agg_query = _DOCSET + """
                FOR docid IN docset
                    FOR e IN edge_doc_to_software
                        FILTER e._from == docid
            """ + _AGG_TAIL
            totals_query = _DOCSET + """
                LET inscope = (
                    FOR docid IN docset
                        FOR e IN edge_doc_to_software
                            FILTER e._from == docid
                            RETURN docid
                )
                RETURN {
                    total_docs: LENGTH(docset),
                    total_mentions: LENGTH(inscope),
                    docs_with: LENGTH(UNIQUE(inscope))
                }
            """
            bind_vars = {'structure': structure}
        else:
            agg_query = "FOR e IN edge_doc_to_software" + _AGG_TAIL
            totals_query = """
                RETURN {
                    total_docs: LENGTH(documents),
                    total_mentions: LENGTH(edge_doc_to_software),
                    docs_with: LENGTH(
                        FOR e IN edge_doc_to_software
                            COLLECT d = e._from
                            RETURN 1
                    )
                }
            """
            bind_vars = {}

        rows = db.AQLQuery(agg_query, bindVars=bind_vars, rawResults=True, batchSize=5000)
        totals = db.AQLQuery(totals_query, bindVars=bind_vars, rawResults=True, batchSize=1)

    except AQLQueryError:
        return 'AQL query error: Unable to fetch files'

    attributes_count = {'used': 0, 'created': 0, 'shared': 0}
    used_software = {}
    created_software = {}
    shared_software = {}
    buckets = {'used': used_software, 'created': created_software, 'shared': shared_software}

    for row in rows:
        bucket = buckets.get(row['attr'])
        if bucket is None:
            continue
        attributes_count[row['attr']] += row['mentions']
        bucket[row['name']] = [row['hal_ids'], row['mentions']]

    totals = totals[0] if totals else {'total_docs': 0, 'total_mentions': 0, 'docs_with': 0}
    nb_mention = totals['total_mentions']
    doc_with_mention = totals['docs_with']
    doc_wno_mention = totals['total_docs'] - totals['docs_with']

    return [
        attributes_count,
        doc_with_mention,
        nb_mention,
        doc_wno_mention,
        used_software,
        shared_software,
        created_software,
    ]
