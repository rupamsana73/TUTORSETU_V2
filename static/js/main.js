/* TutorSetu global JS: toasts, CSRF for fetch, small UX helpers. */
(function () {
    "use strict";

    // Auto-dismiss toasts after 4s
    document.querySelectorAll(".toast").forEach(function (el) {
        setTimeout(function () {
            el.classList.remove("show");
        }, 4000);
    });

    // CSRF helper for fetch() calls
    window.tsGetCsrf = function () {
        var match = document.cookie.match(/csrftoken=([^;]+)/);
        return match ? match[1] : "";
    };

    window.tsFetch = function (url, options) {
        options = options || {};
        options.headers = Object.assign(
            { "X-CSRFToken": window.tsGetCsrf() },
            options.headers || {}
        );
        options.credentials = "same-origin";
        return fetch(url, options);
    };

    // Close mobile navbar collapse on link tap
    document.querySelectorAll("#mainNav .nav-link").forEach(function (link) {
        link.addEventListener("click", function () {
            var collapse = document.getElementById("mainNav");
            if (collapse && collapse.classList.contains("show") && window.bootstrap) {
                window.bootstrap.Collapse.getOrCreateInstance(collapse).hide();
            }
        });
    });

    // Confirm buttons: data-confirm="message"
    document.querySelectorAll("[data-confirm]").forEach(function (el) {
        el.addEventListener("click", function (e) {
            if (!window.confirm(el.getAttribute("data-confirm"))) {
                e.preventDefault();
            }
        });
    });
})();
