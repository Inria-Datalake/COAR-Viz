/*****************************************
 *  GLOBAL STATE
 *****************************************/
const state = {
    availableSoftware: [],
    currentList: [],      // [["SoftwareA", "doc1"], ["SoftwareB","doc2"], ...]
    og: null,             // { name, docid, json }
};


/*****************************************
 *  ELEMENTS
 *****************************************/
const resultBox = document.getElementById("result-box-dis");
const inputBox = document.getElementById("input-box-dis");
const cardContainer = document.getElementById("card-box-disambiguate");


// Sliders
const sliders = {
    range1: document.getElementById("fuzz_ratio"),
    range2: document.getElementById("average_ratio"),
    range3: document.getElementById("partial_ratio"),
    val1: document.getElementById("fuzz_average"),
    val2: document.getElementById("value_average"),
    val3: document.getElementById("value_partial")
};

/*****************************************
 *  API HELPERS
 *****************************************/
async function apiGET(url) {
    const response = await fetch(url, { method: "GET" });
    if (!response.ok) throw new Error(`HTTP error: ${response.status}`);
    return await response.json();
}

async function fetchSoftwareList() {
    try {
        state.availableSoftware = await apiGET(`${window.URL_PREFIX}/api/disambiguate/list_software_search`);
    } catch (err) {
        console.error("Error fetching software list:", err);
    }
}

async function fetchSoftwareJSON(name, docid) {
    try {
        return await apiGET(`${window.URL_PREFIX}/api/disambiguate/fetch_data/${name}/${docid}`);
    } catch (err) {
        console.error(`Error fetching data for ${name}`, err);
        return null;
    }
}

/*****************************************
 *  SET ORIGINAL SOFTWARE
 *****************************************/
async function setOriginalSoftware(name, docid) {
    const data = await fetchSoftwareJSON(name, docid);
    state.og = {
        name,
        docid,
        json: Array.isArray(data) ? data : [data]
    };
}

/*****************************************
 *  RENDER HELPERS
 *****************************************/
function renderJSON(obj,sw,docid) {
    if (!obj) return "<p>No data available.</p>";

    // At this point, obj must be an array
    if (!Array.isArray(obj)) {
        return `<p>Invalid data format (expected array but got ${typeof obj}).</p>`;
    }

    if (obj.length === 0) {
        return "<p>No documents found.</p>";
    }

    return obj.map(item => {
        const doc = item.document || {};
        const softwareList = item.software || [];
        const authors = item.authors || [];
        const structures = item.structures || [];
        const url = item.url || [];
        const verified = item.verification || [];

        if (verified.length > 0 && verified[0] === false) {
            verification_status = `
                <p id="rejected_by_the_author"><strong>This mention was rejected by an author</strong></p>
            `;
        }
        else if (verified.length > 0 && verified[0] === true) {
            verification_status = `
                <p id="accepted_by_the_author"><strong>This mention was approved by an author</strong></p>
            `;
        }
        else {
            verification_status = ``;
        }

        return `
            <div class="doc-card">
                <h3>${doc.title || "(No title)"}</h3>
                <button class="set-og-btn" data-sw="${sw}" data-docid="${docid}">
                    Use as Original
                </button>
                
                ${verification_status}
                
                <p><strong>HAL ID:</strong> <a href="${window.URL_PREFIX}/doc/${doc.file_hal_id}">${doc.file_hal_id}</a></p>
                <p><strong>Date:</strong> ${doc.date || "N/A"}</p>
                <p><strong>Software form:</strong> ${sw || "N/A"}</p>
                ${url && url.length > 0 ? `
                <p><strong>URL:</strong>
                    ${url.map(u => `<a href="${u}" target="_blank">${u}</a>`).join("")}
                ` : ""}</p>
                <h4>Software Mentions (${softwareList.length}):</h4>
                <ul>
                  ${
                    softwareList.map(sw => {
                      // Escape regex special characters
                      const escapeRegExp = s => s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
                      const regex = new RegExp(escapeRegExp(sw.name), 'gi');
                
                      // Replace software name in context with <strong> tags
                      const highlightedContext = sw.context.replace(regex, `<strong>${sw.name}</strong>`);
                
                      return `<li sw-name="${sw.name}"><strong>${sw.name}</strong>:${highlightedContext}</li>`;
                    }).join('')
                  }
                </ul>

                <h4>Authors:</h4>
                <ul>
                    ${authors.map(a =>
                        `<li auth-id="${a.halAuthorId}">${a.name}</li>`
                    ).join("")}
                </ul>

                <h4>Structures:</h4>
                <ul>
                    ${structures.map(s =>
                        `<li struc-id="${s.id_haureal}">${s.name}${s.acronym && s.acronym !== "None" ? " ("+s.acronym+")" : ""}</li>`
                    ).join("")}
                </ul>
            </div>
        `;
    }).join("");
}

function diffSoftwareNames(ogName, swName) {
    if (!ogName || !swName) return { og: ogName, sw: swName };

    let i = 0;
    while (i < ogName.length && i < swName.length && ogName[i] === swName[i]) {
        i++;
    }

    const common = ogName.slice(0, i);
    const ogDiff = ogName.slice(i);
    const swDiff = swName.slice(i);

    return {
        og: `${common}<span class="name-diff">${ogDiff}</span>`,
        sw: `${common}<span class="name-diff">${swDiff}</span>`
    };
}

// Make fetch_ratio async and return the result
async function fetchRatio(target, candidate) {
    try {
        const result = await apiGET(`${window.URL_PREFIX}/api/disambiguate/fetch_ratio/${target}/${candidate}`);
        return result;
    } catch (err) {
        console.error("Error fetching ratio:", err);
        return null;
    }
}

async function renderComparison(ogJson, ogName, swJson, swName) {

    const og = ogJson[0];
    const sw = swJson[0];

    // -----------------------------------------
    // Extract lists
    // -----------------------------------------
    const ogAuthors = og.authors?.map(a => a.halAuthorId) || [];
    const swAuthors = sw.authors?.map(a => a.halAuthorId) || [];

    const ogStruct = og.structures?.map(s => s.id_haureal) || [];
    const swStruct = sw.structures?.map(s => s.id_haureal) || [];

    const swSoftware = sw.software?.map(s => s.context) || [];

    const ogAuthorsById = Object.fromEntries(og.authors.map(a => [a.halAuthorId, a.name]));
    const swAuthorsById = Object.fromEntries(sw.authors.map(a => [a.halAuthorId, a.name]));

    const ogStructById = Object.fromEntries(og.structures.map(s => [s.id_haureal, s.name]));
    const swStructById = Object.fromEntries(sw.structures.map(s => [s.id_haureal, s.name]));

    // -----------------------------------------
    // Compute intersections & differences
    // -----------------------------------------
    const commonAuthors = ogAuthors.filter(id => swAuthors.includes(id));
    const diffAuthorsOG = ogAuthors.filter(id => !swAuthors.includes(id));
    const diffAuthorsSW = swAuthors.filter(id => !ogAuthors.includes(id));

    const commonStruct = ogStruct.filter(id => swStruct.includes(id));
    const diffStructOG = ogStruct.filter(id => !swStruct.includes(id));
    const diffStructSW = swStruct.filter(id => !ogStruct.includes(id));

    // Percentages
    const authorPct = ogAuthors.length ? Math.round((commonAuthors.length / ogAuthors.length) * 100) : 0;
    const structPct = ogStruct.length ? Math.round((commonStruct.length / ogStruct.length) * 100) : 0;

    // Name diff
    const nameDiff = diffSoftwareNames(ogName, swName);

    const docIDcompare = og.document.file_hal_id === sw.document.file_hal_id
        ? `<div class="comparison-row">
                <span class="label">Same Document ID:</span>
                <span class="value" style="color: #0a8a0a"> True </span>
           </div>`
        : `<div class="comparison-row">
                <span class="label">Same Document ID:</span>
                <span class="value" style="color: #b30000"> False </span>
           </div>`;

    let crossContextSummary = "";

    if (ogName !== swName){

    const normalize = s => s.toLowerCase().replace(/\s+/g, " ").trim();

    // Check where OG software name appears in SW context
    const ogContextFoundInSW = [];
    swSoftware.forEach(swCtx => {
        if (normalize(swCtx).includes(normalize(ogName))) {
            ogContextFoundInSW.push(swCtx);
        }
    });

     crossContextSummary = `
            <div class="comparison-row">
                <span class="label">Original software found in Related's contexts:</span>
                <span class="value ${ogContextFoundInSW.length ? "comparison-good" : "comparison-bad"}">
                    ${ogContextFoundInSW.length}/${swSoftware.length}
                </span>
            </div>
        `;
    }

    const pctColor = pct =>
        pct >= 50 ? "comparison-good" :
        pct >= 20 ? "comparison-mid" :
                    "comparison-bad";

    // Generate lists for expanded section
    const listToHTML = (ids, dict) =>
        ids.length === 0
            ? `<li class="empty">None</li>`
            : ids.map(id => `<li>${dict[id] || id}</li>`).join("");

    // Call the API and wait for the JSON result
    const result = await fetchRatio(ogName, swName);

    // Transform all values to numbers
    const ratioJson = Object.fromEntries(
        Object.entries(result).map(([key, value]) => [key, Math.round(parseFloat(value))])
    );

        // Only show div if the corresponding slider is greater than 0
    const normalDiv = sliders.range1.value > 0
        ? `<div class="comparison-row">
                <span class="label">Normal Ratio:</span>
                <span class="value">${ratioJson.normal_ratio}</span>
           </div>`
        : '';

    const tokenDiv = sliders.range2.value > 0
        ? `<div class="comparison-row">
                <span class="label">Token Ratio:</span>
                <span class="value">${ratioJson.token_ratio}</span>
           </div>`
        : '';

    const partialDiv = sliders.range3.value > 0
        ? `<div class="comparison-row">
                <span class="label">Partial Ratio:</span>
                <span class="value">${ratioJson.partial_ratio}</span>
           </div>`
        : '';

    const ratioHTML = `${normalDiv}${tokenDiv}${partialDiv}`;
    // Now you can access ratioJson.normal_ratio, ratioJson.token_ratio, etc.


    // -----------------------------------------
    // HTML OUTPUT
    // -----------------------------------------
    const toggleId = "cmp-" + Math.random().toString(36).slice(2);

    return `
        <div class="comparison-box">

            <h3>Similarity Score</h3>
            <h3>Software Name Difference</h3>
            
            ${docIDcompare}
            
            <div class="comparison-row">
                <span class="label">Original:</span>
                <span class="value">${nameDiff.og}</span>
            </div>
            <div class="comparison-row">
                <span class="label">Related:</span>
                <span class="value">${nameDiff.sw}</span>
            </div>
            
            ${crossContextSummary}
            
            ${ratioHTML}
            
            <div class="comparison-row">
                <span class="label">Authors in common:</span>
                <span class="value ${pctColor(authorPct)}">
                    ${commonAuthors.length} / ${ogAuthors.length} (${authorPct}%)
                </span>
            </div>

            <div class="comparison-row">
                <span class="label">Structures in common:</span>
                <span class="value ${pctColor(structPct)}">
                    ${commonStruct.length} / ${ogStruct.length} (${structPct}%)
                </span>
            </div>

            <button class="cmp-toggle" onclick="document.getElementById('${toggleId}').classList.toggle('open')">
                Show details ▼
            </button>

            <div id="${toggleId}" class="cmp-details">

                <h4>Authors in common</h4>
                <ul>${listToHTML(commonAuthors, ogAuthorsById)}</ul>

                <h4>Authors ONLY in Original</h4>
                <ul>${listToHTML(diffAuthorsOG, ogAuthorsById)}</ul>

                <h4>Authors ONLY in Related</h4>
                <ul>${listToHTML(diffAuthorsSW, swAuthorsById)}</ul>

                <h4>Structures in common</h4>
                <ul>${listToHTML(commonStruct, ogStructById)}</ul>

                <h4>Structures ONLY in Original</h4>
                <ul>${listToHTML(diffStructOG, ogStructById)}</ul>

                <h4>Structures ONLY in Related</h4>
                <ul>${listToHTML(diffStructSW, swStructById)}</ul>

            </div>
        </div>
    `;
}

/*****************************************
 *  CARD RENDERING
 *****************************************/
async function renderComparisonCards() {
    cardContainer.innerHTML = ""; // Clear old

    const og = state.og;
    if (!og) return;

    for (const [sw, docid] of state.currentList) {

        // ----------------------------------
        // HTML FRAME
        // ----------------------------------
        const card = document.createElement("div");
        card.className = "software-card-dis";

        card.innerHTML = `
            <div class="original-software">
                <strong>Original: ${og.name}</strong>
                <p>Loading...</p>
            </div>

            <div class="result-software">
                <strong>Comparison</strong>
                <p>Loading...</p>
            </div>

            <div class="related-software">
                <strong>${sw}</strong>
                <p>Loading...</p>
            </div>
        `;

        cardContainer.appendChild(card);

        // ----------------------------------
        // FILL CONTENT
        // ----------------------------------
        if (og.docid === docid) {
            if (og.name === sw){
            // Skip identical document → do not display it
            card.remove();     // cleanly remove from DOM
            continue;}          // skip to next element
        }
        const originalDiv = card.querySelector(".original-software");
        const resultDiv = card.querySelector(".result-software");
        const relatedDiv = card.querySelector(".related-software");

        const swJSON = await fetchSoftwareJSON(sw, docid);

        originalDiv.innerHTML = renderJSON(og.json, og.name, og.docid)

        relatedDiv.innerHTML = renderJSON([swJSON], sw, docid)

        resultDiv.innerHTML = await renderComparison(og.json, og.name, [swJSON], sw);
        // resultDiv.innerHTML = renderComparison(og.docid, docid);

        // ----------------------------------
        // CLICK HANDLER FOR “SET AS ORIGINAL”
        // ----------------------------------
        card.addEventListener("click", async (e) => {
            if (e.target.classList.contains("set-og-btn")) {

                const newOG = e.target.getAttribute("data-sw");
                const newDocid = e.target.getAttribute("data-docid");

                await setOriginalSoftware(newOG, newDocid);

                await renderComparisonCards(); // refresh UI
            }
        });
    }
}

/*****************************************
 *  MAIN ENTRYPOINT WHEN USER SELECTS SOFTWARE
 *****************************************/
async function softwareClickHandler(softwareName) {
    try {
        const fuzz = sliders.range1.value;
        const avg = sliders.range2.value;
        const partial = sliders.range3.value;
        const data = await apiGET(`${window.URL_PREFIX}/api/disambiguate/list_dup_software/${softwareName}/${fuzz}/${avg}/${partial}`);
        state.currentList = data.result || [];

        if (state.currentList.length === 0) {
            console.log("No related software found.");
            return;
        }

        if (state.currentList.length === 1) {
            cardContainer.innerHTML = `<div class="result-software"><p>No mention for this software can be disambiguated.</p></div>`
            return;
        }

        // ------------------------------
        // SET DEFAULT ORIGINAL SOFTWARE
        // ------------------------------
        const [ogName, ogDocid] = state.currentList[0];
        await setOriginalSoftware(ogName, ogDocid);

        // ------------------------------
        // RENDER EVERYTHING
        // ------------------------------
        await renderComparisonCards();

    } catch (err) {
        console.error("Error in main handler:", err);
    }
}

/*****************************************
 *  SEARCH LOGIC
 *****************************************/
function search() {
    const input = inputBox.value.trim().toLowerCase();

    if (!input.length) {
        resultBox.innerHTML = "";
        resultBox.style.display = "none";
        return;
    }

    const filtered = state.availableSoftware.filter(name =>
        name.toLowerCase().includes(input)
    );

    const content = filtered
        .map(name => `<div class="mention_search_doc_id" data-name="${name}">${name}</div>`)
        .join('');
    resultBox.style.display = "block";

    resultBox.innerHTML = `<div class="dropdown-content-search">${content}</div>`;
}

/*****************************************
 *  SLIDER LOGIC
 *****************************************/
function initSliders() {
    // Set initial displayed values
    sliders.val1.textContent = sliders.range1.value;
    sliders.val2.textContent = sliders.range2.value;
    sliders.val3.textContent = sliders.range3.value;

    // Update on input
    sliders.range1.oninput = () => {
        sliders.val1.textContent = sliders.range1.value;
        onSliderChange();
    };

    sliders.range2.oninput = () => {
        sliders.val2.textContent = sliders.range2.value;
        onSliderChange();
    };
    sliders.range3.oninput = () => {
        sliders.val3.textContent = sliders.range3.value;
        onSliderChange();
    };
}

/**
 * Called whenever any slider value changes.
 * You can trigger filtering, scoring, API calls, etc.
 */
let sliderTimeout = null;

function onSliderChange() {
    const softwareName = state.og.name;
    if (!softwareName) return;

    clearTimeout(sliderTimeout);
    sliderTimeout = setTimeout(() => {
        softwareClickHandler(softwareName);
    }, 300);
}

/*****************************************
 *  EVENT BINDINGS
 *****************************************/
resultBox.addEventListener("click", function (event) {
    const target = event.target;
    if (target.classList.contains('mention_search_doc_id')) {
        const softwareName = target.getAttribute('data-name');
        inputBox.value = softwareName;
        resultBox.style.display = "none";
        softwareClickHandler(softwareName);
    }
});

inputBox.addEventListener("keyup", search);

document.addEventListener("DOMContentLoaded", () => {
    fetchSoftwareList();
    initSliders();
});



