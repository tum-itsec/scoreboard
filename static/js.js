function toggleDisplay(el) {
  if (el.style.display !== "block") {
    el.style.display = "block";
  } else {
    el.style.display = "none";
  }
}

document.addEventListener("DOMContentLoaded", (ev) => {
	var btn = document.querySelector("#navtoggle button");
	btn.addEventListener("click", (ev) => {
		ev.preventDefault();
		toggleDisplay(document.querySelector("nav"));
	});
});
