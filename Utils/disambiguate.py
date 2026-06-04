from app.app import db
from rapidfuzz import fuzz

def disambiguate_from_software(software, fuzz_threshold:float,avg_threshold:float, partial_threshold:float):
    # Ensure thresholds are floats
    fuzz_threshold = float(fuzz_threshold)
    avg_threshold = float(avg_threshold)
    partial_threshold = float(partial_threshold)

    # 1️⃣ Get all software names
    query = '''
        FOR s IN softwares
            RETURN DISTINCT s.software_name.rawForm
    '''
    list_software = list(db.AQLQuery(query, rawResults=True, batchSize=2000))

    list_possible_dup = [software]  # use a set (no duplicates)

    # 2️⃣ Compare against every software in database
    for existing in list_software:
        if existing == software:
            continue
        normal_ratio = fuzz.ratio(software, existing)
        token_ratio = fuzz.token_sort_ratio(software, existing)
        partial_ratio_val = fuzz.partial_ratio(software, existing)

        if fuzz_threshold and normal_ratio >= fuzz_threshold:
            list_possible_dup.append(existing)

        if avg_threshold and token_ratio >= avg_threshold:
            list_possible_dup.append(existing)

        if partial_threshold and partial_ratio_val >= partial_threshold:
            list_possible_dup.append(existing)

    # 3️⃣ Fetch docids for every candidate software
    list_possible_dup_docid = []
    query = '''
        FOR s IN softwares
            FILTER s.software_name.rawForm == @sw
            FOR e IN edge_doc_to_software
                FILTER e._to == s._id
                LET doc = DOCUMENT(e._from)
                RETURN DISTINCT doc._key
    '''
    for sw in list_possible_dup:
        result_docids = list(db.AQLQuery(query, rawResults=True, batchSize=2000, bindVars={"sw": sw}))

        for docid in result_docids:
            list_possible_dup_docid.append([sw, docid])

    return list_possible_dup_docid

def fetch_for_software(softwareName, docid):
    query = f'''
                LET docId = @docId
                
                // -----------------------------------
                // DOCUMENT INFO
                // -----------------------------------
                LET docInfo = (
                    LET d = DOCUMENT(docId)
                    RETURN {{
                        file_hal_id: d.file_hal_id,
                        date: d.date,
                        title: d.title
                    }}
                )
                
                // -----------------------------------
                // SOFTWARE (NOT DISTINCT — preserve context)
                // -----------------------------------
                LET software = (
                    FOR edge IN edge_doc_to_software
                        FILTER edge._from == docId
                        LET sw = DOCUMENT(edge._to)
                        FILTER sw.software_name.normalizedForm == @softwareName
                        RETURN {{
                            name: sw.software_name.rawForm,
                            context: sw.context
                        }}
                )
                
                //////////////////////////////
                // URL (DISTINCT)
                //////////////////////////////
                LET url = (
                    FOR edge IN edge_doc_to_software
                        FILTER edge._from == docId
                        LET sw = DOCUMENT(edge._to)
                        FILTER sw.software_name.normalizedForm == @softwareName
                        FILTER sw.url.rawForm != null && sw.url.rawForm != ""
                        COLLECT urlValue = sw.url.rawForm
                        RETURN urlValue
                )
                
                
                // -----------------------------------
                // Verified
                // -----------------------------------
                LET verification_by_author = (
                    FOR edge IN edge_doc_to_software
                        FILTER edge._from == docId
                        LET sw = DOCUMENT(edge._to)
                        FILTER sw.verification_by_author in [true, false]
                        FILTER sw.software_name.normalizedForm == @softwareName
                        return distinct sw.verification_by_author
                )

                
                // -----------------------------------
                // STRUCTURES (DISTINCT)
                // -----------------------------------
                LET structures = (
                    FOR edge IN edge_doc_to_struc
                        FILTER edge._from == docId
                        LET s = DOCUMENT(edge._to)
                        filter s.type in ["researchteam","department","laboratory"]
                        COLLECT      /* DISTINCT */
                            id = s.id_haureal,
                            name = s.name,
                            acr = s.acronym || "None"
                        RETURN {{
                            id_haureal: id,
                            name,
                            acronym: acr
                        }}
                )
                
                // -----------------------------------
                // AUTHORS (DISTINCT)
                // -----------------------------------
                LET authors = (
                    FOR edge IN edge_doc_to_author
                        FILTER edge._from == docId
                        LET a = DOCUMENT(edge._to)
                        LET fullName = CONCAT(a.name.forename, " ", a.name.surname)
                        COLLECT     /* DISTINCT */
                            full = fullName,
                            authorId = a.id.halauthorid
                        RETURN {{
                            name: full,
                            halAuthorId: authorId
                        }}
                )
                
                // -----------------------------------
                // FINAL STRUCTURED RESULT
                // -----------------------------------
                RETURN {{
                    document: FIRST(docInfo),
                    software,
                    authors,
                    structures,
                    url: url,
                    verification: verification_by_author
                }}
                '''
    data_software = db.AQLQuery(query, rawResults=True, batchSize=2000,
                                bindVars={"docId": f"documents/{docid}", "softwareName": softwareName})
    return data_software[0]