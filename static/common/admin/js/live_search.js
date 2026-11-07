/*
 * Live search for admin list pages (#496), loaded by common.admin.LiveSearchMixin.
 *
 * Typing in the search box (after a short pause) or changing a filter
 * re-fetches the list page with the form's values and swaps in its results
 * form (table, actions, paginator) and result count.  Django's own list page
 * does the searching and filtering, so permissions, pagination, sorting and
 * actions are unchanged.  Without this script, Enter still searches.
 *
 * Elements marked data-live-keep (e.g. the Systems list's power icons, each
 * of which asks a BMC for its power state) are kept from the old results
 * when the new ones have one with the same src, so they aren't fetched again.
 */
(function () {
  'use strict';

  const DELAY_MS = 300;

  function init() {
    const searchForm = document.getElementById('changelist-search');
    if (!searchForm || !document.getElementById('changelist-form')) {
      return;
    }
    const searchBar = document.getElementById('searchbar');
    let timer = null;
    let inFlight = null;

    function queryString() {
      const params = new URLSearchParams();
      for (const [key, value] of new FormData(searchForm)) {
        // an empty search box, or a filter set back to its title, adds nothing.
        if (value !== '') {
          params.append(key, value);
        }
      }
      const qs = params.toString();
      return qs ? '?' + qs : window.location.pathname;
    }

    // swap the marked elements out of the parsed page for placeholders, so
    // importing it doesn't create (and load) them, then put the live ones back.
    function keepLiveElements(newForm) {
      const live = new Map();
      document.querySelectorAll('#changelist-form [data-live-keep]').forEach(function (el) {
        live.set(el.getAttribute('src'), el);
      });
      const kept = [];
      newForm.querySelectorAll('[data-live-keep]').forEach(function (el) {
        const old = live.get(el.getAttribute('src'));
        if (old) {
          live.delete(el.getAttribute('src'));
          const placeholder = newForm.ownerDocument.createElement('span');
          placeholder.setAttribute('data-live-placeholder', kept.length);
          el.replaceWith(placeholder);
          kept.push(old);
        }
      });
      return kept;
    }

    function swapIn(html) {
      const parsed = new DOMParser().parseFromString(html, 'text/html');
      const newForm = parsed.getElementById('changelist-form');
      const newSearch = parsed.getElementById('changelist-search');
      if (!newForm) {
        throw new Error('no results in the response');
      }
      const kept = keepLiveElements(newForm);
      const imported = document.importNode(newForm, true);
      document.getElementById('changelist-form').replaceWith(imported);
      imported.querySelectorAll('[data-live-placeholder]').forEach(function (placeholder) {
        placeholder.replaceWith(kept[Number(placeholder.getAttribute('data-live-placeholder'))]);
      });

      // the "N results (M total)" count sits in the search form, after the
      // Search button, and only while a search or filter is active.
      const oldCount = searchForm.querySelector(':scope > span.small');
      const newCount = newSearch && newSearch.querySelector(':scope > span.small');
      if (oldCount) {
        oldCount.remove();
      }
      const button = searchForm.querySelector(':scope > button[type=submit]');
      if (newCount && button) {
        button.after(document.importNode(newCount, true));
      }

      // re-attach what Django and jazzmin set up on the old results on page load.
      const checkboxes = imported.querySelectorAll('tr input.action-select');
      if (window.Actions && checkboxes.length) {
        window.Actions(checkboxes);
      }
      if (window.jQuery && window.jQuery.fn.select2) {
        window.jQuery(imported).find('.actions select').addClass('form-control').select2({width: 'element'});
      }
    }

    function refresh() {
      clearTimeout(timer);
      if (inFlight) {
        inFlight.abort();
      }
      const controller = new AbortController();
      inFlight = controller;
      const url = queryString();
      fetch(url, {signal: controller.signal, credentials: 'same-origin', headers: {'X-Requested-With': 'XMLHttpRequest'}})
        .then(function (response) {
          if (!response.ok) {
            throw new Error('HTTP ' + response.status);
          }
          return response.text();
        })
        .then(function (html) {
          if (inFlight !== controller) {
            return;  // a newer search started meanwhile.
          }
          swapIn(html);
          window.history.replaceState(null, '', url);
          inFlight = null;
        })
        .catch(function (error) {
          if (error.name === 'AbortError') {
            return;
          }
          // anything unexpected: fall back to an ordinary page load.
          window.location.href = url;
        });
    }

    if (searchBar) {
      searchBar.setAttribute('autocomplete', 'off');
      searchBar.addEventListener('input', function () {
        clearTimeout(timer);
        timer = setTimeout(refresh, DELAY_MS);
      });
    }
    searchForm.addEventListener('submit', function (event) {
      event.preventDefault();
      refresh();
    });
    // jazzmin's filters are select2 boxes, which fire jQuery change events.
    // Its own change handler names the select after the chosen option, so
    // let it run first.
    const onFilterChange = function () {
      setTimeout(refresh, 0);
    };
    if (window.jQuery) {
      window.jQuery(searchForm).on('change', 'select', onFilterChange);
    } else {
      searchForm.addEventListener('change', onFilterChange);
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
