"use strict";

const overview = document.getElementById("overview");
if (overview !== null) {
  const canonicalUrl = overview.dataset.canonicalUrl;
  if (canonicalUrl !== undefined) {
    history.replaceState(history.state, "", canonicalUrl);
  }
}

const selection = document.getElementById("selection");
const reportRegion = document.getElementById("report-region");

if (selection !== null && reportRegion !== null) {
  let activeGeneration = 0;
  const generations = new WeakMap();

  const showLoading = () => {
    const status = document.createElement("div");
    status.className = "report-state report-state--loading";
    status.setAttribute("role", "status");
    status.textContent = "Henter rapporten…";
    reportRegion.replaceChildren(status);
    reportRegion.setAttribute("aria-busy", "true");
  };

  const showFailure = () => {
    const failure = document.createElement("div");
    failure.id = "report-failure";
    failure.className = "report-state report-state--error";
    failure.setAttribute("role", "alert");

    const title = document.createElement("h2");
    title.textContent = "Rapporten kunne ikke hentes.";
    const explanation = document.createElement("p");
    explanation.textContent =
      "De viste tal er ikke opdateret. Kontrollér forbindelsen, og prøv igen.";
    const retry = document.createElement("button");
    retry.type = "button";
    retry.className = "button button--secondary";
    retry.textContent = "Prøv igen";
    retry.addEventListener("click", () => htmx.trigger(selection, "change"));

    failure.append(title, explanation, retry);
    reportRegion.replaceChildren(failure);
    reportRegion.setAttribute("aria-busy", "false");
  };

  const generationFor = (event) => {
    const xhr = event.detail.xhr;
    return xhr === undefined ? undefined : generations.get(xhr);
  };

  document.body.addEventListener("htmx:beforeRequest", (event) => {
    if (event.detail.elt !== selection && event.detail.target !== reportRegion) {
      return;
    }
    activeGeneration += 1;
    if (event.detail.xhr !== undefined) {
      generations.set(event.detail.xhr, activeGeneration);
    }
    showLoading();
  });

  document.body.addEventListener("htmx:sendError", (event) => {
    if (generationFor(event) === activeGeneration) {
      showFailure();
    }
  });

  document.body.addEventListener("htmx:responseError", (event) => {
    if (generationFor(event) === activeGeneration) {
      showFailure();
    }
  });

  document.body.addEventListener("htmx:afterSwap", (event) => {
    if (generationFor(event) === activeGeneration) {
      reportRegion.setAttribute("aria-busy", "false");
    }
  });
}
