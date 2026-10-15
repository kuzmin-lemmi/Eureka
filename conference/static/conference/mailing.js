// Рассылка: отправляем письма пачками и показываем ход. Без JS кнопка отправит одну пачку и вернёт на страницу.

const root = document.querySelector("[data-mailing]");
const form = root && root.querySelector("[data-send-form]");

if (form) {
  const button = form.querySelector("[data-send-btn]");
  const box = root.querySelector("[data-progress]");
  const bar = root.querySelector("[data-bar]");
  const status = root.querySelector("[data-status]");
  const pause = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    button.disabled = true;
    box.hidden = false;
    let retry = "1";
    let totalSent = 0;
    let totalFailed = 0;
    let first = null;
    try {
      for (;;) {
        const data = new FormData(form);
        data.set("retry", retry);
        retry = "0"; // ошибки прошлых попыток сбрасываем только в первой пачке
        const response = await fetch(form.action, {
          method: "POST",
          body: data,
          headers: { Accept: "application/json" },
          credentials: "same-origin",
        });
        const result = await response.json();
        if (result.error && !("sent" in result)) throw new Error(result.error);
        totalSent += result.sent;
        totalFailed += result.failed;
        if (first === null) first = result.sent + result.failed + result.queue;
        const done = totalSent + totalFailed;
        bar.style.width = `${first ? Math.min(100, Math.round((100 * done) / first)) : 100}%`;
        status.textContent = `Отправлено ${totalSent}${totalFailed ? `, ошибок ${totalFailed}` : ""}. Осталось: ${result.queue}.`;
        for (const key of ["sent", "pending", "failed"]) {
          const counter = document.querySelector(`[data-mail="${key}"]`);
          if (counter) counter.textContent = result.totals[key];
        }
        if (result.error) throw new Error(result.error);
        if (!result.queue || (!result.sent && !result.failed)) break;
        await pause(1500); // не перегружаем почтовый сервер
      }
      status.textContent = `Готово. Отправлено ${totalSent}${totalFailed ? `, не дошло ${totalFailed} — их можно отправить снова этой же кнопкой` : ""}.`;
    } catch (error) {
      status.textContent = `Отправка остановлена: ${error.message}. Уже отправленные письма повторно не уйдут.`;
    } finally {
      button.disabled = false;
    }
  });
}
