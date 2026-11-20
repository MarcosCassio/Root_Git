function paraCalendario(texto, periodo, tipo) {
    const formato = periodo ? /^(\d{2})(\d{4})$/ : /^(\d{2})(\d{2})(\d{4})$/;
    const partes = texto.trim().replaceAll("/", "").match(formato);
    if (!partes) return "";
    if (periodo) {
        const mes = `${partes[2]}-${partes[1]}`;
        return tipo === "date" ? `${mes}-01` : mes;
    }
    return `${partes[3]}-${partes[2]}-${partes[1]}`;
}

for (const campo of document.querySelectorAll("[data-calendario]")) {
    const texto = campo.querySelector("input[name]");
    const nativo = campo.querySelector(".seletor-calendario");
    const botao = campo.querySelector("button");
    const periodo = campo.dataset.calendario === "month";

    if (periodo && nativo.type !== "month") {
        nativo.type = "date";
        nativo.setAttribute("aria-label", "Escolher um dia do mês desejado");
    }
    if (nativo.type === "text") continue;

    nativo.hidden = false;
    nativo.tabIndex = -1;
    nativo.setAttribute("aria-hidden", "true");
    botao.hidden = false;

    botao.addEventListener("click", () => {
        nativo.value = paraCalendario(texto.value, periodo, nativo.type);
        try {
            nativo.showPicker();
        } catch {
            nativo.classList.add("aberto");
            nativo.removeAttribute("aria-hidden");
            nativo.tabIndex = 0;
            nativo.focus();
        }
    });

    nativo.addEventListener("change", () => {
        if (!nativo.value) return;
        const partes = nativo.value.split("-");
        texto.value = (periodo ? partes.slice(0, 2) : partes).reverse().join("/");
        if (nativo.classList.contains("aberto")) {
            nativo.classList.remove("aberto");
            nativo.tabIndex = -1;
            botao.focus();
            nativo.setAttribute("aria-hidden", "true");
        }
    });
}
