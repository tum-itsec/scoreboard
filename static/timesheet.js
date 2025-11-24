let new_row = document.querySelector("#new-row");
let sum_row = document.querySelector("#sum-row");
let tasks_list = document.querySelector("#tasks");
let errmsg = document.querySelector("#errmsg");

const addTaskBtn = document.getElementById("add-task-btn");
const adminMode = addTaskBtn == null;
if(!adminMode)
    addTaskBtn.addEventListener('click', () => addTask(addTaskBtn));

async function addTask(elm) {
	let inputs = elm.closest("tr").querySelectorAll("input");
	let select = elm.closest("tr").querySelector("select");
	let [start_date, start, end, desc] = inputs;

	let record = {
		start: start_date.value + " " + start.value,
		end: start_date.value + " " + end.value,
		notes: desc.value,
		tasktype_id: select.value
	};
	const resp = await fetch("./api", { method: "POST", body: JSON.stringify(record) } );
	const resp_json = await resp.json();
	if(resp_json.type == "error") {
		errmsg.innerHTML = "<b>Error:</b> " + resp_json.message;
		errmsg.style.display = "table-cell";
	} else {
		errmsg.innerHTML = "";
		errmsg.style.display = "none";
		console.log(resp);
		fillRows(resp_json);
	}
}

function deleteTask(elm) {
	let tr = elm.closest("tr");
	console.log(tr.dataset.id);
	fetch(`./api/${tr.dataset.id}`, { method: "DELETE" }).then((resp) => tr.remove());
}

function approveTask(elm) {
	let tr = elm.closest("tr");
	let d = {approved: !tr.classList.contains("approved")};
	let btnValues = {
		true: "Approved",
		false: "Approve"
	}
	fetch(`./api/${tr.dataset.id}`, { method: "PUT", body: JSON.stringify(d) })
		.then(resp => {
			console.log(resp);
			if(resp.ok) {
				elm.innerText = btnValues[d.approved];
				tr.classList.toggle("approved");
			} else {
				alert("Server Error on approval!");
			}
	});
}

function fillRows(recs) {
	tasks_list.innerHTML = "";
	let curweek = 0;
	recs.records.forEach(r => {
		if(curweek != r.week) {
			let srow = sum_row.content.firstElementChild.cloneNode(true);
			srow.querySelector("b").innerText = `Sum for week ${r.week}: ${recs.aggregates[r.week]}h`;
			tasks_list.appendChild(srow);
		}
		let [start_date, start] = r.start.split(" ");
		r.start_date = start_date;
		r.start = start;
		r.end = r.end.split(" ")[1];
		let s = new_row.content.firstElementChild.cloneNode(true);
		s.dataset["id"] = r.timerecord_id;
		let btn = s.querySelector("button");
		if(r.approved == 1) {
			s.classList.add("approved");
			btn.innerText = adminMode ? "Approved" : "Already approved - can't delete";
		}
		if(adminMode)
			btn.addEventListener('click', () => approveTask(btn));
		else if(r.approved == 0)
			btn.addEventListener('click', () => deleteTask(btn));
		s.querySelectorAll("[data-bind]").forEach( e => e.innerText = r[e.dataset["bind"]]);
		tasks_list.appendChild(s);
		curweek = r.week;
	});
}

fetch("./api").then(resp => resp.json()).then(j => fillRows(j));
