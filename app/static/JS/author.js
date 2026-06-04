document.addEventListener('DOMContentLoaded', async () => {

    const authorBox = document.getElementById("author-box");

    function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
  }

  function affi_type(str) {
    const typeMap = {
      "department": "Department",
      "institution": "Institution",
      "laboratory": "Laboratory",
      "regroupinstitution": "Regroup Institution",
      "regrouplaboratory": "Regroup Laboratory",
      "researchteam": "Research Team"
    };
    return typeMap[str] || str;
  }

  async function displayAuthorDetails(auth_id) {
    try {
      const response = await fetch(`/software/api/author/${auth_id}`, { method: "GET" });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const auth_info = await response.json();
      console.log(auth_info[0]);
      const soft_info = auth_info[0].software_names;

      const authorCard = document.createElement('div');
      authorCard.classList.add('author_card');
      authorCard.id = auth_id;

      let documentsList = '<ul>';
      auth_info[0].author.documents.forEach(dict_doc => {
        documentsList += `<li class="${dict_doc.role}"><a href="/software/doc/${dict_doc.document_halid}">${dict_doc.document_halid}</a></li>`;
      });
      documentsList += '</ul>';

      let affiList = '<ul>';
      auth_info[0].structures.forEach(affi => {
        const affi_type_cleaned = affi_type(affi.struc.type);
        let affi_card = affi.struc.acronym
          ? `<h4>${affi.struc.acronym} (${affi_type_cleaned})</h4>`
          : `<h4>${affi_type_cleaned}</h4>`;
        if (affi.struc.status) {
          affi_card += `<p class="status">Status: <span class="${affi.struc.status}">${affi.struc.status}</span></p>`;
        }
        affi_card += affi.struc.url_team
          ? `<p>${affi.struc.name} (<a href='${affi.struc.url_team}'>url</a>)</p>`
          : `<p>${affi.struc.name}</p>`;
        affi_card += `<p>AureHAL ID: <a href='https://aurehal.archives-ouvertes.fr/structure/read/id/${affi.struc.id_haureal.replace('struct-','')}'>${affi.struc.id_haureal.replace('struct-','')}</a></p>`;
        affiList += `<li>${affi_card}</li>`;
      });
      affiList += '</ul>';

      let software_list = '<ul>';
      soft_info.forEach(soft_list => {
        let statusText;

        if (soft_list[2] === true) {
          statusText = '<span id="accepted_by_the_author"><strong>Verified by Author</strong></span>';
        } else if (soft_list[2] === false) {
          statusText = '<span id="rejected_by_the_author"><strong>Rejected by Author</strong></span>';
        } else if (soft_list[2] === null) {
          statusText = ''; // No status for null
        } else {
          statusText = '<span class="unexpected_value">Unexpected value</span>';
        }

        software_list += `
          <li>
            <a href="/software/doc/${soft_list[1]}/${soft_list[0]}">${soft_list[0]}</a>
            (${soft_list[1]}) ${statusText}
          </li>`;
      });

      software_list += '</ul>';


      authorCard.innerHTML = `
        <h2>${auth_info[0].author.name.surname} ${auth_info[0].author.name.forename}</h2>
        <p>Hal ID: ${auth_info[0].author.id.halauthorid}</p>
        <p>Documents: ${documentsList}</p>
      `;

      if (auth_info[0].structures.length > 0) {
        authorCard.innerHTML += `<p>Affiliations: ${affiList}</p>`;
      } else {
        authorCard.innerHTML += `<p>We found no affiliations for this author</p>`;
      }

      if (soft_info.length > 0) {
        authorCard.innerHTML += `<p>Softwares: ${software_list}</p>`;
      } else {
        authorCard.innerHTML += `<p>No softwares associated with this author</p>`;
      }

      authorBox.prepend(authorCard);

    } catch (error) {
      console.error('Error fetching the author details:', error);
    }
  }

  const resultBox = document.getElementById("result-box-dis");
  const inputBox = document.getElementById("input-box-dis");

  // Collapse rapid keystrokes into a single request.
  function debounce(fn, delay = 200) {
    let timer;
    return (...args) => {
      clearTimeout(timer);
      timer = setTimeout(() => fn(...args), delay);
    };
  }

  // Query the Elasticsearch-backed prefix endpoint instead of downloading every author
  // (the full /api/author/list_authors payload is ~9.5 MB over 750k authors).
  async function searchAuthors(query) {
    if (!query.length) {
      resultBox.innerHTML = "";
      resultBox.style.display = 'none';
      return;
    }
    try {
      const response = await fetch(`/software/api/search_author?q=${encodeURIComponent(query)}`, { method: "GET" });
      if (!response.ok) throw new Error(`HTTP error! status: ${response.status}`);
      const results = await response.json();

      const content = results.map(a => {
        const name = `${a.last_name || ''} ${a.first_name || ''}`.trim();
        return `<div class='mention_search_auth_id' id="${a.author_id}">${name}</div>`;
      }).join('');

      resultBox.innerHTML = `<div class='dropdown-content-search'>${content}</div>`;
      resultBox.style.height = '150px';
      resultBox.style.overflowY = 'scroll';
      resultBox.style.display = 'block';
    } catch (error) {
      console.error('Error searching authors:', error);
    }
  }

  inputBox.onkeyup = debounce(() => searchAuthors(inputBox.value), 200);

  resultBox.addEventListener('click', function (event) {
    if (event.target && event.target.classList.contains('mention_search_auth_id')) {
      resultBox.style.display = 'none';
      const auth_id = event.target.id;
      displayAuthorDetails(auth_id);
    }
  });

  // Check URL param and display author details automatically if present
  const authorId = getQueryParam('author-id');
  if (authorId) {
    displayAuthorDetails(authorId);
  }

});
