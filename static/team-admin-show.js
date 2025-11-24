const df = document.getElementById("team-delete-form");
df.addEventListener('submit', (e) => {
	if(!confirm(df.attributes["data-msg"].textContent))
		e.preventDefault();
});
