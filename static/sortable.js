// Adpated from https://stackoverflow.com/questions/14267781/sorting-html-table-with-javascript

const getCellValue = (tr, idx) => tr.children[idx].innerText || tr.children[idx].textContent;

const comparer = (idx, asc) => (a, b) => ((v1, v2) => 
    v1 !== '' && v2 !== '' && !isNaN(v1) && !isNaN(v2) ? v1 - v2 : v1.toString().localeCompare(v2)
    )(getCellValue(asc ? a : b, idx), getCellValue(asc ? b : a, idx));

const has_no_th_cells = (tr) => ! tr.querySelector("th");

// do the work...
document.querySelectorAll("table.sortable").forEach(table => table.querySelectorAll('th').forEach(th => th.addEventListener('click', ((ev) => {
    const table = th.closest('table');
    const indexToSort = Array.from(th.parentNode.children).indexOf(th);
    let rows_to_sort = Array.from(table.querySelectorAll('tr:nth-child(n+2)'))
        .filter(has_no_th_cells); // Support for multiple headings at start of a table
    rows_to_sort.sort(comparer(indexToSort, this.asc = !this.asc)).forEach(tr => table.appendChild(tr) );
    ev.preventDefault();
}))));
