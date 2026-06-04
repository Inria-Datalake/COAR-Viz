import os
import json
from pyArango.theExceptions import AQLQueryError
from utils.TEI_to_JSON import transformer_TEI_JSON
import requests
from datetime import date
import xml.etree.ElementTree as ET
import re
from pyArango.theExceptions import CreationError


def parse_xml_safely(file_path, snippet_len=50, log_file="xml_errors.log", max_fixes=20):
    """
    Parses an XML file while repairing stray < or > characters in text content.
    Logs fixes and retries parsing until success or max_fixes reached.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Remove illegal XML control characters
    content = re.sub(r'[\x00-\x08\x0B\x0C\x0E-\x1F]', '', content)

    # Remove illegal declarations like <!PCT!>
    content = re.sub(r'<![^>]+>', '', content)

    fixes = 0

    while fixes < max_fixes:
        try:
            tree = ET.ElementTree(ET.fromstring(content))
            # SUCCESS → log and return
            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"File cleaned and sent to processing: {file_path}\n")
            return tree

        except ET.ParseError as e:
            # If position info is missing → cannot fix
            if not hasattr(e, 'position'):
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"Unrecoverable XML parsing error: {e}\n")
                break

            line, col = e.position
            lines = content.splitlines(keepends=True)
            abs_pos = sum(len(lines[i]) for i in range(line - 1)) + (col - 1)

            bad_char = content[abs_pos]

            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"\nXML parsing error in file: {file_path}\n")
                log.write(f"Error message: {e}\n")
                log.write(f"Error at line {line}, column {col}\n")

                snippet = content[max(0, abs_pos - snippet_len):abs_pos + snippet_len]
                pointer = " " * (abs_pos - max(0, abs_pos - snippet_len)) + "^ <-- invalid character here"

                log.write(snippet + "\n")
                log.write(pointer + "\n")

            # Only try to fix < or >
            if bad_char not in ['<', '>']:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write(f"Character '{bad_char}' cannot be auto-fixed.\n")
                break

            # Check if the < or > is inside a tag → cannot fix
            before = content[:abs_pos]
            inside_tag = before.rfind("<") > before.rfind(">")

            if inside_tag:
                with open(log_file, 'a', encoding='utf-8') as log:
                    log.write("Character appears inside a tag → cannot auto-fix.\n")
                break

            # Escape the character
            replacement = "&lt;" if bad_char == '<' else "&gt;"
            content = content[:abs_pos] + replacement + content[abs_pos + 1:]
            fixes += 1

            with open(log_file, 'a', encoding='utf-8') as log:
                log.write(f"Auto-fixed {bad_char} → {replacement} and retrying parse.\n")

    # Failed after all fixes
    with open(log_file, 'a', encoding='utf-8') as log:
        log.write(f"Max auto-fixes reached or unrecoverable error for file: {file_path}\n")

    return None

def is_elasticsearch_alive(timeout=10):
    host = os.environ.get("ELASTIC_HOST")
    port = os.environ.get("ELASTIC_PORT")
    # Check missing environment variables
    if not host or not port:
        return [False, f"Missing environment variables: ELASTIC_HOST={host}, ELASTIC_PORT={port}"]
    url = f"http://{host}:{port}/_cluster/health"
    try:
        response = requests.get(url, timeout=timeout)

        # HTTP not OK
        if response.status_code != 200:
            return [
                False,
                f"Elasticsearch responded with HTTP {response.status_code} instead of 200"
            ]
        data = response.json()
        status = data.get("status")
        if status in ["green", "yellow"]:
            return [True, f"Elasticsearch is alive (status: {status})"]
        else:
            return [False, f"Elasticsearch returned unhealthy status: {status}"]
    except requests.ConnectionError:
        return [False, f"Connection error: cannot reach Elasticsearch at {url}"]
    except requests.Timeout:
        return [False, f"Timeout after {timeout}s contacting Elasticsearch at {url}"]
    except Exception as e:
        return [False, f"Unexpected error: {e}"]

def check_or_create_collection(db, collection_name, collection_type='Collection'):
    """
    Checks if a collection exists in the database.
    Creates it if missing (safe under concurrency).
    """
    try:
        if not db.hasCollection(collection_name):
            db.createCollection(
                name=collection_name,
                className=collection_type
            )
    except CreationError as e:
        # Another request created it at the same time
        if "exists" in str(e).lower() or "duplicate" in str(e).lower():
            pass
        else:
            raise

    return db[collection_name]


# ---------------------------------------------------------------------------
# Cache-invalidation counter. A single shared document whose integer `version`
# is bumped on every data mutation (e.g. ingest). It's read cheaply (a
# primary-key lookup) on each request to decide whether a per-process cached
# result — such as the dashboard aggregation — is still valid. Because it lives
# in ArangoDB, the signal is shared across all gunicorn workers, unlike a
# per-process in-memory flag would be.
# ---------------------------------------------------------------------------
CACHE_VERSION_COLLECTION = 'cache_version'


def bump_cache_version(db, name='dashboard'):
    """Increment the shared cache-invalidation counter for `name`.

    Call after any mutation that changes what cached aggregations return (e.g. a
    successful ingest). Every worker sees the new value on its next read and
    recomputes once. Best-effort: a failure here only costs a stale cache until
    the consumer's backstop age elapses, so we log rather than raise.
    """
    check_or_create_collection(db, CACHE_VERSION_COLLECTION)
    try:
        db.AQLQuery(
            f"""
            UPSERT {{ _key: @k }}
            INSERT {{ _key: @k, version: 1 }}
            UPDATE {{ version: OLD.version + 1 }}
            IN {CACHE_VERSION_COLLECTION}
            """,
            bindVars={'k': name}, rawResults=True
        )
    except Exception as e:
        print(f"⚠️ Could not bump cache version '{name}': {e}")


def get_cache_version(db, name='dashboard'):
    """Return the current cache-invalidation counter for `name` (0 if unset).

    A cheap single primary-key lookup. Any failure (collection not yet created,
    transient error) returns 0, so callers treat the cache as valid at
    version 0 rather than crashing; the first bump moves it off 0 and
    invalidates every worker's cache.
    """
    try:
        res = db.AQLQuery(
            f"RETURN DOCUMENT('{CACHE_VERSION_COLLECTION}', @k).version",
            bindVars={'k': name}, rawResults=True
        )
        return res[0] if res and res[0] is not None else 0
    except Exception:
        return 0


# Secondary persistent indexes backing the many `FILTER doc.<field> == ...` AQL queries
# across the app. Without these ArangoDB falls back to full collection scans (slow on the
# ~59k documents / ~190k softwares / ~750k authors in production). Edge collections already
# carry an automatic `_from`/`_to` edge index, so traversals need nothing extra here.
INDEX_FIELDS = {
    'documents':  [['file_hal_id']],
    'structures': [['id_haureal'], ['type']],
    'softwares':  [['software_name.normalizedForm'], ['software_name.rawForm']],
    'authors':    [['id.halauthorid']],
}


def _ensure_persistent_index(collection, fields):
    """Create one sparse persistent index, building it in the background when supported.

    `pyArango.ensurePersistentIndex` has no `inBackground` argument, so prefer the generic
    `ensureIndex`, which forwards extra kwargs straight to ArangoDB's index API (background
    build avoids write-locking large collections). Fall back to the typed helper on older
    pyArango versions that lack `ensureIndex`.
    """
    if hasattr(collection, "ensureIndex"):
        try:
            return collection.ensureIndex("persistent", fields, sparse=True, inBackground=True)
        except TypeError:
            pass  # signature mismatch — fall through to the typed helper
    return collection.ensurePersistentIndex(fields, sparse=True)


def ensure_indexes(db):
    """Create the secondary persistent indexes the app relies on.

    Idempotent and safe to call on every startup: ArangoDB returns the existing index when
    one with the same definition already exists. `sparse=True` skips documents missing the
    field (e.g. softwares without a `url`).
    """
    for collection_name, field_sets in INDEX_FIELDS.items():
        collection = check_or_create_collection(db, collection_name)
        for fields in field_sets:
            try:
                _ensure_persistent_index(collection, fields)
            except Exception as e:
                print(f"⚠️ Could not ensure index {collection_name}{fields}: {e}")

    # Shared cache-invalidation counter, read on every cached (dashboard) request.
    check_or_create_collection(db, CACHE_VERSION_COLLECTION)


def duplicates_JSON(lst):
    seen = set()
    duplicates = []

    for item in lst:
        item_hashable = str(item)
        if item_hashable in seen:
            duplicates.append(item)
        else:
            seen.add(item_hashable)

    return duplicates

def find_ancestor_paths(current_affiliation_id, ns, tree):
    # Look for the current structure's relations
    list_relation = tree.find(
        f".//tei:back//tei:listOrg//tei:org[@xml:id='{current_affiliation_id}']//tei:listRelation", ns)

    # If no relations, we're at the top, return the current structure as the only member of the path
    if list_relation is None:
        return [[
            current_affiliation_id]]  # Return a list with a single path containing the current structure

    # Collect all direct parent relations (and their types)
    direct_parents = []
    for relation in list_relation:
        if relation.attrib.get('type') == 'direct':
            parent_id = relation.attrib['active'][1:]  # Strip the initial "#" for the parent ID
            direct_parents.append(parent_id)

    # If no direct parents, return the current structure as the topmost node
    if not direct_parents:
        return [[current_affiliation_id]]  # Return a path with only the current structure

    # For each direct parent, find its ancestor paths and create a separate list for each path
    all_paths = []
    for parent_id in direct_parents:
        parent_paths = find_ancestor_paths(parent_id, ns, tree)  # Recursive call for each parent
        for path in parent_paths:
            all_paths.append(
                [current_affiliation_id] + path)  # Create a separate path for each relation
    return all_paths  # Return all paths for the current structure

def update_nb_document_failed(error_log,db):
    check_or_create_collection(db, 'notifications_failed')
    type = error_log["step"]
    # UPSERT in ArangoDB: insert if not exists, update if exists
    query = f"""
    UPSERT {{ type: "{type}" }}
    INSERT {{ type: "{type}", count: 1}}
    UPDATE {{ 
        count: OLD.count + 1, 
    }} IN notifications_failed
    RETURN NEW
    """
    db.AQLQuery(query, rawResults=True)

def update_nb_notification(db, filename):
    notifications_collection = check_or_create_collection(db, 'notifications')
    # Get today's date as YYYY-MM-DD
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    try:
        # UPSERT in ArangoDB: insert if not exists, update if exists
        query = f"""
        UPSERT {{ date: "{today_str}" }}
        INSERT {{ date: "{today_str}", count: 1, filenames: ["{filename}"] }}
        UPDATE {{ 
            count: OLD.count + 1, 
            filenames: PUSH(OLD.filenames, "{filename}") 
        }} IN notifications
        RETURN NEW
        """
        result = db.AQLQuery(query, rawResults=True)
        result = result[0]
        result['filenames'] = len(result['filenames'])
        return result

    except AQLQueryError as e:
        print(f"⚠️ AQL error while updating notifications: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in update_nb_notification: {e}")
        return None
    
def update_nb_mention(db):
    mentions_collection = check_or_create_collection(db, 'mentions')
    # Get today's date as YYYY-MM-DD
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    try:
        # UPSERT in ArangoDB: insert if not exists, update if exists
        query = f"""
        UPSERT {{ date: "{today_str}" }}
        INSERT {{ date: "{today_str}", count: 1 }}
        UPDATE {{ count: OLD.count + 1 }} IN mentions
        RETURN NEW
        """
        result = db.AQLQuery(query, rawResults=True)
        return result

    except AQLQueryError as e:
        print(f"⚠️ AQL error while updating mentions: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in update_nb_mention: {e}")
        return None
    
def update_nb_accepted(db):
    accepted_collection = check_or_create_collection(db, 'accepted')
    # Get today's date as YYYY-MM-DD
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    try:
        # UPSERT in ArangoDB: insert if not exists, update if exists
        query = f"""
        UPSERT {{ date: "{today_str}" }}
        INSERT {{ date: "{today_str}", count: 1 }}
        UPDATE {{ count: OLD.count + 1 }} IN accepted
        RETURN NEW
        """
        result = db.AQLQuery(query, rawResults=True)
        return result

    except AQLQueryError as e:
        print(f"⚠️ AQL error while updating accepted: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in update_nb_accepted: {e}")
        return None

def update_nb_rejected(db):
    rejected_collection = check_or_create_collection(db, 'rejected')
    # Get today's date as YYYY-MM-DD
    today = date.today()
    today_str = today.strftime("%Y-%m-%d")

    try:
        # UPSERT in ArangoDB: insert if not exists, update if exists
        query = f"""
        UPSERT {{ date: "{today_str}" }}
        INSERT {{ date: "{today_str}", count: 1 }}
        UPDATE {{ count: OLD.count + 1 }} IN rejected
        RETURN NEW
        """
        result = db.AQLQuery(query, rawResults=True)
        return result

    except AQLQueryError as e:
        print(f"⚠️ AQL error while updating rejected: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in update_nb_rejected: {e}")
        return None


# Daily counters split by mention characterization. One collection per attribute
# ("mentions_used" / "mentions_created" / "mentions_shared"), same {date, count} shape
# as the `mentions` counter above, so the existing `_daily_counts` reader and the home
# line-chart helper work on them unchanged.
_ATTRIBUTE_COLLECTIONS = {
    "used": "mentions_used",
    "created": "mentions_created",
    "shared": "mentions_shared",
}


def dominant_attribute(mention):
    """Return the dominant characterization of a software mention — "used",
    "created", or "shared" — or None if it carries no usable characterization.

    This must mirror the dominant-attribute logic in ``utils/dashboard.py``
    (``_AGG_TAIL``) so the home-page trend charts and the dashboard agree:

      - mentions store ``mentionContextAttributes`` with sub-keys ``used`` /
        ``created`` / ``shared``, each an object with a ``.score`` (a float).
      - the dominant attribute is the one with the HIGHEST score.
      - on a tie, resolve in the order used > created > shared.
      - the field MAY BE MISSING on some mentions (documented gotcha in
        CLAUDE.md) — and individual sub-keys/scores may be absent too. In any
        of those cases there is no usable characterization, so return None.

    `mention` is the raw mention dict from the SOFTCITE JSON (so the attribute
    block is at ``mention.get("mentionContextAttributes")``).
    """
    attributes = mention.get("mentionContextAttributes")
    if not isinstance(attributes, dict):
        return None

    # Collect only the scores that are actually present and numeric, mirroring
    # AQL's MAX([...]) which silently ignores nulls: a mention carrying just one
    # of the three sub-keys still resolves to that one.
    scores = {}
    for attr in ("used", "created", "shared"):
        block = attributes.get(attr)
        if isinstance(block, dict):
            score = block.get("score")
            if isinstance(score, (int, float)):
                scores[attr] = score

    if not scores:
        return None

    # Highest score wins; ties resolve used > created > shared. Iterating in that
    # fixed order and keeping the first strict maximum encodes the tie-break.
    best = None
    for attr in ("used", "created", "shared"):
        if attr in scores and (best is None or scores[attr] > scores[best]):
            best = attr
    return best


def update_nb_attribute(db, attribute):
    """Increment today's daily counter for one characterization bucket.

    `attribute` must be one of "used" / "created" / "shared"; anything else
    (including None) is a no-op, so callers can pass ``dominant_attribute(...)``
    straight through without guarding.
    """
    collection = _ATTRIBUTE_COLLECTIONS.get(attribute)
    if collection is None:
        return None

    check_or_create_collection(db, collection)
    today_str = date.today().strftime("%Y-%m-%d")

    try:
        # UPSERT in ArangoDB: insert if not exists, update if exists. The
        # collection name is a trusted constant from _ATTRIBUTE_COLLECTIONS
        # (never user input), so interpolating it here is safe.
        query = f"""
        UPSERT {{ date: "{today_str}" }}
        INSERT {{ date: "{today_str}", count: 1 }}
        UPDATE {{ count: OLD.count + 1 }} IN {collection}
        RETURN NEW
        """
        return db.AQLQuery(query, rawResults=True)

    except AQLQueryError as e:
        print(f"⚠️ AQL error while updating {collection}: {e}")
        return None
    except Exception as e:
        print(f"⚠️ Unexpected error in update_nb_attribute: {e}")
        return None


def insert_json_db(data_path_json,data_path_xml,db, blacklist):
    elastich_alive = is_elasticsearch_alive()

    if not elastich_alive[0]:
        return ["Elasticsearch Error",elastich_alive[1]]

    xml_safe_parser = ""

    # Create or retrieve collections
    documents_collection = check_or_create_collection(db, 'documents')
    softwares_collection = check_or_create_collection(db, 'softwares')
    references_collection = check_or_create_collection(db, 'references')
    authors_collection = check_or_create_collection(db, 'authors')
    structures_collection = check_or_create_collection(db, 'structures')
    list_relation_collection = check_or_create_collection(db, 'list_relation')

    # Create or retrieve edge collections
    doc_struc_edge = check_or_create_collection(db, 'edge_doc_to_struc', 'Edges')
    auth_struc_edge = check_or_create_collection(db, 'edge_auth_to_struc', 'Edges')
    doc_soft_edge = check_or_create_collection(db, 'edge_doc_to_software', 'Edges')
    doc_ref_edge = check_or_create_collection(db, 'edge_doc_to_reference', 'Edges')
    doc_auth_edge = check_or_create_collection(db, 'edge_doc_to_author', 'Edges')
    auth_rel_struc_edge = check_or_create_collection(db, 'edge_auth_to_rel_struc', 'Edges')

    files_list_registered = db.AQLQuery('FOR hal_id in documents RETURN hal_id.file_hal_id', rawResults=True, batchSize=2000)
    dict_registered = {}

    xml_filename = os.path.basename(data_path_xml)
    base_name_xml, _ = os.path.splitext(xml_filename)

    # if already registered, remove and exit
    if base_name_xml in files_list_registered:
        try:
            if os.path.exists(data_path_xml):
                os.remove(data_path_xml)
            if os.path.exists(data_path_json):
                os.remove(data_path_json)
        except Exception as e:
            return ["Document's registration check",f"Document {base_name_xml} deletion failed."]
        return ["Document's registration check",f"Document {base_name_xml} was already registered and has been removed."]

    if base_name_xml[-2] == "v":
       id_for_hal_api =  base_name_xml[-2]
    else:
        id_for_hal_api = base_name_xml

    url = "https://api.archives-ouvertes.fr/search/"
    params = {
        "q": f"halId_id:{id_for_hal_api}",
        "rows": 10,
        "fl": "citationFull_s"
    }


    response = requests.get(url, params=params)
    if response.status_code == 200:
        data = response.json()
        try:
            citations = data["response"]["docs"][0]["citationFull_s"]
        except IndexError:
            citations = None

    try:
        # Try normal parser first
        tree = ET.parse(data_path_xml)
    except ET.ParseError:
        # If normal parse fails, try safe parser
        tree = parse_xml_safely(data_path_xml)
        xml_safe_parser = f"Safe XML Parser used for this file {data_path_xml}"
        if tree is None:
            return ['XML Parsing', f'Cleaning failed for the XML file: {data_path_xml}']
    except Exception as e:
        # Unexpected errors
        return ['XML Parsing', f'Unexpected error: {e} {data_path_xml}']

    data_json_get_document = {}
    ns = {"tei": "http://www.tei-c.org/ns/1.0", 'xml': 'http://www.w3.org/XML/1998/namespace'}

    # Find the measure with commodity="totalSearchResults"
    measure_elem = tree.find(".//tei:profileDesc/tei:creation/tei:measure[@commodity='totalSearchResults']", ns)
    if measure_elem is not None:
        quantity = measure_elem.get("quantity")
        if quantity == 0:
            return["XML Parsing",f"The xml returned is empty for {data_path_xml}"]

    # DOCUMENT -----------------------------------------------------

    title_elem = tree.find(".//tei:listBibl//tei:titleStmt//tei:title", ns)

    if title_elem is not None and title_elem.text:
        title = title_elem.text
    else:
        title = ""  # no text found

    doc_type = tree.findall(".//tei:listBibl//tei:biblFull//tei:profileDesc//tei:textClass//tei:classCode", ns)
    for tag in doc_type:
        if tag.attrib.get('n') == 'COMM':
            production_date = tree.find(".//tei:listBibl//tei:biblFull//tei:sourceDesc//tei:biblStruct//tei:monogr//tei:meeting//tei:date[@type='start']", ns)
            if production_date is not None:
                data_json_get_document['date'] = production_date.text[:4]
        else:
            production_date = tree.find(
                ".//tei:listBibl//tei:biblFull//tei:sourceDesc//tei:biblStruct//tei:monogr//tei:imprint//tei:date[@type='datePub']",
                ns)
            if production_date is not None:
                data_json_get_document['date'] = production_date.text[:4]
            else:
                production_date = tree.find(
                    ".//tei:listBibl//tei:biblFull//tei:editionStmt//tei:edition[@type='current']//tei:date[@type='whenProduced']",
                    ns)
                if production_date is not None:
                    data_json_get_document['date'] = production_date.text[:4]


    abstract = tree.find(".//{http://www.tei-c.org/ns/1.0}abstract")
    if abstract:
        tag_text = list(abstract)[0]
        if tag_text.tag == '{http://www.tei-c.org/ns/1.0}p':
            abstract = "".join(tag_text.itertext())
            data_json_get_document['abstract'] = ['HAL' , abstract]
        if tag_text.tag == '{http://www.tei-c.org/ns/1.0}div':
            for p_tag in list(tag_text):
                text = "".join(p_tag.itertext())
            data_json_get_document['abstract'] = ['GROBID' , abstract]

    data_json_get_document['file_hal_id'] = base_name_xml
    data_json_get_document['citation'] = citations
    data_json_get_document['title'] = title

    document_document = documents_collection.createDocument(data_json_get_document)
    document_document.save()

    # SOFTWARE -----------------------------------------------------

    with open(data_path_json, 'r') as json_file:
        data_json = json.load(json_file)
        data_json_get_mentions = data_json.get("mentions")
        # Remove duplicates
        for elm in duplicates_JSON(data_json_get_mentions):
            data_json_get_mentions.remove(elm)

        # Process each mention
        for mention in data_json_get_mentions:
            if mention['software-name']['normalizedForm'] not in blacklist:
                mention['software_name'] = mention.pop('software-name')
                mention['software_type'] = mention.pop('software-type')
                software_document = softwares_collection.createDocument(mention)
                software_document.save()

                # Create edge from document to software
                edge_doc_soft = doc_soft_edge.createEdge()
                edge_doc_soft['_from'] = document_document._id
                edge_doc_soft['_to'] = software_document._id
                edge_doc_soft.save()
                update_nb_mention(db)
                # split the daily mention count by characterization for the
                # home-page used/created/shared trend charts (no-op when the
                # mention has no usable mentionContextAttributes)
                update_nb_attribute(db, dominant_attribute(mention))

# REFERENCES -----------------------------------------------------

        # Process each reference
        data_json_get_references = data_json.get("references")
        for reference in data_json_get_references:
            try:
                result_json = transformer_TEI_JSON(reference['tei'])
            except Exception as e:
                return["References processing, XML -> JSON",f"Error during the transformation from XML to JSON: {e}"]
            if result_json:
                reference['json'] = result_json
            references_document = references_collection.createDocument(reference)
            references_document.save()

            # Create edge from document to reference
            edge_doc_ref = doc_ref_edge.createEdge()
            edge_doc_ref['_from'] = document_document._id
            edge_doc_ref['_to'] = references_document._id
            edge_doc_ref.save()

    # AUTHORS -----------------------------------------------------

    author_list = tree.findall(".//tei:listBibl//tei:titleStmt//tei:author", ns)
    for elm in author_list:
        author = {}
        persName = elm.find("{http://www.tei-c.org/ns/1.0}persName")
        author['role'] = elm.attrib['role']
        author = {}

        # idhal
        author_id = {}
        id_halid = None
        id_halauthorid = None
        id_halid = elm.findall(".//tei:idno[@type='idhal']", ns)
        if len(id_halid) > 0:
            for id_type in id_halid:
                author_id[id_type.attrib['notation']] = id_type.text
        id_halauthorid = elm.find(".//tei:idno[@type='halauthorid']", ns)
        if id_halauthorid is not None:
            author_id[id_halauthorid.attrib['type']] = id_halauthorid.text
        try:
            author_final_id = author_id['numeric']
        except KeyError:
            author_final_id = author_id['halauthorid']
        if author_final_id in list(dict_registered.keys()):
            registered = True
        else:
            registered = False

        # name
        author_name = {}
        persName = elm.find("{http://www.tei-c.org/ns/1.0}persName")
        for name in persName:
            author_name[name.tag.split('}')[1]] = name.text

        # document
        author_documents = []
        try:
            # Create a dictionary for each document and append it to the list
            document_data = {
                'document_halid': base_name_xml,
                'role': elm.attrib['role']
            }
            author_documents.append(document_data)
        except KeyError:
            # Handle the case where 'role' may not be present, and append with a default 'role'
            document_data = {
                'document_halid': base_name_xml,
                'role': elm.attrib.get('role', 'unknown')
            }
            author_documents.append(document_data)

        if registered == False:

            author['id'] = author_id
            author['name'] = author_name
            author['documents'] = author_documents

            document_author = authors_collection.createDocument(author)
            document_author.save()
            dict_registered[author_final_id] = document_author._id
            # print(dict_registered)
            edge_doc_auth = doc_auth_edge.createEdge()
            edge_doc_auth['_from'] = document_document._id
            edge_doc_auth['_to'] = document_author._id
            edge_doc_auth.save()
            author_document_id = document_author._id

        elif registered == True:
            author_document_id = dict_registered[author_final_id]
            # AQL query to append to the documents and affiliation
            aql_query = f'''
                        FOR doc IN authors
                            FILTER doc._id == '{author_document_id}'
                            UPDATE doc WITH {{ 
                                documents: APPEND(doc.documents, {author_documents}, true), 
                            }} IN authors
                        '''
            # Execute the AQL query
            db.AQLQuery(aql_query, rawResults=True)
            edge_doc_auth = doc_auth_edge.createEdge()
            edge_doc_auth['_from'] = document_document._id
            edge_doc_auth['_to'] = author_document_id
            edge_doc_auth.save()
    # STRUCT -----------------------------------------------------

        # Main logic to collect paths for all affiliations
        author_affiliation_paths = []
        affiliations_list = elm.findall("{http://www.tei-c.org/ns/1.0}affiliation")
        if len(affiliations_list) > 0:
            for affiliation in affiliations_list:
                # Start with the affiliation's referenced structure
                current_affiliation_id = affiliation.attrib['ref'][1:]  # Strip the initial "#"
                ancestor_paths = find_ancestor_paths(current_affiliation_id, ns,
                                                     tree)  # Get all full hierarchy paths
                author_affiliation_paths.extend(ancestor_paths)  # Add all paths to the final list
                # Dictionary to store document key to _id mappings
                for author_affiliation_path in author_affiliation_paths:
                    list_relation_idstruct = []
                    for index, structure in enumerate(author_affiliation_path):
                        result = db.AQLQuery(
                            f'FOR struc IN structures FILTER struc.id_haureal == "{structure}" RETURN struc._id',
                            rawResults=True)
                        if len(result) == 0:
                            affiliated_struct = tree.find(
                                f".//tei:back//tei:listOrg//tei:org[@xml:id='{structure}']", ns)
                            if affiliated_struct is not None:
                                affiliated_struct_name = affiliated_struct.findall('tei:orgName', ns)
                                if affiliated_struct_name is not None:
                                    org = {}
                                    org['status'] = affiliated_struct.attrib['status']
                                    org['url_team'] = False
                                    url_team = affiliated_struct.find(
                                        './/{http://www.tei-c.org/ns/1.0}desc//ref[@type="url"]')
                                    for url_team in affiliated_struct.find(
                                            './/{http://www.tei-c.org/ns/1.0}desc'):
                                        if url_team.attrib == {'type': 'url'}:
                                            org['url_team'] = url_team.text
                                    try:
                                        list_affiliated_str = list(affiliated_struct.find(
                                            ".//{http://www.tei-c.org/ns/1.0}listRelation"))
                                    except TypeError:
                                        list_affiliated_str = []
                                    for struct in affiliated_struct_name:
                                        if struct.attrib:
                                            org[struct.attrib['type']] = struct.text
                                        else:
                                            org["name"] = struct.text
                                    org['id_haureal'] = affiliated_struct.attrib["{http://www.w3.org/XML/1998/namespace}id"]
                                    org['type'] = affiliated_struct.attrib['type']
                                    document_org = structures_collection.createDocument(org)
                                    document_org.save()
                                    struct_id = document_org._id
                        else:
                            struct_id = result[0]
                            pass

                        query = f"""
                                    for edge in edge_doc_to_struc
                                        filter edge._from == "{document_document._id}"
                                        let struct = document(edge._to)
                                        return struct._id
                                        """
                        list_registered_edge_struc_doc = db.AQLQuery(query, rawResults=True)

                        if struct_id not in list_registered_edge_struc_doc:
                            edge_doc_struc = doc_struc_edge.createEdge()
                            edge_doc_struc['_from'] = document_document._id
                            edge_doc_struc['_to'] = struct_id
                            edge_doc_struc.save()

                        query = f"""
                                    for edge in edge_auth_to_struc
                                        filter edge._from == "{author_document_id}"
                                        let struct = document(edge._to)
                                        return struct._id
                                        """
                        list_registered_edge_struc_author = db.AQLQuery(query, rawResults=True)

                        if struct_id not in list_registered_edge_struc_author:
                            edge_auth_struc = auth_struc_edge.createEdge()
                            edge_auth_struc['_from'] = author_document_id
                            edge_auth_struc['_to'] = struct_id
                            edge_auth_struc.save()

                        result = db.AQLQuery(
                            f'FOR struc IN structures FILTER struc.id_haureal == "{structure}" RETURN struc._id',
                            rawResults=True)
                        if result != []:
                            list_relation_idstruct.append(result[0])

                    list_relation_documents = list_relation_collection.createDocument({"list_relation" : list_relation_idstruct})
                    list_relation_documents.save()

                edge_auth_rel_struc = auth_rel_struc_edge.createEdge()
                edge_auth_rel_struc['_from'] = author_document_id
                edge_auth_rel_struc['_to'] = list_relation_documents._id
                edge_auth_rel_struc.save()
    return ["success",xml_safe_parser]