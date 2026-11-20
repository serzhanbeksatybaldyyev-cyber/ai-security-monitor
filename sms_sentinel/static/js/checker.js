/* Проверка SMS и ссылок без перезагрузки страницы: fetch к REST API.
   Пользовательский текст выводится только через textContent. */
(function () {
  "use strict";

  var form = document.getElementById("check-form");
  if (!form || !window.fetch) return;

  var field = form.querySelector("[name=" + form.dataset.field + "]");
  var submit = document.getElementById("check-submit");
  var errorBox = document.getElementById("check-error");
  var idle = document.getElementById("result-idle");
  var busy = document.getElementById("result-busy");
  var box = document.getElementById("result-box");
  var kind = form.dataset.kind;
  form.dataset.ajax = "on";

  var SVG = "http://www.w3.org/2000/svg";

  function el(tag, cls, text) {
    var node = document.createElement(tag);
    if (cls) node.className = cls;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  }
  function icon(id) {
    var svg = document.createElementNS(SVG, "svg");
    svg.setAttribute("class", "sn-ico");
    var use = document.createElementNS(SVG, "use");
    use.setAttribute("href", "#" + id);
    svg.appendChild(use);
    return svg;
  }
  function add(parent) {
    for (var i = 1; i < arguments.length; i++) if (arguments[i]) parent.appendChild(arguments[i]);
    return parent;
  }
  function fmt(value) { return value === null || value === undefined ? "—" : Number(value).toFixed(2); }
  function heading(text) { return el("h3", "sn-section-title", text); }

  function tag(item, score) {
    var t = el("span", "sn-tag is-" + item.tone);
    add(t, icon(item.icon), document.createTextNode(item.category_label + (score === undefined ? "" : " · " + score)));
    return t;
  }

  function gauge(data) {
    var g = el("div", "sn-gauge");
    g.style.setProperty("--score", data.risk_score);
    g.style.setProperty("--t1", data.zones.medium);
    g.style.setProperty("--t2", data.zones.high);
    var row = add(el("div", "sn-gauge-row"), (function () {
      var num = el("span", "sn-gauge-num", String(data.risk_score));
      num.appendChild(el("small", null, "/ 100"));
      return num;
    })(), el("span", "sn-muted sn-small", "Risk Score"));
    var track = el("div", "sn-gauge-track");
    track.setAttribute("role", "img");
    track.setAttribute("aria-label", "Risk Score " + data.risk_score + " из 100");
    add(track, el("span"), el("span"), el("span"));
    var fill = el("div", "sn-gauge-fill");
    add(fill, el("i", "z1"), el("i", "z2"), el("i", "z3"));
    add(track, fill, el("i", "sn-gauge-marker"));
    var scale = el("div", "sn-gauge-scale");
    scale.setAttribute("aria-hidden", "true");
    add(scale, el("span", null, "0"), el("span", "s1", String(data.zones.medium)), el("span", "s2", String(data.zones.high)), el("span", null, "100"));
    return add(g, row, track, scale);
  }

  function prob(label, value, mono) {
    var p = el("div", "sn-prob");
    var strong = el("strong", mono ? "sn-mono" : "", value);
    if (mono) { strong.style.fontSize = "14px"; strong.style.overflowWrap = "anywhere"; }
    return add(p, el("span", null, label), strong);
  }

  function urlLine(link) {
    var line = el("div", "sn-urlbox");
    var url = el("span", "sn-url");
    add(url, document.createTextNode(link.parts.before), el("span", "sn-host", link.parts.host), document.createTextNode(link.parts.after));
    return add(line, url, tag(link, link.risk_score));
  }

  function reasonList(data) {
    var list = el("ul", "sn-list");
    data.explanation.forEach(function (reason) {
      var li = el("li");
      var bullet = add(el("span", "sn-bullet"), icon(data.category === "SAFE" ? "i-check" : "i-bang"));
      add(li, bullet, el("span", null, reason));
      list.appendChild(li);
    });
    return add(el("div"), heading("Почему такой результат"), list);
  }

  function advice(data) {
    var inner = add(el("div"), el("strong", null, "Что делать"), el("span", null, data.recommendation));
    return add(el("div", "sn-advice"), icon("i-shield"), inner);
  }

  function foot(data) {
    var left = el("span");
    add(left, document.createTextNode(data.created_display + " · " + (data.versions_label || "модели: нет данных")), el("br"), document.createTextNode(data.disclaimer));
    var more = el("a", "btn btn-sm btn-outline-secondary", "Подробнее");
    more.href = data.detail_url;
    var del = el("a", "btn btn-sm btn-outline-danger");
    del.href = data.delete_url;
    add(del, icon("i-trash"), document.createTextNode("Удалить"));
    return add(el("div", "sn-foot"), left, add(el("span", "sn-actions"), more, del));
  }

  function verdict(data, body) {
    var article = el("article", "sn-verdict is-" + data.tone);
    var title = add(el("h2", "sn-verdict-title"), icon(data.icon), document.createTextNode(data.verdict_title));
    var top = add(el("div", "sn-verdict-top"), title, el("span", "sn-verdict-level", "Уровень риска: " + data.risk_level_label.toLowerCase()));
    add(article, top, gauge(data));
    body.forEach(function (part) { add(article, part); });
    return add(article, reasonList(data), advice(data), foot(data));
  }

  function renderSms(data) {
    var probs = add(el("div", "sn-probs"), prob("P_sms · текст", fmt(data.p_sms)), prob("P_url · ссылки (макс.)", fmt(data.p_url_max)), prob("Признаков в тексте", String(data.features.length)));
    var parts = [probs];
    if (!data.reliable) {
      var note = el("div", "sn-alert is-warn");
      note.setAttribute("role", "note");
      add(note, icon("i-warn"), el("span", null, "Текстовая модель обучена на английских SMS, поэтому для этого языка оценка текста ненадёжна. Итог больше опирается на словарь признаков и анализ ссылки."));
      parts.push(note);
    }
    var quote = add(el("div"), heading("Проверенный текст" + (data.language_name ? " · язык: " + data.language_name : "")), el("div", "sn-quote", data.text));
    if (data.is_masked) quote.appendChild(el("div", "sn-muted sn-small mt-2", "Телефоны, номера карт, суммы и коды скрыты: хранение полного текста выключено в профиле."));
    parts.push(quote);
    if (data.urls.length) {
      var links = add(el("div"), heading("Найденные ссылки · не кликабельны, не открывались"));
      data.urls.forEach(function (link) { links.appendChild(urlLine(link)); });
      parts.push(links);
    }
    return [verdict(data, parts)];
  }

  function renderUrl(data) {
    var link = data.urls[0];
    var hits = link.checks.filter(function (row) { return row.hit; }).length;
    var probs = add(el("div", "sn-probs"), prob("P_url · опасность", fmt(link.p_url)), prob("Сработало признаков", String(hits)), prob("Домен", link.domain, true));
    var address = add(el("div"), heading("Адрес · не кликабелен, не открывался"), urlLine(link));
    var features = el("section", "sn-panel");
    add(features, add(el("div", "sn-panel-head"), el("h2", "sn-panel-title", "Признаки адреса"), el("span", "sn-muted sn-small", "сработавшие выделены")));
    var list = el("ul", "sn-checks");
    link.checks.forEach(function (row) {
      var li = el("li", row.hit ? "is-hit" : "");
      add(li, add(el("span", "sn-flag"), icon(row.hit ? "i-bang" : "i-check")), el("span", "sn-label", row.label), el("span", "sn-value", String(row.value)));
      list.appendChild(li);
    });
    add(features, list);
    return [verdict(data, [probs, address]), features];
  }

  function show(nodes) {
    box.replaceChildren.apply(box, nodes);
    if (idle) idle.hidden = true;
    box.hidden = false;
    box.scrollIntoView({ block: "nearest", behavior: "smooth" });
  }

  function setBusy(on) {
    busy.classList.toggle("is-on", on);
    submit.disabled = on;
    if (on) { if (idle) idle.hidden = true; box.hidden = true; }
  }

  function showError(message) {
    errorBox.textContent = message;
    errorBox.hidden = false;
    field.classList.add("is-invalid");
    field.setAttribute("aria-invalid", "true");
    field.focus();
  }
  function clearError() {
    errorBox.hidden = true;
    errorBox.textContent = "";
    field.classList.remove("is-invalid");
    field.removeAttribute("aria-invalid");
  }

  function restore() {
    busy.classList.remove("is-on");
    submit.disabled = false;
    if (box.childNodes.length) { box.hidden = false; } else if (idle) { idle.hidden = false; }
  }

  function fillSamples() {
    document.querySelectorAll("[data-sample]").forEach(function (link) {
      link.addEventListener("click", function (event) {
        event.preventDefault();
        field.value = link.dataset.sample;
        field.dispatchEvent(new Event("input", { bubbles: true }));
        clearError();
        field.focus();
      });
    });
  }
  fillSamples();
  field.addEventListener("input", clearError);

  form.addEventListener("submit", function (event) {
    event.preventDefault();
    if (submit.disabled) return;
    clearError();
    var value = field.value.trim();
    if (!value) {
      showError(kind === "sms" ? "Текст SMS не может быть пустым." : "Введите ссылку.");
      return;
    }
    var limit = field.maxLength > 0 ? field.maxLength : 2048;
    if (value.length > limit) {
      showError(kind === "sms" ? "Текст не должен быть длиннее 1000 символов." : "Ссылка длиннее 2048 символов.");
      return;
    }
    setBusy(true);
    var body = {};
    body[form.dataset.field] = value;
    fetch(form.dataset.api, {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "Accept": "application/json", "X-CSRFToken": form.querySelector("[name=csrfmiddlewaretoken]").value },
      body: JSON.stringify(body)
    }).then(function (response) {
      return response.json().catch(function () { return {}; }).then(function (json) { return { ok: response.ok, status: response.status, json: json }; });
    }).then(function (res) {
      if (res.status === 401 || res.status === 403) { window.location.assign("/login/?next=" + encodeURIComponent(window.location.pathname)); return; }
      if (!res.ok) {
        restore();
        showError((res.json.error && res.json.error.message) || "Не удалось выполнить проверку. Попробуйте ещё раз.");
        return;
      }
      busy.classList.remove("is-on");
      submit.disabled = false;
      show(kind === "sms" ? renderSms(res.json) : renderUrl(res.json));
      try { window.history.replaceState(null, "", window.location.pathname + "?result=" + res.json.id); } catch (e) { /* не критично */ }
    }).catch(function () {
      restore();
      showError("Нет связи с сервером. Проверьте подключение и повторите.");
    });
  });
})();
