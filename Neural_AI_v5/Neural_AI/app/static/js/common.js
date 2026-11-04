/* Shared helpers: API calls, toasts, nav bar, and the sign-in / email-verification gate. */
(function () {
  const LOGO = '<svg viewBox="0 0 64 64"><path d="M18 46V18h6l16 20V18h6v28h-6L24 26v20z" fill="#fff"/></svg>';

  function esc(s) {
    return String(s).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  }

  async function api(path, opts) {
    opts = opts || {};
    const init = { method: opts.method || "GET", credentials: "same-origin", headers: {} };
    if (opts.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(opts.body);
    }
    let res;
    try { res = await fetch(path, init); }
    catch (e) { throw new Error("Network error. Check your connection."); }
    if (opts.raw) return res;
    let data = {};
    try { data = await res.json(); } catch (e) { /* empty body */ }
    if (!res.ok) {
      const err = new Error((data.error && data.error.message) || "Something went wrong.");
      err.status = res.status; err.code = data.error && data.error.code;
      throw err;
    }
    return data;
  }

  function toast(msg, bad) {
    const t = document.createElement("div");
    t.className = "toast" + (bad ? " bad" : "");
    t.textContent = msg;
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  function mountNav(active, me) {
    const links = [["/", "Chat"], ["/keys", "API keys"], ["/doc", "Docs"], ["/policy", "Policy"]];
    const nav = document.createElement("nav");
    nav.className = "nav";
    nav.innerHTML =
      '<a class="brand" href="/"><span class="logo">' + LOGO + "</span>Neural AI</a>" +
      '<div class="nav-links">' + links.map((l) => '<a href="' + l[0] + '"' + (l[0] === active ? ' class="active"' : "") + ">" + l[1] + "</a>").join("") + "</div>" +
      '<a class="btn ghost sm nav-app" href="/download">Get the app</a>' +
      '<div class="nav-user" id="navUser"></div>';
    document.body.prepend(nav);
    renderNavUser(me);
  }

  function renderNavUser(me) {
    const el = document.getElementById("navUser");
    if (!el) return;
    if (me && me.user) {
      el.innerHTML = '<span class="who">' + esc(me.user.name) + '</span><button class="btn ghost sm" id="logoutBtn">Sign out</button>';
      document.getElementById("logoutBtn").onclick = async () => { await api("/api/auth/logout", { method: "POST" }); location.href = "/"; };
    } else {
      el.innerHTML = '<button class="btn sm" id="loginBtn">Sign in</button>';
      document.getElementById("loginBtn").onclick = () => gate({ force: true });
    }
  }

  let currentMe = null;
  async function me() {
    currentMe = await api("/api/auth/me");
    return currentMe;
  }

  /* Resolves with the user once signed in. */
  function gate(opts) {
    opts = opts || {};
    return new Promise(async (resolve) => {
      const m = currentMe || (await me());
      if (m.user) return resolve(m);
      const ov = document.createElement("div");
      ov.className = "overlay";
      document.body.appendChild(ov);
      let mode = "login";

      const done = async () => { ov.remove(); const mm = await me(); renderNavUser(mm); resolve(mm); };

      function head(title, sub) {
        return '<span class="logo" style="width:40px;height:40px">' + LOGO + "</span><h2>" + title + "</h2><p>" + sub + "</p>";
      }

      function renderAuth() {
        const reg = mode === "register";
        ov.innerHTML = '<form class="card auth" id="authForm" novalidate>' + head("Welcome to Neural AI", "Private chat, memories and an API for your own apps.") +
          '<div class="tabs"><button type="button" data-m="login" class="' + (reg ? "" : "on") + '">Sign in</button><button type="button" data-m="register" class="' + (reg ? "on" : "") + '">Create account</button></div>' +
          '<div class="field"><label for="e">Username' + (reg ? " (3-30 letters, numbers, . _ -)" : "") + '</label><input class="input" id="e" autocomplete="username" autocapitalize="none" spellcheck="false" maxlength="30"></div>' +
          '<div class="field"><label for="p">Password' + (reg ? " (min 8 characters)" : "") + '</label><input class="input" id="p" type="password" autocomplete="' + (reg ? "new-password" : "current-password") + '"></div>' +
          '<div class="err" id="err" role="alert"></div><button class="btn" style="width:100%" id="go">' + (reg ? "Create account" : "Sign in") + "</button></form>";
        ov.querySelectorAll(".tabs button").forEach((b) => (b.onclick = () => { mode = b.dataset.m; renderAuth(); }));
        ov.querySelector("#authForm").onsubmit = async (ev) => {
          ev.preventDefault();
          const err = ov.querySelector("#err"), go = ov.querySelector("#go");
          err.textContent = ""; go.disabled = true;
          try {
            const body = { username: ov.querySelector("#e").value, password: ov.querySelector("#p").value };
            await api(reg ? "/api/auth/register" : "/api/auth/login", { method: "POST", body });
            return done();
          } catch (e) { err.textContent = e.message; go.disabled = false; }
        };
        const first = ov.querySelector("input"); if (first) first.focus();
      }

      renderAuth();
    });
  }

  window.Neural = { api, toast, esc, mountNav, gate, me, renderNavUser, LOGO };
})();
