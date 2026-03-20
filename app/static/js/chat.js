(function () {
  const messagesEl = document.getElementById("chat-messages");
  const inputEl = document.getElementById("chat-input");
  const sendEl = document.getElementById("chat-send");
  const sourcesEl = document.getElementById("chat-sources");

  const filterDocumentTypeEl = document.getElementById("filter-document-type");
  const filterOrganismEl = document.getElementById("filter-organism");
  const filterTopicEl = document.getElementById("filter-topic");

  let sessionKey = localStorage.getItem("eddi_session_key") || "";
  let sending = false;

  function scrollToBottom() {
    messagesEl.scrollTop = messagesEl.scrollHeight;
  }

  function addMessage(role, text) {
    const wrap = document.createElement("div");
    wrap.className = "msg " + role;

    const roleEl = document.createElement("div");
    roleEl.className = "msg-role";
    roleEl.textContent = role === "user" ? "Usuario" : "EDDI";

    const textEl = document.createElement("div");
    textEl.className = "msg-text";
    textEl.textContent = text;

    wrap.appendChild(roleEl);
    wrap.appendChild(textEl);
    messagesEl.appendChild(wrap);
    scrollToBottom();
    return wrap;
  }

  function renderSources(sources) {
    sourcesEl.innerHTML = "";
    if (!sources || !sources.length) return;

    const title = document.createElement("div");
    title.className = "sources-title";
    title.textContent = "Fuentes consultadas";
    sourcesEl.appendChild(title);

    sources.forEach(src => {
      const item = document.createElement("div");
      item.className = "source-item";

      item.innerHTML = `
        <div class="source-title">${src.title || "Documento"}</div>
        <div class="source-meta">${src.document_type || ""}</div>
        ${src.snippet ? `<div class="source-snippet">${src.snippet}</div>` : ""}
        ${src.url ? `<a href="${src.url}" target="_blank" rel="noopener">Abrir fuente</a>` : ""}
      `;
      sourcesEl.appendChild(item);
    });
  }

  async function sendMessage() {
    const text = inputEl.value.trim();
    if (!text || sending) return;

    sending = true;
    sendEl.disabled = true;

    addMessage("user", text);
    inputEl.value = "";

    const loadingNode = addMessage("assistant", "Procesando consulta...");

    try {
      const res = await fetch("/rag/eddi/chat", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          message: text,
          session_key: sessionKey,
          channel: "web",
          document_type: filterDocumentTypeEl?.value?.trim() || null,
          organism: filterOrganismEl?.value?.trim() || null,
          topic: filterTopicEl?.value?.trim() || null
        })
      });

      const data = await res.json();

      sessionKey = data.session_key || sessionKey;
      localStorage.setItem("eddi_session_key", sessionKey);

      loadingNode.remove();
      addMessage("assistant", data.answer || "No se pudo generar una respuesta.");
      renderSources(data.sources || []);
    } catch (err) {
      loadingNode.remove();
      addMessage("assistant", "Ocurrió un error al consultar el asistente.");
    } finally {
      sending = false;
      sendEl.disabled = false;
      inputEl.focus();
    }
  }

  sendEl.addEventListener("click", sendMessage);

  inputEl.addEventListener("keydown", (e) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
})();