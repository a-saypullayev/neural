(function () {
  const { api, esc, toast } = Neural;
  const $ = (id) => document.getElementById(id);
  let chatId = null, busy = false;

  /* Safe mini-markdown: escape first, then format code blocks, inline code and bold. */
  function md(text) {
    let h = esc(text);
    h = h.replace(/```(?:[\w+-]*)\n?([\s\S]*?)```/g, (_, c) => "<pre><code>" + c.replace(/\n$/, "") + "</code></pre>");
    h = h.replace(/`([^`\n]+)`/g, "<code>$1</code>").replace(/\*\*([^*\n]+)\*\*/g, "<strong>$1</strong>");
    return h.replace(/\n/g, "<br>").replace(/<pre><code>([\s\S]*?)<\/code><\/pre>/g, (m) => m.replace(/<br>/g, "\n"));
  }

  function addMsg(role, text) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + (role === "user" ? "user" : "ai");
    wrap.innerHTML = '<div class="avatar">' + (role === "user" ? "You".slice(0, 1) : "N") + '</div><div class="bubble"></div>';
    const b = wrap.querySelector(".bubble");
    if (role === "user") b.textContent = text; else b.innerHTML = md(text);
    $("msgsInner").appendChild(wrap);
    scroll();
    return b;
  }
  function scroll() { const m = $("msgs"); m.scrollTop = m.scrollHeight; }

  function showEmpty() {
    $("msgsInner").innerHTML = '<div class="empty"><span class="logo" style="width:52px;height:52px;margin:auto"><svg viewBox="0 0 64 64" style="width:30px"><path d="M18 46V18h6l16 20V18h6v28h-6L24 26v20z" fill="#fff"/></svg></span><h1>What are we working on?</h1><p class="muted">Your chats and memories are private to your account.</p></div>';
  }

  async function loadChats() {
    const { chats } = await api("/api/chats");
    const list = $("chatList");
    list.innerHTML = "";
    chats.forEach((c) => {
      const row = document.createElement("div");
      row.className = "chat-item" + (c.id === chatId ? " on" : "");
      row.innerHTML = "<span></span><button title=\"Delete chat\" aria-label=\"Delete chat\">✕</button>";
      row.querySelector("span").textContent = c.title;
      row.onclick = () => openChat(c.id);
      row.querySelector("button").onclick = async (e) => {
        e.stopPropagation();
        if (!confirm("Delete this chat?")) return;
        await api("/api/chats/" + c.id, { method: "DELETE" });
        if (chatId === c.id) newChat();
        loadChats();
      };
      list.appendChild(row);
    });
  }

  async function openChat(id) {
    const c = await api("/api/chats/" + id);
    chatId = id;
    $("msgsInner").innerHTML = "";
    c.messages.forEach((m) => addMsg(m.role, m.content));
    $("side").classList.remove("open");
    loadChats();
  }

  function newChat() { chatId = null; showEmpty(); $("side").classList.remove("open"); loadChats(); }

  function setUsage(u) {
    if (!u) return;
    $("usageText").textContent = u.requests + " / " + u.request_limit + " requests today";
    $("usageBar").style.width = Math.min(100, (u.requests / u.request_limit) * 100) + "%";
  }

  async function send() {
    const input = $("input"), text = input.value.trim();
    if (!text || busy) return;
    busy = true; $("send").disabled = true; input.value = ""; input.style.height = "auto";
    if (!chatId) $("msgsInner").innerHTML = "";
    addMsg("user", text);
    const bubble = addMsg("ai", "");
    bubble.innerHTML = '<span class="dots"><span></span><span></span><span></span></span>';
    let acc = "";
    try {
      const res = await api("/api/chat", { method: "POST", raw: true, body: { message: text, chat_id: chatId, search: $("searchToggle").checked } });
      if (!res.ok) {
        let msg = "Something went wrong."; try { msg = (await res.json()).error.message; } catch (e) {}
        bubble.textContent = msg; bubble.style.color = "var(--danger)";
      } else {
        const reader = res.body.getReader(), dec = new TextDecoder();
        let buf = "";
        for (;;) {
          const { value, done } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          let i;
          while ((i = buf.indexOf("\n")) >= 0) {
            const line = buf.slice(0, i).trim(); buf = buf.slice(i + 1);
            if (!line) continue;
            const ev = JSON.parse(line);
            if (ev.type === "meta") chatId = ev.chat_id;
            else if (ev.type === "delta") { acc += ev.text; bubble.innerHTML = md(acc); scroll(); }
            else if (ev.type === "error") { bubble.innerHTML = md(acc) + '<p style="color:var(--danger)">' + esc(ev.message) + "</p>"; }
          }
        }
        if (!acc && !bubble.textContent.trim()) bubble.textContent = "(No response)";
      }
    } catch (e) { bubble.textContent = e.message; bubble.style.color = "var(--danger)"; }
    busy = false; $("send").disabled = false; input.focus();
    loadChats();
    Neural.me().then((m) => setUsage(m.usage));
  }

  function memoryModal() {
    const ov = document.createElement("div");
    ov.className = "overlay";
    ov.innerHTML = '<div class="card modal"><h2 style="margin-top:0">Memories</h2><p class="muted">Facts Neural should remember about you in every chat. Only you can see them.</p><div id="memList"></div>' +
      '<div class="row" style="margin-top:14px"><input class="input" id="memIn" maxlength="300" placeholder="e.g. I prefer short answers"><button class="btn" id="memAdd">Add</button></div><div class="err" id="memErr"></div>' +
      '<div style="text-align:right;margin-top:8px"><button class="btn ghost" id="memClose">Close</button></div></div>';
    document.body.appendChild(ov);
    const render = async () => {
      const { memories } = await api("/api/memories");
      const l = ov.querySelector("#memList"); l.innerHTML = "";
      if (!memories.length) l.innerHTML = '<p class="muted">No memories yet.</p>';
      memories.forEach((m) => {
        const r = document.createElement("div"); r.className = "mem";
        r.innerHTML = "<span></span><button class=\"btn danger sm\">Delete</button>";
        r.querySelector("span").textContent = m.content;
        r.querySelector("button").onclick = async () => { await api("/api/memories/" + m.id, { method: "DELETE" }); render(); };
        l.appendChild(r);
      });
    };
    ov.querySelector("#memAdd").onclick = async () => {
      const inp = ov.querySelector("#memIn"), err = ov.querySelector("#memErr"); err.textContent = "";
      try { await api("/api/memories", { method: "POST", body: { content: inp.value } }); inp.value = ""; render(); }
      catch (e) { err.textContent = e.message; }
    };
    ov.querySelector("#memClose").onclick = () => ov.remove();
    render();
  }

  async function start() {
    const m0 = await Neural.me();
    Neural.mountNav("/", m0);
    const nav = document.querySelector(".nav");
    const mb = document.createElement("button");
    mb.className = "btn ghost sm menu-btn"; mb.textContent = "☰"; mb.setAttribute("aria-label", "Toggle chat list");
    mb.onclick = () => $("side").classList.toggle("open");
    nav.prepend(mb);
    const m = await Neural.gate();
    Neural.renderNavUser(m);
    $("app").hidden = false;
    setUsage(m.usage);
    showEmpty(); loadChats();
    $("newChat").onclick = newChat;
    $("memBtn").onclick = memoryModal;
    $("send").onclick = send;
    const input = $("input");
    input.addEventListener("keydown", (e) => { if (e.key === "Enter" && !e.shiftKey) { e.preventDefault(); send(); } });
    input.addEventListener("input", () => { input.style.height = "auto"; input.style.height = Math.min(input.scrollHeight, 200) + "px"; });
    input.focus();
  }
  start();
})();
