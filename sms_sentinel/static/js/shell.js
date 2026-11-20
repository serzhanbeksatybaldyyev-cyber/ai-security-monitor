/* Каркас интерфейса: тема, мобильное меню, кликабельные строки, поведение форм. */
(function () {
  "use strict";

  var root = document.documentElement;

  function currentTheme() {
    return root.getAttribute("data-bs-theme") === "light" ? "light" : "dark";
  }

  function paintThemeButtons() {
    var light = currentTheme() === "light";
    document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
      var label = button.querySelector("[data-theme-label]");
      var use = button.querySelector("use");
      if (label) label.textContent = light ? "Тёмная" : "Светлая";
      if (use) use.setAttribute("href", light ? "#i-moon" : "#i-sun");
    });
  }

  function applyTheme(theme) {
    root.setAttribute("data-bs-theme", theme);
    try { localStorage.setItem("sn-theme", theme); } catch (error) { /* хранилище может быть закрыто */ }
    paintThemeButtons();
    document.dispatchEvent(new CustomEvent("sn:theme", { detail: theme }));
  }

  document.querySelectorAll("[data-theme-toggle]").forEach(function (button) {
    button.addEventListener("click", function () {
      applyTheme(currentTheme() === "light" ? "dark" : "light");
    });
  });
  paintThemeButtons();

  /* боковое меню на узких экранах */
  var shell = document.getElementById("shell");
  document.querySelectorAll("[data-nav-toggle]").forEach(function (trigger) {
    trigger.addEventListener("click", function () {
      if (!shell) return;
      var open = shell.classList.toggle("is-nav-open");
      document.querySelectorAll("button[data-nav-toggle]").forEach(function (b) { b.setAttribute("aria-expanded", String(open)); });
    });
  });
  document.addEventListener("keydown", function (event) {
    if (event.key === "Escape" && shell) shell.classList.remove("is-nav-open");
  });

  /* строка таблицы ведёт на подробности */
  document.querySelectorAll("tr[data-href]").forEach(function (row) {
    row.tabIndex = 0;
    var go = function () { window.location.assign(row.dataset.href); };
    row.addEventListener("click", function (event) {
      if (!event.target.closest("a, button")) go();
    });
    row.addEventListener("keydown", function (event) {
      if (event.key === "Enter") go();
    });
  });

  /* подсветка полей с ошибкой, сообщённой сервером */
  document.querySelectorAll(".sn-error").forEach(function (message) {
    var field = message.parentElement && message.parentElement.querySelector("input:not([type=hidden]), textarea, select");
    if (field) {
      field.classList.add("is-invalid");
      field.setAttribute("aria-invalid", "true");
    }
  });

  /* счётчик символов, очистка поля, защита от двойной отправки */
  document.querySelectorAll("textarea[data-counter]").forEach(function (area) {
    var out = document.getElementById(area.dataset.counter);
    if (!out) return;
    var paint = function () {
      out.textContent = area.value.length + " / " + area.maxLength;
      out.classList.toggle("is-over", area.value.length >= area.maxLength);
    };
    area.addEventListener("input", paint);
    paint();
  });
  document.querySelectorAll("[data-clear]").forEach(function (button) {
    button.addEventListener("click", function () {
      var target = document.getElementById(button.dataset.clear);
      if (!target) return;
      target.value = "";
      target.dispatchEvent(new Event("input", { bubbles: true }));
      target.focus();
    });
  });
  document.querySelectorAll("form[data-once]").forEach(function (form) {
    form.addEventListener("submit", function () {
      if (form.dataset.ajax === "on") return;
      var button = form.querySelector("button[type=submit]");
      if (button) { button.disabled = true; }
    });
  });
})();
