var teamname = document.getElementById("teamname");
var form = document.getElementById("change-teamname-form");
teamname.querySelector("a").addEventListener("click", (elm) => {
	form.style.display = "block";
	teamname.style.display = "none";
});
