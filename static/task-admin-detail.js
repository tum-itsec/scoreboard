const debounce = (context, func, delay) => {
	let timeout;
	return (...arguments) => {
		if (timeout) {
			clearTimeout(timeout);
		}
		timeout = setTimeout(() => {
			func.apply(context, arguments);
		}, delay);
	};
};

function renderMarkdown() {
	fetch("/taskadmin/rendermd", { method: "POST", body: md.value }).then((r) => r.text()).then((r) => c.innerHTML = r);
}

let md = document.querySelector("#markdownedit textarea");
let c = document.querySelector("#markdownedit div");
console.log("test");
md.addEventListener("input", debounce(this, (e) => {
	renderMarkdown();
}, 1000));
renderMarkdown();
