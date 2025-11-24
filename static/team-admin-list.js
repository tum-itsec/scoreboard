const choices = JSON.parse(document.getElementById("autocomplete-users").text);
document.querySelectorAll("#create-team div.autocomplete").forEach((elm) => {console.log(elm); autocomplete(elm, choices)});
