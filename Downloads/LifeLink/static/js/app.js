/* LifeLink interaction layer: navigation, reveal, meters, copy, tooltips. */
(function () {
  "use strict";

  document.addEventListener("DOMContentLoaded", function () {
    /* Mobile navigation */
    var navToggle = document.querySelector("[data-nav-toggle]");
    var mobileNav = document.getElementById("mobileNav");
    if (navToggle && mobileNav) {
      navToggle.addEventListener("click", function () {
        var open = mobileNav.classList.toggle("is-open");
        navToggle.setAttribute("aria-expanded", open ? "true" : "false");
        navToggle.innerHTML = open
          ? '<i class="bi bi-x-lg"></i>'
          : '<i class="bi bi-list"></i>';
      });
    }

    /* Scroll reveal */
    var revealables = document.querySelectorAll("[data-reveal]");
    if (revealables.length) {
      if ("IntersectionObserver" in window) {
        var observer = new IntersectionObserver(
          function (entries) {
            entries.forEach(function (entry, index) {
              if (entry.isIntersecting) {
                var delay = Number(entry.target.getAttribute("data-reveal-delay") || 0);
                setTimeout(function () {
                  entry.target.classList.add("is-revealed");
                }, delay || index * 40);
                observer.unobserve(entry.target);
              }
            });
          },
          { rootMargin: "0px 0px -60px 0px", threshold: 0.08 }
        );
        revealables.forEach(function (element) {
          observer.observe(element);
        });
      } else {
        revealables.forEach(function (element) {
          element.classList.add("is-revealed");
        });
      }
    }

    /* Meters carry their value in a data attribute so CSS stays declarative */
    document.querySelectorAll("[data-meter]").forEach(function (element) {
      var value = Math.max(0, Math.min(100, Number(element.getAttribute("data-meter")) || 0));
      element.style.width = value + "%";
    });

    document.querySelectorAll("[data-bar]").forEach(function (element) {
      var value = Math.max(0, Math.min(100, Number(element.getAttribute("data-bar")) || 0));
      element.style.height = value + "%";
    });

    /* Copy to clipboard */
    document.querySelectorAll("[data-copy]").forEach(function (button) {
      button.addEventListener("click", function () {
        var value = button.getAttribute("data-copy");
        var label = button.innerHTML;
        function done() {
          button.innerHTML = '<i class="bi bi-check2"></i> Copied';
          setTimeout(function () {
            button.innerHTML = label;
          }, 1800);
        }
        if (navigator.clipboard && navigator.clipboard.writeText) {
          navigator.clipboard.writeText(value).then(done);
        } else {
          var field = document.createElement("textarea");
          field.value = value;
          document.body.appendChild(field);
          field.select();
          try {
            document.execCommand("copy");
            done();
          } catch (error) {
            /* clipboard unavailable */
          }
          document.body.removeChild(field);
        }
      });
    });

    /* Bootstrap tooltips */
    if (window.bootstrap && window.bootstrap.Tooltip) {
      document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach(function (element) {
        new window.bootstrap.Tooltip(element, { trigger: "hover focus" });
      });
    }

    /* Print buttons (camp tickets) */
    document.querySelectorAll("[data-print]").forEach(function (button) {
      button.addEventListener("click", function () {
        window.print();
      });
    });

    /* Confirmation prompts for destructive actions */
    document.querySelectorAll("[data-confirm]").forEach(function (form) {
      form.addEventListener("submit", function (event) {
        if (!window.confirm(form.getAttribute("data-confirm"))) {
          event.preventDefault();
        }
      });
    });
  });
})();
