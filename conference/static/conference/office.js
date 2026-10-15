// Кабинет: отметка допуска ко 2 этапу без перезагрузки страницы.
// Без JS кнопки отправляют форму обычным способом — сервер вернёт ту же страницу.
document.querySelectorAll("form[data-admission]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    const data = new FormData(form);
    data.set("admission", button ? button.value : "");
    form.classList.add("admission--busy");
    try {
      const response = await fetch(form.action, {
        method: "POST",
        body: data,
        headers: { Accept: "application/json" },
        credentials: "same-origin",
      });
      if (!response.ok) throw new Error(response.status);
      const result = await response.json();
      form.querySelectorAll(".admission__btn").forEach((b) => {
        b.setAttribute("aria-pressed", String(b.value === result.admission));
      });
      form.querySelector(".admission__clear").hidden = !result.admission;
      const row = form.closest("tr");
      row.className = `people__row--${result.admission || "pending"}`;
      ["admitted", "not_admitted", "pending"].forEach((key) => {
        const counter = document.querySelector(`[data-count="${key}"]`);
        if (counter) counter.textContent = result[key];
      });
    } catch {
      // Что-то пошло не так — отправляем форму обычным способом: сервер сохранит или покажет ошибку.
      const input = Object.assign(document.createElement("input"), { type: "hidden", name: "admission", value: data.get("admission") });
      form.querySelectorAll("button").forEach((b) => b.removeAttribute("name"));
      form.append(input);
      form.submit();
    } finally {
      form.classList.remove("admission--busy");
    }
  });
});
