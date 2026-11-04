(function () {
  const { api, esc, toast } = Neural;
  const $ = (id) => document.getElementById(id);
  const fmt = (t) => (t ? new Date(t * 1000).toLocaleString() : "Never");

  async function load() {
    const { keys } = await api("/api/keys");
    const rows = $("rows"); rows.innerHTML = "";
    $("empty").hidden = keys.length > 0;
    keys.forEach((k) => {
      const tr = document.createElement("tr");
      tr.innerHTML = "<td></td><td><code>" + esc(k.prefix) + "…</code></td><td>" + esc(fmt(k.created_at)) + "</td><td>" + esc(fmt(k.last_used_at)) +
        "</td><td>" + (k.revoked ? "–" : esc(k.tokens_used.toLocaleString() + " / " + k.token_limit.toLocaleString())) +
        '</td><td><span class="pill' + (k.revoked ? " off" : "") + '">' + (k.revoked ? "Revoked" : "Active") + "</span></td><td></td>";
      tr.children[0].textContent = k.name;
      if (!k.revoked) {
        const b = document.createElement("button");
        b.className = "btn danger sm"; b.textContent = "Revoke";
        b.onclick = async () => {
          if (!confirm('Revoke "' + k.name + '"? Apps using it will stop working immediately.')) return;
          try { await api("/api/keys/" + k.id, { method: "DELETE" }); toast("Key revoked."); load(); } catch (e) { toast(e.message, true); }
        };
        tr.children[6].appendChild(b);
      }
      rows.appendChild(tr);
    });
  }

  function showSecret(secret) {
    const box = $("secretBox");
    box.innerHTML = '<div class="secret"><strong>Copy your new key now.</strong><span class="muted"> You will not be able to see it again.</span><code></code><button class="btn sm" id="copyBtn">Copy key</button> <button class="btn ghost sm" id="hideBtn">I have saved it</button></div>';
    box.querySelector("code").textContent = secret;
    $("copyBtn").onclick = async () => {
      try { await navigator.clipboard.writeText(secret); toast("Copied to clipboard."); }
      catch (e) { const r = document.createRange(); r.selectNodeContents(box.querySelector("code")); const s = getSelection(); s.removeAllRanges(); s.addRange(r); toast("Press Ctrl+C to copy.", true); }
    };
    $("hideBtn").onclick = () => (box.innerHTML = "");
  }

  async function start() {
    const m0 = await Neural.me();
    Neural.mountNav("/keys", m0);
    const m = await Neural.gate();
    Neural.renderNavUser(m);
    $("page").hidden = false;
    $("createForm").onsubmit = async (e) => {
      e.preventDefault();
      $("err").textContent = ""; $("createBtn").disabled = true;
      try {
        const r = await api("/api/keys", { method: "POST", body: { name: $("keyName").value } });
        $("keyName").value = ""; showSecret(r.secret); load();
      } catch (er) { $("err").textContent = er.message; }
      $("createBtn").disabled = false;
    };
    load();
  }
  start();
})();
