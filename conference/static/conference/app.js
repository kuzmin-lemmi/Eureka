document.addEventListener("DOMContentLoaded", () => {
  // Проверка размера файла до отправки, чтобы не ждать загрузку зря.
  document.querySelectorAll("input[type=file][data-max-mb]").forEach((input) => {
    input.addEventListener("change", () => {
      const maxMb = Number(input.dataset.maxMb);
      const file = input.files[0];
      input.setCustomValidity(
        file && file.size > maxMb * 1024 * 1024 ? `Файл больше ${maxMb} МБ` : ""
      );
      input.reportValidity();
    });
  });

  // Счётчик символов для полей с ограничением длины.
  document.querySelectorAll("textarea[maxlength]").forEach((textarea) => {
    const counter = document.createElement("span");
    counter.className = "help counter";
    const update = () => (counter.textContent = `${textarea.value.length} / ${textarea.maxLength}`);
    textarea.insertAdjacentElement("afterend", counter);
    textarea.addEventListener("input", update);
    update();
  });

  // Защита от двойной отправки.
  document.querySelectorAll("form[data-once]").forEach((form) => {
    form.addEventListener("submit", (event) => {
      const fileInput = form.querySelector("input[type=file]");
      if (fileInput && fileInput.validity.customError) {
        event.preventDefault();
        fileInput.reportValidity();
        return;
      }
      const button = form.querySelector("button[type=submit]");
      button.disabled = true;
      button.textContent = "Отправляем…";
    });
  });
});
