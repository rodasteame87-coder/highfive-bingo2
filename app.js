/* Highfive Bingo Mini App
   The browser never receives your Telegram bot token.
   It talks to server.py through /api/*.
*/

const tg = window.Telegram?.WebApp;
const API_BASE = ""; // same origin; change only if your API is on another HTTPS host.

const state = {
  user: null,
  joined: false,
  card: null,
  marked: new Set(),
  called: [],
  running: false,
  poll: null
};

const $ = (id) => document.getElementById(id);

function telegramInit() {
  if (!tg) {
    $("playerName").textContent = "Preview mode (open from Telegram for real user data)";
    return;
  }
  tg.ready();
  tg.expand();
  const u = tg.initDataUnsafe?.user;
  state.user = u || null;
  $("playerName").textContent = u
    ? `Player: ${u.first_name || ""}${u.last_name ? " " + u.last_name : ""}`.trim()
    : "Telegram player";
}

function headers() {
  const h = {"Content-Type": "application/json"};
  if (tg?.initData) h["X-Telegram-Init-Data"] = tg.initData;
  return h;
}

async function api(path, options = {}) {
  const res = await fetch(API_BASE + path, {
    ...options,
    headers: {...headers(), ...(options.headers || {})}
  });
  let data = {};
  try { data = await res.json(); } catch (_) {}
  if (!res.ok) throw new Error(data.error || `Server error ${res.status}`);
  return data;
}

function letter(n) {
  if (n <= 15) return "B";
  if (n <= 30) return "I";
  if (n <= 45) return "N";
  if (n <= 60) return "G";
  return "O";
}

function renderCard() {
  const root = $("card");
  root.innerHTML = "";
  if (!state.card) {
    for (let i = 0; i < 25; i++) {
      const d = document.createElement("div");
      d.className = "cell";
      d.textContent = "–";
      root.appendChild(d);
    }
    return;
  }

  state.card.forEach((n, i) => {
    const d = document.createElement("div");
    const free = i === 12;
    const marked = free || state.marked.has(n);
    d.className = `cell${free ? " free" : ""}${marked && !free ? " marked" : ""}`;
    d.textContent = free ? "FREE" : (marked ? "✕" : n);
    root.appendChild(d);
  });
}

function renderNumbers() {
  const root = $("numbers");
  root.innerHTML = "";
  state.called.forEach((n, i) => {
    const d = document.createElement("span");
    d.className = `num${i === state.called.length - 1 ? " latest" : ""}`;
    d.textContent = `${letter(n)}-${n}`;
    root.appendChild(d);
  });
  $("count").textContent = `${state.called.length}/75`;
  const latest = state.called.at(-1);
  $("calledLetter").textContent = latest ? letter(latest) : "–";
  $("calledNumber").textContent = latest ?? "–";
}

function render() {
  renderCard();
  renderNumbers();
  $("statusPill").textContent = state.running ? "LIVE" : "WAITING";
  $("statusPill").classList.toggle("live", state.running);
  $("joinBtn").textContent = state.joined ? "Joined ✓" : "Join game";
  $("joinBtn").disabled = state.joined;
  $("bingoBtn").disabled = !state.joined || !state.running;
  $("cardStatus").textContent = state.joined ? "Card active" : "Not joined";
}

async function sync() {
  try {
    const data = await api("/api/state");
    state.running = !!data.running;
    state.called = Array.isArray(data.called) ? data.called : [];
    if (data.card) {
      state.card = data.card;
      state.joined = true;
      state.marked = new Set(data.marked || []);
    }
    $("gameTitle").textContent = data.title || "Highfive Bingo";
    $("gameMessage").textContent = data.message || "Join the game to receive a card.";
    render();
  } catch (e) {
    $("notice").textContent = `Connection: ${e.message}`;
    $("notice").className = "notice bad";
  }
}

async function joinGame() {
  try {
    $("joinBtn").disabled = true;
    const data = await api("/api/join", {method: "POST", body: "{}"});
    state.joined = true;
    state.card = data.card;
    state.marked = new Set([0]); // only used for UI bookkeeping; FREE is index 12.
    state.marked.delete(0);
    $("notice").textContent = "You're in! Your card is ready.";
    $("notice").className = "notice good";
    render();
    await sync();
  } catch (e) {
    $("joinBtn").disabled = false;
    $("notice").textContent = e.message;
    $("notice").className = "notice bad";
  }
}

async function claimBingo() {
  try {
    const data = await api("/api/claim", {method: "POST", body: "{}"});
    $("notice").textContent = data.message || "BINGO submitted!";
    $("notice").className = data.ok ? "notice good" : "notice bad";
    if (tg?.HapticFeedback) tg.HapticFeedback.notificationOccurred(data.ok ? "success" : "error");
  } catch (e) {
    $("notice").textContent = e.message;
    $("notice").className = "notice bad";
  }
}

$("joinBtn").addEventListener("click", joinGame);
$("bingoBtn").addEventListener("click", claimBingo);

telegramInit();
render();
sync();
state.poll = setInterval(sync, 2500);
