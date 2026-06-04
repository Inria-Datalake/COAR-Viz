from pyArango.theExceptions import AQLQueryError


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


def dashboard(db, structure):
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
