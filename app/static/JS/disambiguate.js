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
function renderJSON(obj,sw,docid,showOgButton = true) {
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
                ${showOgButton ? `<button class="set-og-btn" data-sw="${sw}" data-docid="${docid}">
                    Use as Original
                </button>` : ""}
                
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

                <h4>Affiliations:</h4>
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
    // STRUCTURED OUTPUT
    //   - summary fields drive the always-visible candidate header
    //   - detailsHTML fills the collapsible body
    // -----------------------------------------
    const activeRatios = [];
    if (sliders.range1.value > 0) activeRatios.push(ratioJson.normal_ratio);
    if (sliders.range2.value > 0) activeRatios.push(ratioJson.token_ratio);
    if (sliders.range3.value > 0) activeRatios.push(ratioJson.partial_ratio);
    const headlineScore = activeRatios.length ? Math.max(...activeRatios) : null;

    const authorBadge = {
        text: `${commonAuthors.length} / ${ogAuthors.length} (${authorPct}%)`,
        cls: pctColor(authorPct)
    };
    const affilBadge = {
        text: `${commonStruct.length} / ${ogStruct.length} (${structPct}%)`,
        cls: pctColor(structPct)
    };

    const detailsHTML = `
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
            <span class="value ${authorBadge.cls}">${authorBadge.text}</span>
        </div>
        <div class="comparison-row">
            <span class="label">Affiliations in common:</span>
            <span class="value ${affilBadge.cls}">${affilBadge.text}</span>
        </div>

        <h4>Authors in common</h4>
        <ul>${listToHTML(commonAuthors, ogAuthorsById)}</ul>

        <h4>Authors ONLY in Original</h4>
        <ul>${listToHTML(diffAuthorsOG, ogAuthorsById)}</ul>

        <h4>Authors ONLY in Related</h4>
        <ul>${listToHTML(diffAuthorsSW, swAuthorsById)}</ul>

        <h4>Affiliations in common</h4>
        <ul>${listToHTML(commonStruct, ogStructById)}</ul>

        <h4>Affiliations ONLY in Original</h4>
        <ul>${listToHTML(diffStructOG, ogStructById)}</ul>

        <h4>Affiliations ONLY in Related</h4>
        <ul>${listToHTML(diffStructSW, swStructById)}</ul>
    `;

    return { headlineScore, nameDiff, authorBadge, affilBadge, detailsHTML };
}

/*****************************************
 *  CARD RENDERING
 *****************************************/
async function renderComparisonCards() {
    cardContainer.innerHTML = ""; // Clear old

    const og = state.og;
    if (!og) return;

    // ----------------------------------
    // TWO-PANE FRAME: pinned Original (left) + candidate list (right)
    // The Original is rendered ONCE here, not per candidate.
    // ----------------------------------
    const layout = document.createElement("div");
    layout.className = "dis-layout";
    layout.innerHTML = `
        <aside class="dis-original">
            <div class="dis-original-label">Original</div>
            ${renderJSON(og.json, og.name, og.docid, false)}
        </aside>
        <div class="dis-candidate-list"></div>
    `;
    cardContainer.appendChild(layout);

    const list = layout.querySelector(".dis-candidate-list");

    for (const [sw, docid] of state.currentList) {

        // Skip the identical mention (same software, same document)
        if (og.docid === docid && og.name === sw) continue;

        const swJSON = await fetchSoftwareJSON(sw, docid);
        const cmp = await renderComparison(og.json, og.name, [swJSON], sw);

        const scoreChip = cmp.headlineScore != null
            ? `<span class="dis-score">${cmp.headlineScore}%</span>`
            : "";

        const card = document.createElement("div");
        card.className = "dis-candidate";
        card.innerHTML = `
            <button type="button" class="dis-candidate-header">
                <span class="dis-cand-name">${cmp.nameDiff.sw}</span>
                ${scoreChip}
                <span class="dis-metric ${cmp.authorBadge.cls}">auth ${cmp.authorBadge.text}</span>
                <span class="dis-metric ${cmp.affilBadge.cls}">affil ${cmp.affilBadge.text}</span>
                <span class="dis-chevron material-symbols-outlined">expand_more</span>
            </button>
            <div class="dis-candidate-body">
                <div class="comparison-box">${cmp.detailsHTML}</div>
                <div class="related-software">${renderJSON([swJSON], sw, docid)}</div>
            </div>
        `;
        list.appendChild(card);
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

// Delegated handler for the candidate list: expand/collapse + "Use as Original".
// Attached once (not per card) so repeated renders don't stack listeners.
cardContainer.addEventListener("click", async (event) => {
    const header = event.target.closest(".dis-candidate-header");
    if (header) {
        header.closest(".dis-candidate").classList.toggle("open");
        return;
    }

    const ogBtn = event.target.closest(".set-og-btn");
    if (ogBtn) {
        await setOriginalSoftware(ogBtn.getAttribute("data-sw"), ogBtn.getAttribute("data-docid"));
        await renderComparisonCards(); // refresh UI with the new original
    }
});

inputBox.addEventListener("keyup", search);

document.addEventListener("DOMContentLoaded", () => {
    fetchSoftwareList();
    initSliders();
});



