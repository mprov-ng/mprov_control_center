/*
 * The member-system chips on System Groups and Physical Disk Layouts (#497),
 * for systems.member_widget.SystemMembersWidget.
 *
 * The posted value is the hidden input: member IDs, comma-separated.  This
 * script keeps a list of {id, hostname}, draws the first chips from it, and
 * writes the IDs back to the input on every change.  Django's lookup popup
 * appends an ID to the input and fires a jQuery change event; new IDs are
 * looked up through the admin lookup URL for their hostnames.
 */
(function () {
  'use strict';

  function csrfToken() {
    const input = document.querySelector('input[name=csrfmiddlewaretoken]');
    if (input) {
      return input.value;
    }
    const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return match ? decodeURIComponent(match[1]) : '';
  }

  function lookup(url, params) {
    const body = new URLSearchParams(params);
    return fetch(url, {
      method: 'POST',
      credentials: 'same-origin',
      headers: {'X-CSRFToken': csrfToken(), 'X-Requested-With': 'XMLHttpRequest'},
      body: body,
    }).then(function (response) {
      if (!response.ok) {
        throw new Error('The lookup failed (HTTP ' + response.status + ').');
      }
      return response.json();
    });
  }

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) {
      node.className = className;
    }
    if (text !== undefined) {
      node.textContent = text;
    }
    return node;
  }

  function modal(node) {
    return window.bootstrap ? window.bootstrap.Modal.getOrCreateInstance(node) : null;
  }

  function setup(root) {
    const input = document.getElementById(root.dataset.input);
    const url = root.dataset.lookupUrl;
    const shown = Number(root.dataset.chipsShown) || 50;
    const chips = root.querySelector('.system-members-chips');
    const allModal = root.querySelector('.system-members-all-modal');
    const manyModal = root.querySelector('.system-members-many-modal');
    const list = allModal.querySelector('.system-members-list');
    const filter = allModal.querySelector('.system-members-filter');
    const paste = manyModal.querySelector('.system-members-paste');
    const result = manyModal.querySelector('.system-members-result');
    const addButton = manyModal.querySelector('.system-members-add');
    let members = JSON.parse(document.getElementById(root.dataset.members).textContent);
    // inside the change form's card a modal ends up under its backdrop, so
    // move both to <body>.  Their fields have no name, so nothing they hold
    // is posted with the form.
    document.body.appendChild(allModal);
    document.body.appendChild(manyModal);
    let pending = [];

    function label(member) {
      return member.hostname === null || member.hostname === undefined ? '#' + member.id + ' (not found)' : member.hostname;
    }

    function chip(member) {
      const node = el('span', 'system-member badge', label(member));
      node.dataset.id = member.id;
      const remove = el('button', 'system-member-remove', '×');
      remove.type = 'button';
      remove.title = 'Remove ' + label(member);
      remove.setAttribute('aria-label', remove.title);
      remove.addEventListener('click', function () {
        removeIds([member.id]);
      });
      node.appendChild(remove);
      return node;
    }

    function drawList() {
      const wanted = filter.value.trim().toLowerCase();
      list.replaceChildren();
      members.filter(function (m) {
        return !wanted || label(m).toLowerCase().includes(wanted);
      }).forEach(function (member) {
        const item = el('li', 'list-group-item', label(member));
        const remove = el('button', 'btn btn-sm btn-link text-danger', 'Remove');
        remove.type = 'button';
        remove.addEventListener('click', function () {
          removeIds([member.id]);
        });
        item.appendChild(remove);
        list.appendChild(item);
      });
      allModal.querySelector('.system-members-count').textContent = members.length;
    }

    // by hostname, numbers in order (c2 before c10), unknown IDs last, as
    // member_widget.natural_key does.
    const collator = new Intl.Collator(undefined, {numeric: true, sensitivity: 'base'});
    function sortMembers() {
      members.sort(function (a, b) {
        const an = a.hostname === null || a.hostname === undefined;
        const bn = b.hostname === null || b.hostname === undefined;
        if (an !== bn) {
          return an ? 1 : -1;
        }
        return an ? a.id - b.id : collator.compare(a.hostname, b.hostname) || a.id - b.id;
      });
    }

    function draw() {
      sortMembers();
      input.value = members.map(function (m) { return m.id; }).join(',');
      chips.replaceChildren();
      if (!members.length) {
        chips.appendChild(el('span', 'system-members-none text-muted', 'No systems.'));
      }
      members.slice(0, shown).forEach(function (member) {
        chips.appendChild(chip(member));
      });
      if (members.length > shown) {
        const more = el('a', 'system-members-more', '… and ' + (members.length - shown) + ' more — show all');
        more.href = '#';
        more.addEventListener('click', function (event) {
          event.preventDefault();
          filter.value = '';
          drawList();
          const m = modal(allModal);
          if (m) {
            m.show();
          }
        });
        chips.appendChild(more);
      }
      if (allModal.classList.contains('show')) {
        drawList();
      }
    }

    function removeIds(ids) {
      const gone = new Set(ids.map(String));
      members = members.filter(function (m) { return !gone.has(String(m.id)); });
      draw();
    }

    function addMembers(found) {
      const have = new Set(members.map(function (m) { return String(m.id); }));
      found.forEach(function (m) {
        if (!have.has(String(m.id))) {
          have.add(String(m.id));
          members.push(m);
        }
      });
      draw();
    }

    // Django's lookup popup changed the input: pick up added (or removed) IDs.
    function inputChanged() {
      const ids = input.value.split(',').map(function (s) { return s.trim(); }).filter(Boolean);
      const known = new Map(members.map(function (m) { return [String(m.id), m]; }));
      const missing = ids.filter(function (id) { return !known.has(id); });
      const keep = ids.filter(function (id) { return known.has(id); }).map(function (id) { return known.get(id); });
      members = keep;
      if (!missing.length) {
        draw();
        return;
      }
      lookup(url, {ids: missing.join(',')}).then(function (data) {
        addMembers(data.found);
        data.not_found.forEach(function (id) {
          if (/^\d+$/.test(id)) {
            members.push({id: Number(id), hostname: null});
          }
        });
        draw();
      }).catch(function (error) {
        window.alert(error.message);
        draw();
      });
    }
    if (window.jQuery) {
      window.jQuery(input).on('change', inputChanged);
    } else {
      input.addEventListener('change', inputChanged);
    }

    filter.addEventListener('input', drawList);
    // the modals sit inside the change form: Enter in the filter box mustn't submit it.
    filter.addEventListener('keydown', function (event) {
      if (event.key === 'Enter') {
        event.preventDefault();
      }
    });
    allModal.querySelector('.system-members-remove-all').addEventListener('click', function () {
      members = [];
      draw();
    });

    root.querySelector('.system-members-add-many').addEventListener('click', function () {
      paste.value = '';
      result.replaceChildren();
      pending = [];
      addButton.disabled = true;
      addButton.textContent = 'Add';
      const m = modal(manyModal);
      if (m) {
        m.show();
      }
    });
    paste.addEventListener('input', function () {
      pending = [];
      addButton.disabled = true;
      addButton.textContent = 'Add';
    });
    manyModal.querySelector('.system-members-find').addEventListener('click', function () {
      result.replaceChildren(el('span', 'text-muted', 'Looking them up…'));
      lookup(url, {text: paste.value}).then(function (data) {
        result.replaceChildren();
        if (data.error) {
          result.appendChild(el('div', 'not-found', data.error));
          return;
        }
        const have = new Set(members.map(function (m) { return String(m.id); }));
        pending = data.found.filter(function (m) { return !have.has(String(m.id)); });
        const already = data.found.length - pending.length;
        let summary = 'Found ' + data.found.length + ' system' + (data.found.length === 1 ? '' : 's') + '.';
        if (already) {
          summary += ' ' + already + ' already listed.';
        }
        result.appendChild(el('div', '', summary));
        if (data.not_found.length) {
          result.appendChild(el('div', 'not-found', 'Not found: ' + data.not_found.join(', ')));
        }
        addButton.disabled = !pending.length;
        addButton.textContent = pending.length ? 'Add ' + pending.length : 'Add';
      }).catch(function (error) {
        result.replaceChildren(el('div', 'not-found', error.message));
      });
    });
    addButton.addEventListener('click', function () {
      addMembers(pending);
      pending = [];
      const m = modal(manyModal);
      if (m) {
        m.hide();
      }
    });

    draw();
  }

  function init() {
    document.querySelectorAll('.system-members').forEach(setup);
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', init);
  } else {
    init();
  }
})();
