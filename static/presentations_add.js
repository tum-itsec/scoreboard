const choices = JSON.parse(document.getElementById("autocomplete-teams").text);
document.querySelectorAll("#add-presentation div.autocomplete").forEach((elm) => {console.log(elm); autocomplete(elm, choices)});
