document.addEventListener('DOMContentLoaded', (event) => {

    const url_info = window.location.pathname.split('/').pop();
    const div_block = document.getElementsByClassName("software_canva_info");

    // Ensure div_block is not empty
    if (div_block.length > 0) {
        if (url_info.startsWith('struct-')) {
            fetch(`${window.URL_PREFIX}/api/soft/${url_info}`)
            .then(response => {
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                return response.json();
            })
            .then(data => {
                const title_block = document.createElement('div');
                title_block.className = "titre-block";
                const pathParts = window.location.pathname.split('/');
                const softwareName = decodeURIComponent(pathParts.pop() || '');
                title_block.innerHTML = `<h2 style="padding: 5px">${softwareName}</h2>`;
                // Insert at the top of the div
                div_block[0].insertBefore(title_block, div_block[0].firstChild);
            })
            .catch(error => {
                console.error('Error fetching data:', error);
            });
        } else {
            const title_block = document.createElement('div');
            title_block.className = "titre-block";
            const pathParts = window.location.pathname.split('/');
            const softwareName = decodeURIComponent(pathParts.pop() || '');
            title_block.innerHTML = `<h2 style="padding: 5px">${softwareName}</h2>`;
            // Insert at the top of the div
            div_block[0].insertBefore(title_block, div_block[0].firstChild);
        }
    };

    function setupSoftwareSearch() {
        const resultBox = document.getElementById("result-box-software");
        const inputBox = document.getElementById("input-box-software");
        if (!inputBox || !resultBox) return;

        // Debounce function to delay input handling
        function debounce(func, wait) {
            let timeout;
            return function (...args) {
                clearTimeout(timeout);
                timeout = setTimeout(() => func.apply(this, args), wait);
            };
        }

        function displayResult(results) {
            const content = results.map(keyword =>
                `<div class='mention_search_doc_id' id="${keyword}">${keyword}</div>`
            ).join('');
            resultBox.style.display = results.length ? 'block' : 'none';
            resultBox.innerHTML = `<div class='dropdown-content-search'>${content}</div>`;

            // Add event listeners for new result items
            document.querySelectorAll('.mention_search_doc_id').forEach(item => {
                item.addEventListener('click', function () {
                    const idValue = this.getAttribute('id');
                    handleClick(idValue);
                    resultBox.style.display = 'none';
                    resultBox.innerHTML = ""; // Clear results
                });
            });
        }

        // Query the Elasticsearch-backed prefix endpoint instead of downloading the full
        // software list (~519 KB) and filtering in the browser.
        async function searchSoftware(query) {
            try {
                const response = await fetch(`${window.URL_PREFIX}/api/search_software?q=${encodeURIComponent(query)}`, { method: "GET" });
                if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
                const results = await response.json();
                displayResult(results.map(r => r.name));
            } catch (error) {
                console.error('Error searching software:', error);
            }
        }

        inputBox.onkeyup = debounce(function () {
            const input = inputBox.value.trim();
            if (input.length) {
                searchSoftware(input);
            } else {
                resultBox.style.display = 'none';
                resultBox.innerHTML = "";
            }
        }, 300); // Debounce delay of 300ms
    }

    // Call the setup function on page load
    setupSoftwareSearch();

    function handleClick(softwareName) {
    // Navigate to a new URL, passing the software name as part of the path or query string
    const url = `${window.URL_PREFIX}/software_stat/${softwareName}`;
    window.location.href = url;
}



});
