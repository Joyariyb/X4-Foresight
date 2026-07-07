  // Core role: App-wide Help hub — builds the topic list and landing cards from
  // the help-topic sections in body.html and swaps between them inside tab-help.

  window.Help = (function () {
    // The DOM is the topic registry (see the tab-help comment in body.html):
    // the TOC and hub grid are derived from the sections' data-help-* attrs,
    // so adding a topic is one new <section> there — no list here to sync.
    let _built = false;
    let _topic = null;   // active section id; null = the hub landing view

    function _sections() {
      return Array.from(document.querySelectorAll('#tab-help .help-topic'));
    }

    function _build() {
      // data-topic="" on the hub entry (vs a section id) lets one dataset
      // comparison in open() drive the active highlight for both cases.
      let toc = '<div class="help-toc-item" data-topic="" onclick="Help.open()">'
              + '<i class="ti ti-layout-grid"></i> All topics</div>';
      let cards = '';
      let group = null;
      for (const sec of _sections()) {
        const g = sec.dataset.helpGroup || 'Other';
        if (g !== group) {
          toc += `<div class="help-toc-group">${g}</div>`;
          group = g;
        }
        toc += `<div class="help-toc-item" data-topic="${sec.id}" onclick="Help.open('${sec.id}')">`
             + `<i class="ti ${sec.dataset.helpIcon}"></i> ${sec.dataset.helpTitle}</div>`;
        cards += `<div class="help-hub-card" onclick="Help.open('${sec.id}')">`
               + `<div class="help-hub-card-head"><i class="ti ${sec.dataset.helpIcon}"></i>`
               + `<span>${sec.dataset.helpTitle}</span></div>`
               + `<p>${sec.dataset.helpBlurb || ''}</p></div>`;
      }
      document.getElementById('help-toc').innerHTML = toc;
      document.getElementById('help-hub-grid').innerHTML = cards;
      _built = true;
    }

    // No topicId → the hub landing view. This only swaps views; callers that
    // want a Back trail wrap it in _navRecord()/_navAfterJump() the same way
    // the other jump links do (see openHelp() in advisors-feed.js).
    function open(topicId) {
      if (!_built) _build();
      _topic = topicId || null;
      document.getElementById('help-hub').style.display = _topic ? 'none' : '';
      _sections().forEach(sec => sec.classList.toggle('active', sec.id === _topic));
      document.querySelectorAll('#help-toc .help-toc-item').forEach(el =>
        el.classList.toggle('active', (el.dataset.topic || null) === _topic));
      switchTab('help', null);
      // Topics share #content's scroll position, so a long previous topic
      // must not leave the next one opened mid-page. goBack()'s scroll restore
      // still wins — it reapplies its snapshot a frame later.
      const content = document.getElementById('content');
      if (content) content.scrollTop = 0;
    }

    // Lets navigation.js snapshot the open topic so Back can land on it.
    function currentTopic() { return _topic; }

    return { open, currentTopic };
  })();
