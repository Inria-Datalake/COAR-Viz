from app.app import app, db
from utils.db import check_or_create_collection
from flask import jsonify, render_template
import csv
from pyArango.theExceptions import AQLQueryError

BLACKLIST_PATH = './app/static/data/blacklist.csv'

def get_list_blacklist():

    try:
        result = db.AQLQuery(
            "FOR b IN blacklist RETURN DISTINCT b.name",
            rawResults=True, batchSize=all
        )
    except AQLQueryError:
        return []

    return result[:]

def apply_blacklist_to_db():
    blacklist = get_list_blacklist()

    deleted_mention_list = []

    query = '''
        FOR soft IN softwares
            RETURN [soft._id, soft.software_name.normalizedForm]
    '''

    list_software_documents = db.AQLQuery(query, rawResults=True)


    for software_document in list_software_documents:
        if software_document[1] in blacklist:
            software_id = software_document[0]
            log_message = test_delete_document_and_edges(db, software_id, "softwares")
            deleted_mention_list.append(log_message)
            delete_document_and_edges(db, software_id, "softwares")

    return deleted_mention_list

def delete_document_and_edges(db, doc_id, collection_name):

    edge_collections = [
        'edge_doc_to_struc',
        'edge_auth_to_struc',
        'edge_doc_to_software',
        'edge_doc_to_reference',
        'edge_doc_to_author',
        'edge_auth_to_rel_struc'
    ]

    # Delete all edges connected to this document
    for edge_name in edge_collections:
        edge_col = db[edge_name]
        query = f'''
        FOR edge IN {edge_name}
            FILTER edge._from == "{doc_id}" OR edge._to == "{doc_id}"
            REMOVE edge IN {edge_name}
        '''
        db.AQLQuery(query, rawResults=True)
        print(f"Deleted edges from collection: {edge_name}")

    # Delete the document itself
    collection = db[collection_name]
    doc = collection[doc_id.split('/')[-1]]  # extract the key from _id
    doc.delete()
    print(f"Deleted document: {doc_id}")

def test_delete_document_and_edges(db, doc_id, collection_name):
    log = []   # <-- collect all items that would be deleted

    edge_collections = [
        'edge_doc_to_struc',
        'edge_auth_to_struc',
        'edge_doc_to_software',
        'edge_doc_to_reference',
        'edge_doc_to_author',
        'edge_auth_to_rel_struc'
    ]

    # Check edges that would be deleted
    for edge_name in edge_collections:
        query = f'''
        FOR edge IN {edge_name}
            FILTER edge._from == "{doc_id}" OR edge._to == "{doc_id}"
            RETURN edge
        '''

        edges = db.AQLQuery(query, rawResults=True)

        # If edges were found, record them
        for edge in edges:
            log.append({
                "type": "edge",
                "collection": edge_name,
                "id": edge["_id"],
                "from": edge["_from"],
                "to": edge["_to"],
                "action": "deleted"
            })

    # Check document that would be deleted
    key = doc_id.split('/')[-1]
    collection = db[collection_name]

    try:
        doc = collection[key]
        log.append({
            "type": "document",
            "collection": collection_name,
            "id": doc_id,
            "action": "deleted"
        })
    except KeyError:
        log.append({
            "type": "document",
            "collection": collection_name,
            "id": doc_id,
            "action": "not_found"
        })

    return log

@app.route('/add_to_blacklist/<software_name>')
def add_to_blacklist(software_name):

    # Read existing blacklist
    existing = get_list_blacklist()

    # Check if already added
    if software_name in existing:
        return jsonify({"message": "Software already in blacklist", "software": software_name}), 500
    else:
        query = """
               UPSERT { name: @name }
               INSERT { name: @name }
               UPDATE { name: @name }
               IN blacklist
               RETURN NEW
           """
        db.AQLQuery(
            query,
            bindVars={"name": software_name},
            rawResults=True
        )

    return jsonify({"message": "Software added to blacklist", "software": software_name}), 201

@app.route('/remove_from_blacklist/<software_name>', methods=['DELETE'])
def remove_from_blacklist(software_name):

    # Read existing blacklist
    existing = get_list_blacklist()

    # Check if software exists
    if software_name not in existing:
        return jsonify({
            "message": "Software not found in blacklist",
            "software": software_name
        }), 409

    # Remove from blacklist
    query = """
        FOR s IN blacklist
            FILTER s.name == @name
            REMOVE s IN blacklist
            RETURN OLD
    """

    db.AQLQuery(
        query,
        bindVars={"name": software_name},
        rawResults=True
    )

    return jsonify({
        "message": "Software removed from blacklist",
        "software": software_name
    }), 200


@app.route('/update_db_blacklist')
def update_db_blacklist():
    deleted_mention_list = apply_blacklist_to_db()
    return jsonify({
        "message": "Database blacklist updated",
        "deleted_mention": deleted_mention_list
    })

@app.route('/register_blacklist')
def register_blacklist():

    check_or_create_collection(db, 'blacklist')

    list_already_registered = get_list_blacklist()
    registered = []

    query = """
        UPSERT { name: @name }
        INSERT { name: @name }
        UPDATE { name: @name }
        IN blacklist
        RETURN NEW
    """

    with open(BLACKLIST_PATH, newline='', encoding='utf-8') as csvfile:
        reader = csv.reader(csvfile)
        next(reader, None)  # skip header safely

        for row in reader:
            if not row:
                continue

            software_name = row[0]

            if software_name in list_already_registered:
                continue

            result = db.AQLQuery(
                query,
                bindVars={"name": software_name},
                rawResults=True
            )

            if result:
                registered.append(result[0])

    return jsonify({
        "message": "Blacklist registered in database",
        "registered_count": len(registered),
        "registered": registered
    })

@app.route('/blacklist', methods=['GET', 'POST'])
def blacklist_form():
    data = get_list_blacklist()
    messages = ""
    return render_template('pages/blacklist.html', data=data, messages=messages)

