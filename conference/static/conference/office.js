// Кабинет: допуск ко 2 этапу и итог (место или номинация) без перезагрузки страницы.
// Без JS формы отправляются обычным способом — сервер вернёт ту же страницу.

async function postForm(form, data) {
  const response = await fetch(form.action, {
    method: "POST",
    body: data,
    headers: { Accept: "application/json" },
    credentials: "same-origin",
  });
  if (!response.ok) throw new Error(response.status);
  return response.json();
}

function updateAwarded() {
  const counter = document.querySelector('[data-count="awarded"]');
  if (counter) counter.textContent = [...document.querySelectorAll(".award__select")].filter((s) => s.value).length;
}

function showAward(select, value) {
  select.value = value;
  select.classList.toggle("award__select--set", Boolean(value));
  select.title = value ? select.selectedOptions[0].textContent : "";
}

document.querySelectorAll("form[data-admission]").forEach((form) => {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = event.submitter;
    const data = new FormData(form);
    data.set("admission", button ? button.value : "");
    form.classList.add("admission--busy");
    try {
      const result = await postForm(form, data);
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
      // Место или номинация — только у допущенных: сервер снимает итог, если допуск убрали.
      const select = row.querySelector(".award__select");
      if (select) {
        select.disabled = result.admission !== "admitted";
        select.options[0].textContent = select.disabled ? "только допущенным" : "— нет —";
        showAward(select, result.award);
        updateAwarded();
      }
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

document.querySelectorAll("form[data-award]").forEach((form) => {
  const select = form.querySelector(".award__select");
  form.querySelector(".award__save").hidden = true; // с JS итог сохраняется сразу при выборе
  select.addEventListener("change", async () => {
    form.classList.add("admission--busy");
    try {
      const result = await postForm(form, new FormData(form));
      showAward(select, result.award);
      updateAwarded();
    } catch {
      form.submit();
    } finally {
      form.classList.remove("admission--busy");
    }
  });
});
