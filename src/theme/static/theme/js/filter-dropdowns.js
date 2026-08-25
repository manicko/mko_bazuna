(function () {
    'use strict';

    /*
     * Filter dropdowns (e.g. the Features floating checkbox panel).
     *
     * The filter form partial (filter_form.html) is destroyed and recreated on
     * every HTMX innerHTML swap of #ad-list, so per-element addEventListener
     * calls attached at init-time would be lost. Instead we use document-level
     * event delegation — the listeners live on `document` and survive re-renders.
     */

    /** Close every open data-filter-trigger panel. */
    function closeAllPanels() {
        var triggers = document.querySelectorAll('[data-filter-trigger]');
        triggers.forEach(function (trigger) {
            var toggle = trigger.querySelector('[data-filter-toggle]');
            var panel = trigger.querySelector('[data-filter-panel]');
            if (toggle) {
                toggle.setAttribute('aria-expanded', 'false');
            }
            if (panel) {
                panel.classList.add('hidden');
            }
        });
    }

    /** Click delegation: toggle panel on trigger, close on outside click. */
    document.addEventListener('click', function (e) {
        var toggle = e.target.closest('[data-filter-toggle]');
        var trigger = e.target.closest('[data-filter-trigger]');

        if (!trigger) {
            /* Clicked outside every trigger — close all panels. */
            closeAllPanels();
            return;
        }

        if (toggle) {
            e.preventDefault();
            var panel = toggle.closest('[data-filter-trigger]')
                .querySelector('[data-filter-panel]');
            var isOpen = panel && !panel.classList.contains('hidden');

            /* Close any other open panel first. */
            closeAllPanels();

            if (panel && !isOpen) {
                panel.classList.remove('hidden');
                toggle.setAttribute('aria-expanded', 'true');
                var svg = toggle.querySelector('svg');
                if (svg) {
                    svg.classList.add('rotate-180');
                }
            }
        }
    });

    /** Escape key closes any open panel. */
    document.addEventListener('keydown', function (e) {
        if (e.key === 'Escape') {
            closeAllPanels();
        }
    });

    /* Ensure panels start hidden on load. */
    closeAllPanels();
})();
