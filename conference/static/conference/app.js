// Улучшения анкеты. Без JS форма тоже работает: всё проверяет сервер.
document.addEventListener("DOMContentLoaded", () => {
  const DRAFT_KEY = "eureka-submission-draft-v1";

  const storage = {
    get(key) {
      try { return JSON.parse(localStorage.getItem(key)); } catch { return null; }
    },
    set(key, value) {
      try { localStorage.setItem(key, JSON.stringify(value)); } catch { /* приватный режим */ }
    },
    remove(key) {
      try { localStorage.removeItem(key); } catch { /* приватный режим */ }
    },
  };

  // Страница «Спасибо»: анкета отправлена, черновик больше не нужен.
  if (document.querySelector("[data-clear-draft]")) storage.remove(DRAFT_KEY);

  const form = document.querySelector("form[data-draft]");
  if (!form) return;

  const formatSize = (bytes) =>
    bytes < 1024 * 1024 ? `${Math.max(1, Math.round(bytes / 1024))} КБ` : `${(bytes / 1024 / 1024).toFixed(1)} МБ`;

  // --- Поля загрузки файлов ---
  form.querySelectorAll(".drop").forEach((drop) => {
    const input = drop.querySelector("input[type=file]");
    const text = drop.querySelector(".drop__text");
    const icon = drop.querySelector(".drop__icon");
    const initialText = text.innerHTML;
    const accept = (input.accept || "").split(",").map((ext) => ext.trim().toLowerCase()).filter(Boolean);
    const maxMb = Number(input.dataset.maxMb);

    const update = () => {
      const file = input.files[0];
      let message = "";
      if (file) {
        const ext = file.name.slice(file.name.lastIndexOf(".")).toLowerCase();
        if (accept.length && !accept.includes(ext)) {
          message = `Недопустимый формат. Подойдут: ${accept.map((e) => e.slice(1).toUpperCase()).join(", ")}.`;
        } else if (maxMb && file.size > maxMb * 1024 * 1024) {
          message = `Файл больше ${maxMb} МБ.`;
        }
      }
      input.setCustomValidity(message);
      drop.classList.toggle("has-file", Boolean(file) && !message);
      if (file) {
        text.innerHTML = "";
        const name = document.createElement("b");
        name.textContent = file.name;
        const meta = document.createElement("small");
        meta.textContent = `${formatSize(file.size)} · нажмите, чтобы заменить`;
        text.append(name, meta);
        icon.textContent = message ? "!" : "✓";
      } else {
        text.innerHTML = initialText;
        icon.textContent = "⬆";
      }
    };

    input.addEventListener("change", () => {
      update();
      validateField(input, true);
    });
    ["dragenter", "dragover"].forEach((type) => input.addEventListener(type, () => drop.classList.add("is-dragover")));
    ["dragleave", "drop"].forEach((type) => input.addEventListener(type, () => drop.classList.remove("is-dragover")));
    update();
  });

  // --- Маска телефона: +7 (900) 123-45-67 ---
  form.querySelectorAll("input[data-phone]").forEach((input) => {
    const format = () => {
      let digits = input.value.replace(/\D/g, "");
      if (!digits) return;
      if (digits[0] === "8") digits = "7" + digits.slice(1);
      if (digits[0] === "9") digits = "7" + digits;
      if (digits[0] !== "7") return; // не российский номер — оставляем как ввели
      digits = digits.slice(0, 11);
      const p = [digits.slice(1, 4), digits.slice(4, 7), digits.slice(7, 9), digits.slice(9, 11)];
      let out = "+7";
      if (p[0]) out += ` (${p[0]}`;
      if (p[0].length === 3 && p[1]) out += `) ${p[1]}`;
      if (p[2]) out += `-${p[2]}`;
      if (p[3]) out += `-${p[3]}`;
      input.value = out;
    };
    input.addEventListener("input", (event) => {
      if (event.inputType && event.inputType.startsWith("delete")) return; // не мешаем стирать
      format();
    });
    input.addEventListener("blur", format);
  });

  // --- Маска СНИЛС: 123-456-789 01 ---
  form.querySelectorAll("input[data-snils]").forEach((input) => {
    input.addEventListener("input", (event) => {
      if (event.inputType && event.inputType.startsWith("delete")) return;
      const d = input.value.replace(/\D/g, "").slice(0, 11);
      let out = d.slice(0, 3);
      if (d.length > 3) out += `-${d.slice(3, 6)}`;
      if (d.length > 6) out += `-${d.slice(6, 9)}`;
      if (d.length > 9) out += ` ${d.slice(9, 11)}`;
      input.value = out;
    });
  });

  // --- Проверка полей при вводе ---
  const messageFor = (input) => {
    const v = input.validity;
    if (v.customError) return input.validationMessage;
    if (v.valueMissing) {
      if (input.type === "file") return "Прикрепите файл.";
      if (input.type === "checkbox") return "Нужно ваше подтверждение.";
      return input.tagName === "SELECT" ? "Выберите из списка." : "Заполните поле.";
    }
    if (v.typeMismatch && input.type === "email") return "Проверьте адрес: например, name@example.ru.";
    if (v.tooLong) return "Слишком длинное значение.";
    return input.validationMessage;
  };

  const checkSnils = (input) => {
    if (!input.matches("[data-snils]")) return;
    const digits = input.value.replace(/\D/g, "");
    input.setCustomValidity(input.value && digits.length !== 11 ? "СНИЛС состоит из 11 цифр." : "");
  };

  const checkPhone = (input) => {
    checkSnils(input);
    if (!input.matches("[data-phone]")) return;
    const digits = input.value.replace(/\D/g, "");
    input.setCustomValidity(input.value && digits.length < 10 ? "Укажите телефон полностью." : "");
  };

  function validateField(input, show) {
    const field = input.closest(".field");
    if (!field) return true;
    checkPhone(input);
    const valid = input.checkValidity();
    field.querySelectorAll(".error").forEach((el) => el.remove());
    field.classList.toggle("field--error", show && !valid);
    field.classList.toggle("field--valid", valid && input.type !== "checkbox" && Boolean(input.value));
    if (show && !valid) {
      const error = document.createElement("p");
      error.className = "error";
      error.textContent = messageFor(input);
      field.append(error);
    }
    return valid;
  }

  const controls = () =>
    [...form.querySelectorAll("input, select, textarea")].filter(
      (el) => el.name && el.type !== "hidden" && !el.closest(".hp")
    );

  controls().forEach((input) => {
    // Серверные ошибки остаются, пока поле не исправят.
    input.addEventListener("blur", () => {
      if (input.type !== "file" && (input.value || input.closest(".field--error"))) validateField(input, true);
    });
    input.addEventListener("input", () => {
      if (input.closest(".field--error")) validateField(input, true);
    });
    input.addEventListener("change", () => {
      if (input.tagName === "SELECT" || input.type === "checkbox") validateField(input, true);
    });
  });

  // --- «Совпадает с почтой участника» ---
  const sameEmail = form.querySelector("[data-same-email]");
  const email = form.elements.email;
  const linksEmail = form.elements.links_email;
  if (sameEmail && email && linksEmail) {
    const checkbox = sameEmail.querySelector("input");
    sameEmail.hidden = false;
    const sync = () => {
      linksEmail.readOnly = checkbox.checked;
      if (checkbox.checked) {
        linksEmail.value = email.value;
        if (email.value) validateField(linksEmail, true);
      }
      updateProgress();
    };
    checkbox.addEventListener("change", sync);
    email.addEventListener("input", () => checkbox.checked && sync());
    checkbox.checked = Boolean(email.value) && email.value === linksEmail.value;
    linksEmail.readOnly = checkbox.checked;
  }

  // --- Прогресс по разделам ---
  const progress = document.querySelector("[data-progress]");
  const steps = [...form.querySelectorAll("[data-step]")];

  function updateProgress() {
    if (!progress) return;
    let done = 0;
    steps.forEach((step) => {
      const required = [...step.querySelectorAll("[required]")];
      required.forEach(checkPhone);
      const complete = required.every((el) => el.checkValidity());
      if (complete) done += 1;
      progress.querySelector(`[data-step-link="${step.dataset.step}"]`)?.classList.toggle("is-done", complete);
    });
    progress.querySelector("[data-progress-count]").textContent = done;
    progress.querySelector("[data-progress-total]").textContent = steps.length;
    progress.querySelector("[data-progress-bar]").style.width = `${(done / steps.length) * 100}%`;
  }

  if (progress) {
    progress.hidden = false;
    form.addEventListener("input", updateProgress);
    form.addEventListener("change", updateProgress);

    // Подсветка раздела, который сейчас на экране.
    const links = progress.querySelectorAll(".progress__list a");
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return;
          links.forEach((link) => link.classList.toggle("is-current", link.hash === `#${entry.target.id}`));
        });
      },
      { rootMargin: "-30% 0px -60% 0px" }
    );
    form.querySelectorAll("fieldset[id], details[id]").forEach((el) => observer.observe(el));
  }

  // --- Черновик в браузере (без файлов: их браузер сохранить не может) ---
  const draftFields = () =>
    controls().filter((el) => el.type !== "file" && el.type !== "checkbox" && el.name !== "csrfmiddlewaretoken");

  // При редактировании поданной заявки черновик не нужен: он подставил бы данные чужой анкеты.
  const useDraft = form.dataset.draft !== "off";

  const saveDraft = () => {
    if (!useDraft) return;
    const data = {};
    draftFields().forEach((el) => {
      if (el.value) data[el.name] = el.value;
    });
    if (Object.keys(data).length) storage.set(DRAFT_KEY, data);
    else storage.remove(DRAFT_KEY);
  };

  const draft = useDraft ? storage.get(DRAFT_KEY) : null;
  if (draft && typeof draft === "object") {
    let restored = 0;
    draftFields().forEach((el) => {
      // Заполняем только пустые поля: введённое на сервере (ошибки, «ещё одна работа») важнее.
      if (!el.value && typeof draft[el.name] === "string") {
        el.value = draft[el.name];
        if (el.value) restored += 1;
      }
    });
    if (restored) {
      const notice = form.querySelector("[data-draft-notice]");
      notice.hidden = false;
      const coauthor = form.querySelector("#step-coauthor");
      if (coauthor && ["coauthor_last_name", "coauthor_first_name", "coauthor_grade", "coauthor_snils"].some((n) => form.elements[n]?.value)) {
        coauthor.open = true;
      }
      const supervisor2 = form.querySelector("#step-supervisor2");
      if (supervisor2 && [...supervisor2.querySelectorAll("input")].some((el) => el.value)) supervisor2.open = true;
      if (sameEmail && email.value && email.value === linksEmail.value) {
        sameEmail.querySelector("input").checked = true;
        linksEmail.readOnly = true;
      }
      notice.querySelector("[data-draft-reset]").addEventListener("click", () => {
        storage.remove(DRAFT_KEY);
        window.location.href = window.location.pathname;
      });
    }
  }

  let saveTimer;
  form.addEventListener("input", () => {
    clearTimeout(saveTimer);
    saveTimer = setTimeout(saveDraft, 400);
  });
  form.addEventListener("change", saveDraft);

  updateProgress();

  // --- Отправка: проверка всех полей и защита от двойного нажатия ---
  form.addEventListener("submit", (event) => {
    const invalid = controls().filter((input) => !validateField(input, true));
    if (invalid.length) {
      event.preventDefault();
      const first = invalid[0];
      first.closest("details")?.setAttribute("open", "");
      first.closest(".field").scrollIntoView({ behavior: "smooth", block: "center" });
      first.focus({ preventScroll: true });
      return;
    }
    saveDraft();
    const button = form.querySelector("button[type=submit]");
    button.disabled = true;
    button.textContent = button.dataset.busyText || "Отправляем…";
  });
});
