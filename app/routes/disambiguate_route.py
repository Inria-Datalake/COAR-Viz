from app.app import app, db
from flask import render_template, jsonify
from utils.disambiguate import disambiguate_from_software, fetch_for_software
from rapidfuzz import fuzz

@app.route('/disambiguate')
def disambiguate():
    return render_template('pages/disambiguate.html')

@app.route('/api/disambiguate/list_software_search')
def list_software():
    query = f'''
            for software in softwares
            return distinct software.software_name.rawForm
            '''
    response = db.AQLQuery(query, rawResults=True, batchSize=2000)
    return list(response)

@app.route('/api/disambiguate/list_dup_software/<softwareName>/<fuzz>/<avg>/<partial>')
def retrieve(softwareName,fuzz,avg,partial):
    result = disambiguate_from_software(softwareName,fuzz,avg, partial)
    return jsonify({'result': result})

@app.route('/api/disambiguate/fetch_data/<softwareName>/<docid>')
def fetch_data(softwareName, docid):
    result = fetch_for_software(softwareName,docid)
    return jsonify(result)

@app.route('/api/disambiguate/fetch_ratio/<softwareName>/<candidateName>', methods=['GET'])
def fetch_ratio(softwareName, candidateName):

    # Compute all three ratios
    normal_ratio = fuzz.ratio(softwareName, candidateName)
    token_ratio = fuzz.token_sort_ratio(softwareName, candidateName)
    partial_ratio_val = fuzz.partial_ratio(softwareName, candidateName)

    # Return according to requested ratio
    result = {
        "normal_ratio": normal_ratio,
        "token_ratio": token_ratio,
        "partial_ratio": partial_ratio_val
    }
    # Otherwise return all three
    return result
