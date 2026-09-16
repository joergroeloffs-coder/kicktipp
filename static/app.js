const tbody = document.querySelector("#matches tbody");
const statusEl = document.querySelector("#status");
const submitBtn = document.querySelector("#submit");
const reloadBtn = document.querySelector("#reload");

let currentMatches = [];

async function loadMatches() {
  statusEl.style.display = "none";
  tbody.innerHTML = "<tr><td colspan='5'>Lade...</td></tr>";
  const resp = await fetch("/api/matches");
  const data = await resp.json();

  if (data.error) {
    tbody.innerHTML = `<tr><td colspan='5'>Fehler: ${data.error}</td></tr>`;
    return;
  }
  currentMatches = data;

  if (!currentMatches.length) {
    tbody.innerHTML = "<tr><td colspan='5'>Keine Spiele auf der Kicktipp-Tippabgabe-Seite gefunden.</td></tr>";
    return;
  }

  tbody.innerHTML = "";
  currentMatches.forEach((m, idx) => {
    const tr = document.createElement("tr");
    if (m.already_tipped) tr.classList.add("already-tipped");
    tr.innerHTML = `
      <td>${m.home_team}${m.already_tipped ? ' <span class="tag">bereits getippt</span>' : ""}</td>
      <td class="form-hint">${m.home_form.goals_scored_avg} / ${m.home_form.goals_conceded_avg}</td>
      <td>
        <input type="number" min="0" data-idx="${idx}" data-side="home" value="${m.predicted_home_goals}">
        :
        <input type="number" min="0" data-idx="${idx}" data-side="away" value="${m.predicted_away_goals}">
      </td>
      <td class="form-hint">${m.away_form.goals_scored_avg} / ${m.away_form.goals_conceded_avg}</td>
      <td>${m.away_team}</td>
    `;
    tbody.appendChild(tr);
  });
}

function collectTips() {
  return currentMatches.map((m, idx) => {
    const homeInput = document.querySelector(`input[data-idx="${idx}"][data-side="home"]`);
    const awayInput = document.querySelector(`input[data-idx="${idx}"][data-side="away"]`);
    return {
      home_team: m.home_team,
      away_team: m.away_team,
      home_goals: parseInt(homeInput.value, 10),
      away_goals: parseInt(awayInput.value, 10),
    };
  });
}

async function submitTips() {
  if (!currentMatches.length) return;
  submitBtn.disabled = true;
  statusEl.style.display = "block";
  statusEl.textContent = "Sende Tipps an Kicktipp...";

  try {
    const resp = await fetch("/api/submit", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(collectTips()),
    });
    const data = await resp.json();
    if (data.error) {
      statusEl.textContent = "Fehler: " + data.error;
    } else {
      statusEl.textContent = data.messages.join("\n");
    }
  } catch (e) {
    statusEl.textContent = "Fehler: " + e;
  } finally {
    submitBtn.disabled = false;
  }
}

reloadBtn.addEventListener("click", loadMatches);
submitBtn.addEventListener("click", submitTips);

loadMatches();
