(function () {
  var campo = document.getElementById("busca-politico");
  var lista = document.getElementById("sugestoes");
  if (!campo || !lista || !window.fetch) return;

  var timer = null, itens = [], ativo = -1, pedido = 0;

  function fechar() {
    lista.hidden = true;
    lista.innerHTML = "";
    itens = [];
    ativo = -1;
    campo.setAttribute("aria-expanded", "false");
    campo.removeAttribute("aria-activedescendant");
  }

  function marcar(i) {
    if (!itens.length) return;
    ativo = (i + itens.length) % itens.length;
    itens.forEach(function (li, n) { li.setAttribute("aria-selected", n === ativo ? "true" : "false"); });
    campo.setAttribute("aria-activedescendant", itens[ativo].id);
  }

  function mostrar(dados) {
    fechar();
    if (!dados.length) return;
    dados.forEach(function (d, n) {
      var li = document.createElement("li");
      li.id = "sugestao-" + n;
      li.setAttribute("role", "option");
      li.setAttribute("aria-selected", "false");
      var a = document.createElement("a");
      a.href = d.url;
      a.tabIndex = -1;
      a.textContent = d.nome_urna + " — " + d.cargo + (d.partido ? " (" + d.partido + ")" : "");
      li.appendChild(a);
      lista.appendChild(li);
      itens.push(li);
    });
    lista.hidden = false;
    campo.setAttribute("aria-expanded", "true");
  }

  campo.addEventListener("input", function () {
    clearTimeout(timer);
    var q = campo.value.trim();
    if (q.length < 2) { pedido++; fechar(); return; }
    timer = setTimeout(function () {
      var meu = ++pedido;
      fetch(campo.getAttribute("data-url") + "?q=" + encodeURIComponent(q))
        .then(function (r) { return r.ok ? r.json() : []; })
        .then(function (d) { if (meu === pedido) mostrar(d); })
        .catch(function () { fechar(); });
    }, 200);
  });

  campo.addEventListener("keydown", function (e) {
    if (e.key === "ArrowDown" && itens.length) { e.preventDefault(); marcar(ativo + 1); }
    else if (e.key === "ArrowUp" && itens.length) { e.preventDefault(); marcar(ativo - 1); }
    else if (e.key === "Enter" && ativo >= 0) { e.preventDefault(); window.location = itens[ativo].querySelector("a").href; }
    else if (e.key === "Escape") { fechar(); }
  });

  document.addEventListener("click", function (e) {
    if (e.target !== campo && !lista.contains(e.target)) fechar();
  });
})();
