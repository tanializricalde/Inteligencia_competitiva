import "@tabler/core/dist/css/tabler.min.css";
import "@tabler/icons-webfont/dist/tabler-icons.min.css";
import "./app.scss";
import htmx from "htmx.org";
import Chart from "chart.js/auto";

const themeStorageKey = "market-watch-theme";
const root = document.documentElement;
const systemTheme = window.matchMedia("(prefers-color-scheme: dark)");
const sidebarStorageKey = "market-watch-sidebar-collapsed";

function storedTheme() {
  try {
    const value = localStorage.getItem(themeStorageKey);
    return value === "dark" || value === "light" ? value : null;
  } catch (_error) {
    return null;
  }
}

function updateThemeControls() {
  const current = root.getAttribute("data-bs-theme") === "dark" ? "dark" : "light";
  const nextLabel = current === "dark" ? "claro" : "oscuro";
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    const label = `Cambiar a tema ${nextLabel}`;
    button.setAttribute("aria-label", label);
    button.setAttribute("title", label);
    const hiddenLabel = button.querySelector("[data-theme-label]");
    if (hiddenLabel) hiddenLabel.textContent = label;
  });
}

function applyTheme(theme, persist = false) {
  root.setAttribute("data-bs-theme", theme);
  if (persist) {
    try {
      localStorage.setItem(themeStorageKey, theme);
    } catch (_error) {
      // The selected theme still applies for the current page.
    }
  }
  updateThemeControls();
}

document.addEventListener("DOMContentLoaded", () => {
  updateThemeControls();
  document.querySelectorAll("[data-theme-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const current = root.getAttribute("data-bs-theme") === "dark" ? "dark" : "light";
      applyTheme(current === "dark" ? "light" : "dark", true);
    });
  });
  initializeSidebar();
  if (window.location.hash === "#dashboard-results") {
    document.getElementById("dashboard-results")?.focus({ preventScroll: true });
  }
});

function initializeSidebar() {
  const shell = document.querySelector("[data-app-shell]");
  const button = document.querySelector("[data-sidebar-toggle]");
  if (!shell || !button) return;
  const compact = window.matchMedia("(max-width: 800px)");
  let collapsed = false;
  try {
    collapsed = localStorage.getItem(sidebarStorageKey) === "true";
  } catch (_error) {
    // Keep the expanded default when storage is unavailable.
  }
  if (!compact.matches) shell.classList.toggle("sidebar-collapsed", collapsed);

  const updateControl = () => {
    const expanded = compact.matches
      ? shell.classList.contains("sidebar-open")
      : !shell.classList.contains("sidebar-collapsed");
    button.setAttribute("aria-expanded", String(expanded));
    button.setAttribute("title", expanded ? "Contraer menú" : "Expandir menú");
  };
  button.addEventListener("click", () => {
    if (compact.matches) {
      shell.classList.toggle("sidebar-open");
    } else {
      shell.classList.toggle("sidebar-collapsed");
      collapsed = shell.classList.contains("sidebar-collapsed");
      try {
        localStorage.setItem(
          sidebarStorageKey,
          String(collapsed),
        );
      } catch (_error) {
        // The layout still changes for the current page.
      }
    }
    updateControl();
  });
  compact.addEventListener("change", () => {
    shell.classList.remove("sidebar-open");
    if (compact.matches) shell.classList.remove("sidebar-collapsed");
    else shell.classList.toggle("sidebar-collapsed", collapsed);
    updateControl();
  });
  updateControl();
}

systemTheme.addEventListener("change", (event) => {
  if (!storedTheme()) applyTheme(event.matches ? "dark" : "light");
});

const dashboardCharts = new Map();

function replaceChart(id, configuration) {
  const canvas = document.getElementById(id);
  if (!canvas) return;
  dashboardCharts.get(id)?.destroy();
  dashboardCharts.set(id, new Chart(canvas, configuration));
}

function initializeDashboard() {
  const payloadNode = document.getElementById("dashboard-data");
  if (!payloadNode) return;
  const data = JSON.parse(payloadNode.textContent);
  const evolution = data.price_evolution;
  if (evolution.datasets.length) {
    replaceChart("price-evolution-chart", {
      type: "line",
      data: {
        labels: evolution.labels,
        datasets: evolution.datasets.map((series) => ({
          label: series.label,
          data: series.values,
          borderColor: series.color,
          backgroundColor: series.color,
          tension: 0.25,
          pointRadius: 3,
          spanGaps: false,
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        interaction: { mode: "index", intersect: false },
        scales: { y: { title: { display: true, text: "Precio mensual efectivo" } } },
        plugins: { legend: { position: "bottom" } },
      },
    });
  }

  const rating = data.price_rating;
  if (rating.points.length) {
    replaceChart("price-rating-chart", {
      type: "bubble",
      data: {
        datasets: rating.points.map((point) => ({
          label: `${point.label} · ${point.currency}`,
          borderColor: point.color,
          backgroundColor: `${point.color}bb`,
          data: [{ x: point.x, y: point.y, r: point.radius, reviews: point.reviews }],
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { title: { display: true, text: "Precio mensual efectivo" }, beginAtZero: true },
          y: { title: { display: true, text: "Puntuación media (1–5)" }, min: 1, max: 5 },
        },
        plugins: {
          legend: { position: "bottom" },
          tooltip: {
            callbacks: {
              label: (context) =>
                `${context.dataset.label}: ${context.raw.y} · ${context.raw.reviews} reseñas`,
            },
          },
        },
      },
    });
  }

  const sentiment = data.sentiment;
  if (sentiment.rows.length) {
    replaceChart("sentiment-chart", {
      type: "bar",
      data: {
        labels: sentiment.rows.map((row) => row.label),
        datasets: [
          { label: "Positivo", key: "positive", backgroundColor: "#2fb344" },
          { label: "Neutral", key: "neutral", backgroundColor: "#f59f00" },
          { label: "Negativo", key: "negative", backgroundColor: "#d63939" },
        ].map((series) => ({
          label: series.label,
          backgroundColor: series.backgroundColor,
          data: sentiment.rows.map((row) => row[series.key]),
        })),
      },
      options: {
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { stacked: true },
          y: {
            stacked: true,
            min: 0,
            max: 100,
            title: { display: true, text: "% de reseñas clasificadas" },
          },
        },
        plugins: { legend: { position: "bottom" } },
      },
    });
  }

  document.querySelectorAll("[data-price-period]").forEach((button) => {
    button.addEventListener("click", () => {
      const period = button.dataset.pricePeriod;
      document.querySelectorAll("[data-plan-price]").forEach((price) => {
        price.hidden = price.dataset.planPrice !== period;
      });
      document.querySelectorAll("[data-price-period]").forEach((candidate) => {
        candidate.classList.toggle("btn-primary", candidate === button);
      });
    });
  });
}

function initializeDashboardFilters() {
  const form = document.querySelector("[data-dashboard-filter-form]");
  if (!form || form.dataset.initialized === "true") return;
  form.dataset.initialized = "true";
  const preset = form.querySelector("select[name='preset']");
  const period = form.querySelector("select[name='period']");
  const providerInputs = Array.from(form.querySelectorAll("[data-dashboard-provider]"));
  const planInputs = Array.from(form.querySelectorAll("input[name='plan']"));

  const synchronizePlans = () => {
    const selectedProviders = new Set(
      providerInputs.filter((input) => input.checked).map((input) => input.value),
    );
    planInputs.forEach((input) => {
      const available = selectedProviders.has(input.dataset.providerCode);
      input.disabled = !available;
      if (!available) input.checked = false;
    });
  };
  providerInputs.forEach((input) => input.addEventListener("change", synchronizePlans));
  preset?.addEventListener("change", () => {
    const url = new URL(form.action, window.location.href);
    url.hash = "dashboard-results";
    url.search = "";
    url.searchParams.set("preset", preset.value);
    if (period?.value) url.searchParams.set("period", period.value);
    window.location.assign(url.toString());
  });
  synchronizePlans();
}

function initializeFeatureFilters() {
  document.querySelectorAll("[data-feature-filter]").forEach((panel) => {
    if (panel.dataset.initialized === "true") return;
    panel.dataset.initialized = "true";
    const summary = panel.querySelector("summary");
    const search = panel.querySelector("[data-feature-search]");
    const options = Array.from(panel.querySelectorAll("[data-feature-option]"));
    const checkboxes = options.map((option) => option.querySelector("input[type='checkbox']"));
    const count = panel.querySelector("[data-feature-count]");
    const updateCount = () => {
      const selected = checkboxes.filter((checkbox) => checkbox.checked).length;
      if (count) count.textContent = `${selected} características seleccionadas`;
    };
    const setAll = (checked) => {
      checkboxes.forEach((checkbox) => { checkbox.checked = checked; });
      updateCount();
    };
    panel.querySelector("[data-feature-select-all]")?.addEventListener("click", () => setAll(true));
    panel.querySelector("[data-feature-clear]")?.addEventListener("click", () => setAll(false));
    checkboxes.forEach((checkbox) => checkbox.addEventListener("change", updateCount));
    search?.addEventListener("input", () => {
      const query = search.value.trim().toLocaleLowerCase("es");
      options.forEach((option) => {
        option.hidden = Boolean(query) && !option.textContent.toLocaleLowerCase("es").includes(query);
      });
    });
    panel.addEventListener("toggle", () => {
      if (panel.open) search?.focus();
    });
    panel.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && panel.open) {
        panel.open = false;
        summary?.focus();
      }
    });
    updateCount();
  });
}

document.addEventListener("DOMContentLoaded", () => {
  initializeDashboard();
  initializeDashboardFilters();
  initializeFeatureFilters();
});
document.addEventListener("htmx:afterSwap", () => {
  initializeDashboard();
  initializeDashboardFilters();
  initializeFeatureFilters();
});

window.htmx = htmx;
window.Chart = Chart;
