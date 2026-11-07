'use strict';
const $ = id => document.getElementById(id);
const state = {workspace: null, items: [], changes: [], item: null, view: 'library'};
function el(tag, text, cls) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (cls) node.className = cls;
  return node;
}
function screen(title, message) {
  document.querySelectorAll('#selection-tools, #passage-ask, #resume-passage').forEach(node => node.remove());
  $('content').replaceChildren(el('h1', title), el('p', message));
  closeNavigation();
  window.scrollTo(0, 0);
}
async function api(path, options = {}) {
  let response;
  try {
    response = await fetch('/api' + path, {credentials: 'same-origin', ...options,
      headers: {'Content-Type': 'application/json', ...options.headers}});
  } catch {
    throw new Error('The local workspace could not be reached. Your input is preserved. Retry, or reopen Knowledge Hub if the app has closed.');
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    const code = typeof data.error === 'string' ? data.error : data.error?.code;
    const error = new Error(code || (response.status === 422 ? 'Check the required fields and try again.' : `Request failed (${response.status}). Try again.`));
    error.status = response.status;
    throw error;
  }
  return data;
}
async function start() {
  const destination = location.search;
  restoringRoute = true;
  restoreCaptureDrafts();
  const fragment = new URLSearchParams(location.hash.slice(1));
  const token = fragment.get('token');
  if (location.hash) history.replaceState(null, '', location.pathname + location.search);
  try {
    if (token) await api('/session', {method: 'POST', headers: {Authorization: 'Bearer ' + token}});
    await refreshWorkspace();
    await openLibrary();
    restoringRoute = false;
    await restoreReadingRoute(destination);
  } catch (error) {
    screen(error.status === 401 ? 'Open Knowledge Hub from the desktop app' : 'Could not open your workspace',
      error.status === 401 ? 'Close this window and launch the installed Knowledge Hub app to connect securely.' : error.message + ' Reopen the desktop app to retry.');
  }
}
function button(text, action, cls) {
  const node = el('button', text, cls);
  node.type = 'button';
  node.addEventListener('click', async () => { try { await action(); } catch (error) { showError(error); } });
  return node;
}
function iconButton(label, kind, action, cls = '') {
  const node = button('', action, 'icon-button ' + cls);
  node.setAttribute('aria-label', label);
  node.title = label;
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  for (const [key, value] of Object.entries({viewBox: '0 0 24 24', width: '20', height: '20', fill: 'none', stroke: 'currentColor', 'stroke-width': '1.7', 'stroke-linecap': 'round', 'stroke-linejoin': 'round', 'aria-hidden': 'true'})) svg.setAttribute(key, value);
  const path = document.createElementNS(svg.namespaceURI, 'path');
  path.setAttribute('d', {attach: 'M8 12.5 14.5 6a3.2 3.2 0 0 1 4.5 4.5l-8 8A5 5 0 0 1 4 11.4l8-8', send: 'M12 19V5m-6 6 6-6 6 6', remove: 'm6 6 12 12M18 6 6 18', close: 'm6 6 12 12M18 6 6 18'}[kind]);
  svg.append(path); node.append(svg);
  return node;
}
function showError(error) {
  const descriptions = {
    request_context_stale: 'The page changed before this request was saved. Your draft, attachments and original passage are preserved. Copy any text you need, clear this draft, then reopen Library and select the latest passage.',
    invalid_request_context: 'The passage no longer matches this page and section. Your draft is preserved. Clear it and select a passage from the current Library page.',
    stale_revision: 'The workspace changed since this proposal was prepared. Reject this proposal and prepare a new change from the latest revision.',
    revision_conflict: 'The workspace changed since this proposal was prepared. Reject this proposal and prepare a new change from the latest revision.',
    authentication_required: 'Your session has ended. Reopen Knowledge Hub from the desktop app.',
    provider_http_error: 'The provider rejected the connection check. Verify your sign-in, model and account entitlement, then retry. Processing remains disabled.',
  };
  $('notice').textContent = descriptions[error.message] || error.message;
  $('notice').hidden = false;
  $('status').textContent = $('notice').textContent;
}
function clearError() { $('notice').hidden = true; }
function field(form, label, name, value = '', type = 'input') {
  const wrapper = el('label', label);
  const input = el(type);
  input.name = name;
  input.setAttribute('aria-label', label);
  input.value = value;
  if (type === 'input') input.type = 'text';
  wrapper.append(input);
  form.append(wrapper);
  return input;
}
function path(suffix = '') {
  if (suffix.startsWith('/knowledge')) return suffix.replace('/knowledge', '/warehouse');
  if (suffix.startsWith('/books') || suffix.startsWith('/pages')) return '/library' + suffix;
  return suffix;
}
let viewVersion = 0;
async function refreshWorkspace() {
  const [workspace, knowledge, changes] = await Promise.all([api('/workspace'), api('/warehouse'), api('/changes')]);
  state.workspace = workspace;
  state.items = knowledge.items;
  state.changes = changes.changes;
  $('revision').textContent = 'Revision ' + workspace.revision;
  $('add-topic').disabled = false;
  updateCount();
}
function propose(item = null) {
  clearError();
  screen(item ? 'Propose a change' : 'Add a topic', 'Prepare a structured proposal. Nothing changes until you approve it in review.');
  const form = el('form');
  const title = field(form, 'Title', 'title', item?.title || '');
  title.required = true;
  title.maxLength = 500;
  const kind = field(form, 'Kind', 'kind', '', 'select');
  for (const value of ['fact', 'finding', 'concept', 'procedure', 'decision', 'question']) {
    const option = el('option', value[0].toUpperCase() + value.slice(1));
    option.value = value;
    kind.append(option);
  }
  kind.value = item?.kind || 'fact';
  const body = field(form, 'Body', 'body', item?.body || '', 'textarea');
  body.rows = 9;
  body.maxLength = 100000;
  const summary = field(form, 'Change summary', 'summary', item ? 'Update ' + item.title : '');
  summary.placeholder = 'What changed and why? (defaults to the title)';
  const evidenceSection = el('fieldset');
  evidenceSection.append(el('legend', 'Supporting evidence'));
  evidenceSection.append(el('p', 'Existing evidence is preserved. Add a source or record your decision.', 'muted'));
  const evidenceKind = field(evidenceSection, 'Evidence kind', 'evidence_kind', '', 'select');
  for (const [value, label] of [['user_decision', 'User decision'], ['document', 'Document'], ['observation', 'Observation']]) {
    const option = el('option', label);
    option.value = value;
    evidenceKind.append(option);
  }
  const sourceLabel = field(evidenceSection, 'Source label', 'source_label');
  sourceLabel.maxLength = 1000;
  const sourceLocator = field(evidenceSection, 'Source locator', 'source_locator');
  sourceLocator.maxLength = 4000;
  sourceLocator.placeholder = 'Optional URL, document path or decision reference';
  form.append(evidenceSection);
  const dependencies = el('fieldset');
  dependencies.append(el('legend', 'Depends on'));
  dependencies.append(el('p', 'Register the topics this knowledge relies on. Only registered relationships can be assessed.', 'muted'));
  const dependencyInputs = [];
  for (const candidate of state.items.filter(candidate => candidate.id !== item?.id)) {
    const label = el('label', undefined, 'check-label');
    const input = el('input');
    input.type = 'checkbox';
    input.value = candidate.id;
    input.checked = (item?.depends_on || []).includes(candidate.id);
    label.append(input, el('span', candidate.title));
    dependencyInputs.push(input);
    dependencies.append(label);
  }
  if (!dependencyInputs.length) dependencies.append(el('p', 'No other topics in the shared workspace.', 'muted'));
  form.append(dependencies);
  const submit = el('button', 'Preview proposal', 'primary');
  submit.type = 'submit';
  const actions = el('div', undefined, 'actions');
  actions.append(submit, button('Cancel', () => item ? renderItem(item) : openLibrary()));
  form.append(actions);
  const baseRevision = state.workspace.revision;
  const idempotencyKey = crypto.randomUUID();
  form.addEventListener('submit', async event => {
    event.preventDefault();
    clearError();
    submit.disabled = true;
    try {
      const evidence = [...(item?.evidence || [])];
      if (sourceLabel.value.trim() || sourceLocator.value.trim() || !evidence.length) evidence.push({
        kind: evidenceKind.value, locator: sourceLocator.value.trim(), label: sourceLabel.value.trim() || 'Owner-proposed knowledge'});
      const operation = {op: 'upsert', title: title.value.trim(), body: body.value, kind: kind.value,
        evidence, depends_on: dependencyInputs.filter(input => input.checked).map(input => input.value)};
      if (item) operation.id = item.id;
      const change = await api(path('/changes'), {method: 'POST', body: JSON.stringify({
        base_revision: baseRevision, idempotency_key: idempotencyKey, summary: summary.value.trim() || title.value.trim(), operations: [operation]})});
      state.changes = (await api(path('/changes'))).changes;
      updateCount();
      renderChange(change);
    } catch (error) { showError(error); submit.disabled = false; }
  });
  $('content').append(form);
  title.focus();
}
function updateCount() {
  const count = [...state.changes, ...(state.libraryChanges || [])].filter(change => change.status === 'pending').length;
  $('review-count').textContent = count || '';
}
function renderItem(item) {
  clearError();
  if (!['warehouse', 'attention'].includes(state.view)) { setView('warehouse'); renderTopics(state.items); }
  state.item = item;
  $('content').replaceChildren();
  const article = el('article');
  article.append(el('h1', item.title));
  const metadata = el('div', undefined, 'metadata');
  metadata.append(el('span', item.kind), el('span', ({current: 'Current', needs_review: 'Needs review', unresolved: 'Unresolved'})[item.state] || item.state, 'state ' + item.state), el('span', 'Revision ' + item.revision));
  article.append(metadata, button('Propose a change', () => propose(item)), el('div', item.body, 'prose'));
  article.append(el('h2', 'Evidence'));
  if (!item.evidence?.length) article.append(el('p', 'No evidence registered.', 'muted'));
  for (const evidence of item.evidence || []) {
    const source = el('p', undefined, 'source');
    let url;
    try { url = new URL(evidence.locator); } catch { /* Plain local locator. */ }
    if (url && ['http:', 'https:'].includes(url.protocol)) {
      const link = el('a', evidence.label || evidence.locator);
      link.href = url.href;
      link.target = '_blank';
      link.rel = 'noopener noreferrer';
      source.append(link);
    } else source.append(el('span', evidence.label || evidence.kind), el('span', evidence.locator, 'locator'));
    article.append(source);
  }
  $('content').append(article);
  closeNavigation();
  window.scrollTo(0, 0);
  $('status').textContent = 'Reading ' + item.title;
}
function previewRecord(record) {
  const block = el('div');
  block.append(el('p', 'Title: ' + record.title, 'muted'), el('p', 'Kind: ' + record.kind, 'muted'), el('div', record.body, 'prose'));
  const list = el('ul', undefined, 'muted');
  for (const evidence of record.evidence || []) list.append(el('li', `${evidence.label} — ${evidence.locator || 'no locator'} (${evidence.kind})`));
  if (list.childNodes.length) block.append(el('h3', 'Evidence'), list);
  else block.append(el('p', 'No evidence registered.', 'muted'));
  const names = (record.depends_on || []).map(id => state.items.find(item => item.id === id)?.title || id);
  block.append(el('p', 'Depends on: ' + (names.join(', ') || 'No registered topics'), 'muted'));
  return block;
}
function renderChange(change) {
  closeUtility();
  clearError();
  setView('reviews');
  renderTopics(state.items);
  screen('Review proposed change', change.summary);
  $('content').append(el('p', 'Base revision ' + change.base_revision + ' · ' + change.status, 'muted'));
  for (const operation of change.operations) {
    const old = state.items.find(item => item.id === operation.id);
    const section = el('section', undefined, 'comparison');
    section.append(el('h2', operation.title), el('h3', 'Before'));
    if (old) section.append(previewRecord(old));
    else section.append(el('p', 'New topic — no accepted content yet.', 'muted'));
    section.append(el('h3', 'After'), previewRecord(operation));
    $('content').append(section);
  }
  $('content').append(el('h2', 'Registered impact'));
  const ids = change.impact?.review_required_ids || [];
  if (!ids.length) $('content').append(el('p', 'No registered dependent topics require review. Unregistered relationships are not assessed.', 'muted'));
  else {
    const list = el('ul');
    for (const id of ids) list.append(el('li', (state.items.find(item => item.id === id)?.title || id) + ' — needs review'));
    $('content').append(list);
  }
  if (change.status !== 'pending') return;
  const actions = el('div', undefined, 'actions');
  const captureIds = [...new Set(change.operations.filter(operation => !state.items.some(item => item.id === operation.id)).flatMap(operation => (operation.evidence || []).map(evidence => /^capture:([a-f0-9-]{36})#[a-f0-9]{64}$/.exec(evidence.locator)?.[1]).filter(Boolean)))];
  const retain = el('input'); retain.type = 'checkbox';
  if (captureIds.length) {
    const label = el('label', undefined, 'check-label');
    label.append(retain, el('span', 'Keep original capture until its expiry'));
    $('content').append(el('p', 'Original captures are removed when the review workflow is complete. After Warehouse approval, suggested pages remain available for Library arrangement and review, or explicit dismissal. Deletion does not erase filesystem backups.', 'muted'), label);
  }
  const resource = path();
  const decide = async decision => {
    const decisionVersion = viewVersion;
    clearError();
    for (const btn of actions.querySelectorAll('button')) btn.disabled = true;
    try {
      await api(resource + '/changes/' + encodeURIComponent(change.id) + '/' + decision, {method: 'POST'});
      const verified = await api(resource + '/changes');
      if (verified.changes.find(candidate => candidate.id === change.id)?.status !== (decision === 'approve' ? 'approved' : 'rejected')) throw new Error('Decision could not be verified. Reopen review before retrying.');
      let cleanupError = null;
      let arrangement = null;
      for (const id of captureIds) {
        try {
          const capture = await api(resource + '/captures/' + encodeURIComponent(id));
          if (decision === 'approve' && capture.result?.library_suggestions.length) arrangement = capture;
          else await finishCapture(resource + '/captures/' + encodeURIComponent(id), retain.checked);
        } catch (error) { if (error.status !== 404) cleanupError = error; }
      }
      // Read back canonical state after the write; never infer acceptance from the POST alone.
      await refreshWorkspace();
      if (decisionVersion === viewVersion) {
        const library = openLibrary();
        const readerVersion = viewVersion;
        await library;
        if (readerVersion === viewVersion) {
          if (arrangement) { await arrangeCapture(arrangement, retain.checked); return; }
          if (decision === 'approve' && state.items.length) {
            const changed = change.operations[0];
            const item = state.items.find(item => item.id === changed.id) || state.items.find(item => item.title === changed.title);
            if (item) {
              const current = await api(path('/knowledge/' + encodeURIComponent(item.id)));
              if (readerVersion === viewVersion) renderItem(current);
            }
          }
        }
      }
      $('status').textContent = decision === 'approve' ? 'Change approved' : 'Change rejected';
      if (cleanupError) showError(new Error('Your decision was saved, but original capture cleanup could not be verified. Open Add knowledge and discard the saved capture.'));
    } catch (error) {
      showError(error);
      for (const btn of actions.querySelectorAll('button')) btn.disabled = false;
    }
  };
  actions.append(button('Approve change', () => decide('approve'), 'primary'), button('Reject change', () => decide('reject')));
  $('content').append(actions);
}
const stateLabel = value => ({current: 'Current', needs_review: 'Needs review', unresolved: 'Unresolved'})[value] || value;
function renderTopics(items) {
  $('topics').replaceChildren();
  if (!items.length) $('topics').append(el('p', $('search').value ? 'No topics match your search.' : 'No topics yet.', 'muted'));
  for (const item of items) {
    const row = button('', async () => {
      const version = viewVersion;
      const result = await api(path('/knowledge/' + encodeURIComponent(item.id)));
      if (version !== viewVersion) return;
      renderItem(result);
      for (const other of $('topics').querySelectorAll('button')) other.removeAttribute('aria-current');
      row.setAttribute('aria-current', 'page');
    }, 'topic');
    row.append(el('span', item.title), el('small', item.kind + ' · ' + stateLabel(item.state)));
    $('topics').append(row);
  }
}
let searchVersion = 0;
$('search').addEventListener('input', async () => {
  const version = ++searchVersion;
  if (state.view === 'library') { renderLibraryIndex(); return; }
  try {
    const result = await api(path('/knowledge?q=' + encodeURIComponent($('search').value)));
    if (version === searchVersion) {
      renderTopics(state.view === 'attention' ? result.items.filter(item => item.state !== 'current') : result.items);
      $('status').textContent = result.items.length + ' matching topics';
    }
  } catch (error) { if (version === searchVersion) showError(error); }
});
document.addEventListener('keydown', event => {
  if ((event.metaKey || event.ctrlKey) && event.key.toLowerCase() === 'k' && state.workspace) {
    event.preventDefault();
    const search = $('content').querySelector('.search-control input[type="search"]') || $('library-search') || $('search');
    const panel = search.closest('[popover]');
    if (panel && !panel.matches(':popover-open')) panel.showPopover();
    search.focus();
    search.select();
  }
});
async function readView(attention = false) {
  clearError();
  const view = attention ? 'attention' : 'warehouse';
  setView(view);
  const version = viewVersion;
  $('search').value = '';
  const result = await api(path('/knowledge'));
  if (version !== viewVersion || state.view !== view) return;
  state.items = result.items;
  screen(attention ? 'Needs attention' : 'Warehouse', attention ? 'Facts with registered uncertainty or changes that need review.' : 'Shared granular facts and their evidence. Books reference these records without duplicating them. Select a fact to inspect it.');
  const search = el('input'); search.type = 'search'; search.setAttribute('aria-label', 'Search Warehouse');
  search.placeholder = 'Find a fact, finding or question';
  const grid = el('div'); grid.id = 'warehouse-results'; grid.setAttribute('role', 'list');
  const render = () => {
    grid.replaceChildren();
    const query = search.value.toLocaleLowerCase();
    const items = state.items.filter(item => (!attention || item.state !== 'current') && (item.title + ' ' + item.body).toLocaleLowerCase().includes(query));
    for (const item of items) {
      const wrapper = el('div'); wrapper.setAttribute('role', 'listitem');
      const card = button('', async () => {
        const current = await api('/warehouse/' + encodeURIComponent(item.id));
        if (version === viewVersion) renderItem(current);
      }, 'warehouse-card');
      card.setAttribute('aria-label', item.title);
      card.append(el('small', item.kind + ' · ' + stateLabel(item.state)), el('h2', item.title), el('p', item.body.slice(0, 240)), el('small', (item.evidence?.length || 0) + ' evidence references'));
      wrapper.append(card); grid.append(wrapper);
    }
    if (!items.length) grid.append(el('p', query ? 'No topics match your search.' : 'No knowledge saved yet.', 'muted'));
  };
  search.addEventListener('input', render); render();
  $('content').append(searchControl(search, 'Search Warehouse'), grid, button('Advanced: add fact', () => propose()));
  if (attention && !state.items.some(item => item.state !== 'current')) $('topics').replaceChildren(el('p', 'No topics need attention.', 'muted'));
}
async function reviewsView() {
  clearError();
  setView('reviews');
  screen('Activity', 'Loading saved work and proposed changes…');
  const version = viewVersion;
  const [changes, knowledge, libraryChanges, captures, jobs] = await Promise.all([api(path('/changes')), api(path('/knowledge')), api(path('/library/changes')).catch(error => ({error})), api('/captures'), api('/curator-jobs')]);
  const saved = await Promise.all(captures.captures.map(capture => api('/captures/' + encodeURIComponent(capture.id))));
  if (version !== viewVersion || state.view !== 'reviews') return;
  state.changes = changes.changes;
  state.libraryChanges = libraryChanges.changes || [];
  state.items = knowledge.items;
  renderTopics(state.items);
  updateCount();
  screen('Activity', 'Saved work and changes awaiting your review.');
  $('content').append(el('h2', 'Curator work'));
  if (!jobs.jobs.length) $('content').append(el('p', 'No Curator jobs.', 'muted'));
  for (const job of jobs.jobs) {
    const row = button('Open Curator work ' + job.id.slice(0, 8), () => {
      closeUtility(); inspectCuratorJob(job);
    }, 'review-row');
    row.setAttribute('aria-label', 'Open Curator work ' + job.id.slice(0, 8));
    row.append(el('small', job.status.replaceAll('_', ' ')));
    $('content').append(row);
  }
  $('content').append(el('h2', 'Saved captures'));
  if (!saved.length) $('content').append(el('p', 'No saved captures.', 'muted'));
  for (const capture of saved) {
    const row = button('Review saved capture ' + capture.id.slice(0, 8), () => {
      closeUtility();
      setView('intake');
      inspectCapture(capture).catch(showError);
      savedCaptures().catch(showError);
    }, 'review-row');
    row.append(el('small', captureState(capture)));
    $('content').append(row);
  }
  $('content').append(el('h2', 'Human review'));
  const pending = state.changes.filter(change => change.status === 'pending');
  if (!pending.length && !state.libraryChanges.some(change => change.status === 'pending')) $('content').append(el('p', 'No pending changes.', 'muted'));
  if (libraryChanges.error) $('content').append(el('p', 'Library review service unavailable. Only Warehouse proposals are shown.', 'muted'));
  for (const change of state.libraryChanges.filter(change => change.status === 'pending')) {
    $('content').append(button('Library: ' + change.summary, () => renderLibraryChange(change), 'review-row'));
  }
  for (const change of pending) {
    const row = button(change.summary, () => renderChange(change), 'review-row');
    row.append(el('small', change.operations.length + ' topic change(s) · base revision ' + change.base_revision));
    $('content').append(row);
  }
}
function closeNavigation() {
  (utility?.root || $('reader')).focus({preventScroll: true});
}
let utility = null;
function closeUtility() {
  if (!utility) return;
  const previous = utility;
  utility = null;
  previous.dialog.close();
  previous.dialog.remove();
  previous.content.id = 'content';
  previous.notice.id = 'notice';
  state.view = previous.view;
  viewVersion++;
  $('app').dataset.view = previous.view;
  $('app').dataset.empty = previous.empty;
  previous.trigger?.focus({preventScroll: true});
}
async function openUtility(title, trigger, render) {
  closeUtility();
  const content = $('content'), notice = $('notice');
  const dialog = el('dialog', undefined, 'utility-dialog');
  dialog.setAttribute('aria-label', title);
  const root = el('div', undefined, 'reading'); root.id = 'content'; root.tabIndex = -1;
  const feedback = el('div'); feedback.id = 'notice'; feedback.hidden = true; feedback.setAttribute('role', 'alert');
  const close = iconButton('Close ' + title, 'close', closeUtility, 'dialog-close');
  content.id = 'home-content'; notice.id = 'home-notice';
  utility = {content, notice, dialog, root, trigger, view: state.view, empty: $('app').dataset.empty};
  dialog.append(close, feedback, root); document.body.append(dialog);
  dialog.addEventListener('cancel', event => { event.preventDefault(); closeUtility(); });
  dialog.showModal();
  await render();
}
async function attentionView() {
  setView('attention');
  const version = viewVersion;
  screen('Needs attention', 'Loading…');
  const result = await api('/warehouse');
  if (version !== viewVersion) return;
  state.items = result.items;
  screen('Needs attention', 'Knowledge with uncertainty or registered changes.');
  const items = result.items.filter(item => item.state !== 'current');
  const search = el('input'); search.type = 'search'; search.setAttribute('aria-label', 'Search needs attention');
  search.placeholder = 'Find a fact needing attention';
  const list = el('div');
  const render = () => {
  list.replaceChildren();
  const filtered = items.filter(item => item.title.toLocaleLowerCase().includes(search.value.toLocaleLowerCase()));
  if (!filtered.length) list.append(el('p', search.value ? 'No topics match your search.' : 'No topics need attention.', 'muted'));
  for (const item of filtered) list.append(button(item.title + ' · ' + stateLabel(item.state), async () => {
    const version = viewVersion;
    const current = await api('/warehouse/' + encodeURIComponent(item.id));
    if (version !== viewVersion) return;
    closeUtility(); setView('warehouse'); renderTopics(items); renderItem(current);
  }, 'review-row'));
  };
  search.addEventListener('input', render); render();
  $('content').append(search, list);
}
$('reviews-view').addEventListener('click', () => openUtility('Activity', $('reviews-view'), reviewsView).catch(showError));
$('read-view').addEventListener('click', () => readView().catch(showError));
$('attention-view').addEventListener('click', () => openUtility('Needs attention', $('attention-view'), attentionView).catch(showError));
$('add-topic').addEventListener('click', () => propose());
async function openLibrary() {
  rememberReadingRoute({view: 'library'});
  closeUtility();
  return libraryView();
}
$('library-view').addEventListener('click', () => openLibrary().catch(showError));
$('settings-view').addEventListener('click', settingsView);
function setView(view) {
  viewVersion++;
  $('app').dataset.reading = 'false';
  searchVersion++;
  clearError();
  state.view = view;
  $('breadcrumb').textContent = '';
  $('app').dataset.view = view;
  $('app').dataset.empty = 'false';
  if (view === 'intake') $('breadcrumb').textContent += ' / Library / Add knowledge';
  for (const [id, value] of [['library-view', 'library'], ['read-view', 'warehouse'], ['settings-view', 'settings'], ['reviews-view', 'reviews'], ['attention-view', 'attention']]) {
    const active = view === value || (value === 'library' && view === 'intake');
    $(id).toggleAttribute('aria-current', active);
    if (active) $(id).setAttribute('aria-current', 'page');
  }
  $('add-topic').hidden = !['warehouse', 'attention'].includes(view);

  $('search').disabled = !state.workspace || !['library', 'warehouse', 'attention'].includes(view);
  $('search').placeholder = view === 'library' ? 'Find a book or page' : 'Find a fact';
  $('index-title').textContent = view === 'library' ? 'Books & pages' : view === 'settings' ? 'Settings' : 'Shared facts';
  if (view === 'settings') $('topics').replaceChildren();
}
async function libraryView() {
  setView('library');
  const version = viewVersion;
  screen('Library', 'Opening your books…');
  $('topics').replaceChildren();
  try {
    const [result, changes, workspace] = await Promise.all([api(path('/books')), api(path('/library/changes')), api('/workspace')]);
    if (version !== viewVersion) return;
    state.workspace = workspace;
    if (version !== viewVersion || state.view !== 'library') return;
    state.libraryChanges = changes.changes;
    updateCount();
    state.books = await Promise.all(result.books.map(book => api(path('/books/' + encodeURIComponent(book.id)))));
    if (version !== viewVersion || state.view !== 'library') return;
    renderLibraryHome();
    renderLibraryIndex();
  } catch (error) {
    if (version !== viewVersion || state.view !== 'library') return;
    screen('Library unavailable', 'The local Library service could not be loaded. Warehouse facts are still available; retry Library after updating or reopening the app.');
  }
}
function libraryRecord(record, operations = []) {
  const block = el('div');
  block.append(el('p', 'Title: ' + record.title), el('p', 'Publication: ' + record.state, 'muted'));
  if (record.page_ids) {
    block.append(el('p', 'Purpose: ' + record.purpose), el('div', record.overview, 'prose'));
    const names = record.page_ids.map(id => operations.find(operation => operation.id === id)?.title || state.books?.flatMap(book => book.pages).find(page => page.id === id)?.title || id);
    block.append(el('p', 'Page order: ' + names.join(' → '), 'muted'));
  } else {
    for (const section of record.sections) {
      block.append(el('p', 'Section: ' + section.kind, 'muted'), el('div', section.body, 'prose'));
      for (const support of section.supports) block.append(el('p', 'Supports: ' + (state.items.find(item => item.id === support.item_id)?.title || support.item_id) + ' · revision ' + support.revision, 'muted'));
      if (!section.supports.length) block.append(el('p', 'No registered factual support.', 'muted'));
    }
    block.append(el('p', 'Related page IDs: ' + (record.links.join(', ') || 'None'), 'muted'));
  }
  return block;
}
async function renderLibraryChange(change, completion = null) {
  closeUtility();
  const resource = path();
  setView('reviews');
  const version = viewVersion;
  if (!completion) {
    const source = /^Library from capture ([a-f0-9-]{36})$/.exec(change.summary);
    if (source) {
      try { completion = {capture: await api(resource + '/captures/' + source[1]), retain: false}; }
      catch (error) { if (error.status !== 404) throw error; }
    }
  }
  const before = await Promise.all(change.operations.map(async operation => {
    try { return await api(path((operation.op === 'upsert_book' ? '/books/' : '/pages/') + encodeURIComponent(operation.id))); }
    catch (error) { if (error.status === 404) return null; throw error; }
  }));
  if (version !== viewVersion || state.view !== 'reviews') return;
  screen('Review Library change', change.summary);
  $('content').append(el('p', 'Pending publication · base workspace revision ' + change.base_revision + '. Factual accuracy and paraphrase fidelity still need your review.', 'muted'));
  change.operations.forEach((operation, index) => {
    const section = el('section', undefined, 'comparison');
    section.append(el('h2', operation.title), el('h3', 'Before'));
    section.append(before[index] ? libraryRecord(before[index]) : el('p', 'New book or page — nothing published yet.', 'muted'));
    section.append(el('h3', 'After'), libraryRecord(operation, change.operations));
    $('content').append(section);
  });
  if (change.status !== 'pending') return;
  const keep = el('input'); keep.type = 'checkbox'; keep.checked = completion?.retain || false;
  if (completion) {
    const label = el('label', undefined, 'check-label'); label.append(keep, el('span', 'Keep original capture until its expiry'));
    $('content').append(el('p', 'This is the final Library review for the capture. Approval or rejection completes its source lifecycle; originals are removed unless retained explicitly.', 'muted'), label);
  }
  const actions = el('div', undefined, 'actions');
  const decide = async decision => {
    for (const btn of actions.querySelectorAll('button')) btn.disabled = true;
    try {
      const changesResource = resource + '/library/changes';
      await api(changesResource + '/' + encodeURIComponent(change.id) + '/' + decision, {method: 'POST'});
      const result = await api(changesResource);
      if (result.changes.find(candidate => candidate.id === change.id)?.status !== (decision === 'approve' ? 'approved' : 'rejected')) throw new Error('Decision could not be verified. Reload review before retrying.');
      if (completion) await finishCapture(resource + '/captures/' + encodeURIComponent(completion.capture.id), keep.checked);
      await refreshWorkspace();
      await openLibrary();
      if (decision === 'approve') {
        const id = change.operations.find(operation => operation.op === 'upsert_page')?.id;
        const book = state.books?.find(book => book.pages.some(page => page.id === id));
        if (book) renderPage(book.pages.find(page => page.id === id), book);
      } else await reviewsView();
      $('status').textContent = 'Library change ' + (decision === 'approve' ? 'approved' : 'rejected');
    } catch (error) { showError(error); for (const btn of actions.querySelectorAll('button')) btn.disabled = false; }
  };
  actions.append(button('Approve Library change', () => decide('approve'), 'primary'), button('Reject Library change', () => decide('reject')));
  $('content').append(actions);
}
function renderLibraryHome() {
  rememberReadingRoute({view: 'library'});
  $('app').dataset.reading = 'false';
  if (!state.books?.length && !state.workspace.item_count) {
    screen('Your knowledge starts here', 'Add what you know, or ask for something you want to understand.');
    $('app').dataset.empty = 'true';
    $('search').disabled = true;
    appendCaptureComposer();
    return;
  }
  $('app').dataset.empty = 'false';
  screen('Library', 'Readable subjects, grounded in your shared knowledge.');
  $('breadcrumb').textContent = 'Library';
  const shelf = el('div', undefined, 'book-shelf');
  const search = el('input'); search.type = 'search'; search.id = 'library-search';
  search.setAttribute('aria-label', 'Search Library'); search.placeholder = 'Find a subject or page';
  const renderShelf = () => {
  shelf.replaceChildren();
  const query = search.value.trim().toLocaleLowerCase();
  for (const book of state.books || []) {
    const matchingPages = book.pages.filter(page => page.title.toLocaleLowerCase().includes(query));
    if (query && !book.title.toLocaleLowerCase().includes(query) && !matchingPages.length) continue;
    const entry = el('section', undefined, 'book-entry');
    entry.append(el('h2', book.title), el('p', book.purpose || 'No purpose registered.', 'muted'));
    if (book.overview) entry.append(el('p', book.overview));
    if (book.support_state !== 'current') entry.append(el('p', stateLabel(book.support_state), 'muted'));
    entry.append(button('Open ' + book.title, () => renderBook(book)));
    if (query) for (const page of matchingPages) entry.append(button('Read ' + page.title, () => renderPage(page, book), 'review-row'));
    shelf.append(entry);
  }
  if (!shelf.childNodes.length) {
    if (query) { shelf.append(el('p', 'No books or pages match your search.', 'muted')); return; }
    shelf.append(el('p', 'Your knowledge is saved. No reading subjects have been published yet.'), button('Request a reading subject', () => {
      intakeView();
      const intent = document.querySelector('[name=intention]');
      intent.value = 'request';
      intent.dispatchEvent(new Event('change'));
      document.querySelector('[name=capture]').focus();
    }));
  }
  };
  search.addEventListener('input', renderShelf);
  renderShelf();
  if (state.books?.length) {
    const heading = el('div', undefined, 'home-heading');
    heading.append($('content').querySelector('h1'), searchControl(search, 'Search Library'));
    $('content').prepend(heading);
  }
  $('content').append(shelf);
  appendCaptureComposer();
  if (state.books?.length) {
    const dock = el('div', undefined, 'composer-dock');
    dock.append($('content').querySelector('.capture-composer'), $('content').querySelector('.composer-footnote'));
    $('content').append(dock);
  }
}
function searchControl(input, label) {
  const wrap = el('div', undefined, 'search-control');
  const panel = el('div', undefined, 'search-panel');
  panel.id = 'search-panel-' + crypto.randomUUID(); panel.setAttribute('popover', 'auto');
  const trigger = button(label, () => {}, 'quiet-search');
  trigger.setAttribute('popovertarget', panel.id);
  panel.append(input, button('Close search', () => panel.hidePopover()));
  panel.addEventListener('toggle', event => { if (event.newState === 'open') input.focus(); });
  wrap.append(trigger, panel); return wrap;
}
function renderBook(book) {
  clearError();
  setView('library');
  screen(book.title, book.purpose || 'No purpose registered.');
  $('breadcrumb').textContent = 'Library / ' + book.title;
  $('content').append(button('Back to Library', () => { renderLibraryHome(); renderLibraryIndex(); }));
  const metadata = el('div', undefined, 'metadata');
  metadata.append(el('span', book.state), el('span', stateLabel(book.support_state), 'state ' + book.support_state));
  $('content').append(metadata);
  if (book.overview) $('content').append(el('div', book.overview, 'prose'));
  $('content').append(el('h2', 'Pages'));
  if (!book.pages.length) $('content').append(el('p', 'No pages in this book yet. Add material and review a Library proposal to extend it.', 'muted'));
  for (const page of book.pages) {
    const row = button('Read ' + page.title, () => renderPage(page, book), 'review-row');
    row.setAttribute('aria-label', 'Read ' + page.title);
    row.append(el('small', page.state + ' · ' + stateLabel(page.support_state)));
    $('content').append(row);
  }
  renderLibraryIndex();
  setupReadingRoom(book, null);
}
function renderLibraryIndex() {
  const query = $('search').value.toLocaleLowerCase();
  $('topics').replaceChildren();
  for (const book of state.books || []) {
    const pages = book.pages.filter(page => !query || (book.title + ' ' + page.title).toLocaleLowerCase().includes(query));
    if (!pages.length && query && !book.title.toLocaleLowerCase().includes(query)) continue;
    const heading = button(book.title, () => renderBook(book), 'book-title');
    heading.setAttribute('aria-label', 'Open ' + book.title);
    $('topics').append(heading, el('small', book.state + ' · ' + stateLabel(book.support_state)));
    for (const page of pages) {
      const row = button('', () => renderPage(page, book), 'topic');
      row.append(el('span', page.title), el('small', page.state + ' · ' + stateLabel(page.support_state)));
      row.dataset.pageId = page.id;
      $('topics').append(row);
    }
  }
  if (!$('topics').childNodes.length) $('topics').append(el('p', query ? 'No books or pages match your search.' : 'No books yet.', 'muted'));
}
function renderPage(page, book) {
  clearError();
  setView('library');
  screen(page.title, book.purpose);
  $('content').append(button('About this book', () => renderBook(book)));
  $('breadcrumb').textContent = 'Library / ' + book.title;
  const metadata = el('div', undefined, 'metadata');
  metadata.append(el('span', page.state), el('span', stateLabel(page.support_state), 'state ' + page.support_state), el('span', 'Page revision ' + page.revision));
  $('content').append(metadata);
  if (book.overview) {
    const overview = el('details'); overview.append(el('summary', 'About this book'), el('p', book.overview));
    $('content').append(overview);
  }
  $('content').append(el('p', 'Select a passage to ask or add a personal reading mark.', 'selection-hint'));
  for (const [index, section] of page.sections.entries()) {
    const block = el('section');
    block.dataset.sectionId = section.id;
    const prose = el('div', section.body, 'prose');
    const request = button('Request change', async () => {
      const selection = window.getSelection();
      const selected = selection?.toString() || '';
      if (selected && (!prose.contains(selection.anchorNode) || !prose.contains(selection.focusNode))) throw new Error('Select text within this section, or clear the selection to request a change to the whole section.');
      const passage = selected || section.body;
      if (!passage.trim() || passage.length > 10000) throw new Error('Select a passage of 1–10,000 characters in this section before requesting a change.');
      state.captureDrafts ||= new Map();
      const context = {page_id: page.id, page_revision: page.revision, section_id: section.id, passage};
      const existing = state.captureDrafts.get('passage');
      if (existing && JSON.stringify(existing.request_context) !== JSON.stringify(context)) throw new Error('Finish or clear your existing passage request in Add knowledge before selecting a different passage. Your original draft is preserved.');
      state.captureDraftId = 'passage';
      if (!existing) state.captureDrafts.set('passage', {text: '', intent: 'request', files: [], request_context: context});
      intakeView();
      document.querySelector('[name=capture]').focus();
    });
    request.setAttribute('aria-label', 'Request change to section ' + (index + 1));
    request.className = 'legacy-section-request';
    block.append(prose, request);
    const support = el('details');
    support.append(el('summary', section.kind === 'editorial' ? 'Editorial section · not a factual claim' : 'Registered support · ' + stateLabel(section.support_state)));
    if (!section.supports.length && section.kind === 'factual') support.append(el('p', 'No registered support. This section is unresolved.', 'muted'));
    for (const source of section.supports) {
      const item = state.items.find(item => item.id === source.item_id);
      const label = item?.title || source.item_id;
      support.append(button('Inspect ' + label, async () => {
        const version = viewVersion;
        const result = await api(path('/knowledge/' + encodeURIComponent(source.item_id)));
        if (version !== viewVersion || state.view !== 'library') return;
        setView('warehouse'); renderTopics(state.items); renderItem(result);
      }));
      support.append(el('p', `${stateLabel(source.state)} · cited revision ${source.revision} · current revision ${source.current_revision ?? 'missing'}`, 'muted'));
    }
    // Keep factual support visible, not buried behind an unexplained marker.
    support.open = section.kind === 'factual';
    block.append(support); $('content').append(block);
  }
  if (page.links.length) {
    const links = el('section'); links.append(el('h2', 'Related pages'));
    for (const id of page.links) {
      const linkedBook = state.books.find(candidate => candidate.pages.some(candidatePage => candidatePage.id === id));
      const linked = linkedBook?.pages.find(candidate => candidate.id === id);
      if (linked) links.append(button(linked.title, () => renderPage(linked, linkedBook)));
      else links.append(el('p', 'Linked page ' + id + ' is not in a loaded book.', 'muted'));
    }
    $('content').append(links);
  }
  for (const row of $('topics').querySelectorAll('button')) {
    row.removeAttribute('aria-current');
    if (row.dataset.pageId === page.id) row.setAttribute('aria-current', 'page');
  }
  $('status').textContent = 'Reading ' + page.title;
  setupReadingRoom(book, page);
}
function requestContextView(context) {
  const section = el('section');
  section.setAttribute('aria-label', 'Request context');
  section.append(el('h2', 'Passage to review'), el('p', 'Page ' + context.page_id + ' · revision ' + context.page_revision + (context.section_id ? ' · section ' + context.section_id : ''), 'locator'),
    el('blockquote', context.passage, 'prose'), el('p', 'This saved passage is context, not a new fact or an instruction to fetch sources. Factual changes require Warehouse review; presentation changes require Library review.', 'muted'));
  return section;
}
function intakeView() {
  setView('intake');
  screen('Your draft', '');
  appendCaptureComposer();
}
function persistCaptureDrafts() {
  try {
    sessionStorage.setItem('kh-reading-drafts', JSON.stringify({active: state.captureDraftId || 'shared',
      drafts: [...(state.captureDrafts || new Map())].map(([id, draft]) => [id, {...draft, files: [], reattach: draft.files.map(file => file.name)}])}));
  } catch { $('status').textContent = 'Draft recovery storage is unavailable. Keep this window open or copy your draft.'; }
}
function restoreCaptureDrafts() {
  try {
    const saved = JSON.parse(sessionStorage.getItem('kh-reading-drafts') || 'null');
    if (saved?.drafts) { state.captureDrafts = new Map(saved.drafts); state.captureDraftId = saved.active; }
  } catch { /* An invalid local draft never replaces canonical data. */ }
}
async function refreshContextChips(form, draft) {
  const result = await api('/context-sources');
  if (!form.isConnected) return;
  let list = form.querySelector('.context-sources');
  if (!list) { list = el('ul', undefined, 'context-sources'); list.setAttribute('aria-label', 'Authorized local context'); form.prepend(list); }
  list.replaceChildren();
  for (const source of result.sources || []) {
    const row = el('li');
    const use = el('input'); use.type = 'checkbox';
    use.setAttribute('aria-label', 'Use local context ' + source.name);
    use.checked = (draft.source_ids || []).includes(source.id);
    use.disabled = source.status !== 'active';
    use.addEventListener('change', () => {
      draft.source_ids = [...new Set(use.checked ? [...(draft.source_ids || []), source.id] : (draft.source_ids || []).filter(id => id !== source.id))];
      persistCaptureDrafts();
    });
    row.append(use, el('span', source.name), el('small', source.kind + ' · ' + source.status));
    row.append(button('Revoke ' + source.name, async () => {
      await api('/context-sources/' + encodeURIComponent(source.id) + '/revoke', {method: 'POST', body: '{}'});
      const verified = await api('/context-sources/' + encodeURIComponent(source.id));
      if (verified.status !== 'revoked') throw new Error('Revocation could not be verified. Reopen local context before retrying.');
      await refreshContextChips(form, draft);
    }));
    list.append(row);
  }
}
function growComposer(text) {
  text.style.height = '0px';
  text.style.height = Math.min(Math.max(text.scrollHeight, 44), Math.min(160, innerHeight * .28)) + 'px';
}
function appendCaptureComposer() {
  const form = el('form', undefined, 'capture-composer');
  form.setAttribute('aria-label', 'Capture composer');
  const intention = field(form, 'Intention', 'intention', '', 'select');
  for (const [value, label] of [['add_knowledge', 'Add knowledge'], ['request', 'Request something']]) {
    const option = el('option', label); option.value = value; intention.append(option);
  }
  const text = field(form, 'Capture', 'capture', '', 'textarea');
  text.parentElement.className = 'capture-field';
  text.rows = 3;
  text.maxLength = 100000;
  text.placeholder = 'Add knowledge, or ask for something…';
  state.captureDrafts ||= new Map();
  const draftId = state.captureDraftId || 'shared';
  if (!state.captureDrafts.has(draftId)) state.captureDrafts.set(draftId, {text: '', intent: 'add_knowledge', files: []});
  const draft = state.captureDrafts.get(draftId);
  text.value = draft.text;
  intention.value = draft.intent;
  if (draft.request_context) {
    intention.disabled = true;
    form.append(requestContextView(draft.request_context));
    $('content').querySelector('h1').textContent = 'Request something';
    text.placeholder = 'What would you like changed or explained?';
  }
  intention.addEventListener('change', () => { draft.intent = intention.value; persistCaptureDrafts(); });
  text.addEventListener('input', () => { draft.text = text.value; persistCaptureDrafts(); growComposer(text); });
  const attachments = draft.files;
  const list = el('ul', undefined, 'attachments');
  list.setAttribute('aria-label', 'Review attachments');
  const render = () => {
    list.replaceChildren(...attachments.map((file, index) => {
      const row = el('li');
      const name = file.webkitRelativePath || file.name;
      row.append(el('span', name));
      row.title = `${name} · ${file.type || 'Unknown format'} · ${file.size.toLocaleString()} bytes · not processed`;
      if (['image/png', 'image/jpeg', 'image/webp'].includes(captureMediaType(file)) && file.size <= 5 * 1024 * 1024) {
        const preview = el('img', undefined, 'attachment-preview');
        preview.alt = 'Preview ' + name;
        const reader = new FileReader();
        reader.onload = () => { preview.src = String(reader.result); };
        reader.readAsDataURL(file);
        row.append(preview);
      }
      const remove = iconButton('Remove ' + name, 'remove', () => { attachments.splice(index, 1); render(); });
      row.append(remove);
      return row;
    }));
  };
  render();
  const addFiles = files => { attachments.push(...Array.from(files)); persistCaptureDrafts(); render(); };
  const picker = el('input');
  picker.name = 'files'; picker.setAttribute('aria-label', 'Attach files');
  picker.hidden = true; picker.type = 'file'; picker.multiple = true;
  picker.addEventListener('change', () => { addFiles(picker.files); picker.value = ''; });
  form.append(picker);
  const attach = iconButton('Attach files or local context', 'attach', async () => {
    const handler = window.webkit?.messageHandlers?.knowledgeHubContext;
    const bridge = typeof handler?.postMessage === 'function'
      ? {choose_context_sources: () => handler.postMessage(null)} : window.pywebview?.api;
    if (typeof bridge?.choose_context_sources === 'function') {
      const result = await bridge.choose_context_sources();
      if (result?.error) throw new Error('Local selection could not be completed. Your draft is preserved.');
      if (!result?.cancelled) {
        draft.source_ids = [...new Set([...(draft.source_ids || []), ...(result.sources || []).map(source => source.id)])];
        persistCaptureDrafts();
      }
      await refreshContextChips(form, draft);
    } else {
      $('status').textContent = 'Browser mode supports files only. Open the desktop app to choose folders as local context.';
      picker.click();
    }
  });
  const fallback = el('span', 'Browser: files only; folders require the desktop app.', 'picker-disclosure');
  if (typeof window.webkit?.messageHandlers?.knowledgeHubContext?.postMessage !== 'function'
      && typeof window.pywebview?.api?.choose_context_sources !== 'function') form.append(fallback);
  const menu = el('div', undefined, 'attachment-menu');
  menu.id = 'draft-options-' + crypto.randomUUID(); menu.setAttribute('popover', 'auto');
  const options = button('Draft options', () => {}, 'draft-options');
  options.setAttribute('popovertarget', menu.id);
  if (draft.reattach?.length) form.append(el('p', 'Reattach files after reload: ' + draft.reattach.join(', '), 'muted'));
  refreshContextChips(form, draft).catch(error => { if (error.status !== 404) showError(error); });
  text.addEventListener('paste', event => {
    const images = Array.from(event.clipboardData?.items || []).filter(item => item.kind === 'file').map(item => item.getAsFile()).filter(Boolean);
    if (images.length) { event.preventDefault(); addFiles(images); }
  });
  form.addEventListener('dragover', event => { event.preventDefault(); form.classList.add('drag-over'); });
  form.addEventListener('dragleave', () => form.classList.remove('drag-over'));
  form.addEventListener('drop', event => {
    event.preventDefault(); form.classList.remove('drag-over');
    const directory = Array.from(event.dataTransfer?.items || []).some(item => item.webkitGetAsEntry?.()?.isDirectory);
    if (directory) { showError(new Error('Directory drops are not supported. Use the desktop attachment control to authorize a folder as local context. No folder contents were read.')); return; }
    addFiles(event.dataTransfer?.files || []);
  });
  form.append(list);
  const save = iconButton('Send', 'send', () => {}, 'primary');
  save.type = 'submit';
  menu.append(button('Clear draft', () => {
    menu.hidePopover();
    state.captureDrafts.delete(draftId);
    persistCaptureDrafts();
    if (state.captureDraftId === draftId) state.captureDraftId = 'shared';
    if (state.view === 'library') renderLibraryHome(); else intakeView();
  }));
  const tools = el('div', undefined, 'composer-tools');
  const intentionLabel = intention.parentElement;
  intentionLabel.className = 'intention-field';
  menu.prepend(intentionLabel);
  tools.append(attach, options, save);
  form.append(tools, menu);
  let composing = false;
  text.addEventListener('compositionstart', () => { composing = true; });
  text.addEventListener('compositionend', () => { composing = false; });
  text.addEventListener('keydown', event => {
    if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !composing && event.keyCode !== 229) {
      event.preventDefault();
      if (!save.disabled) form.requestSubmit();
    }
  });
  form.addEventListener('submit', async event => {
    event.preventDefault(); clearError(); save.disabled = true;
    const resource = path('/captures');
    const version = viewVersion;
    const snapshot = {text: text.value, intent: intention.value, files: [...attachments], request_context: draft.request_context, source_ids: [...(draft.source_ids || [])]};
    try {
      if (snapshot.source_ids.length) {
        if (!snapshot.text.trim()) throw new Error('Describe what the Curator should learn from the selected local context.');
        if (snapshot.files.length || snapshot.request_context) throw new Error('Send local context separately from uploaded files or a passage request; your draft is preserved.');
        const binding = JSON.stringify({text: snapshot.text, source_ids: snapshot.source_ids});
        if (draft.job_binding !== binding) { draft.job_binding = binding; draft.job_request_id = crypto.randomUUID(); persistCaptureDrafts(); }
        const saved = await api('/curator-jobs', {method: 'POST', body: JSON.stringify({source_ids: snapshot.source_ids, instruction: snapshot.text, request_id: draft.job_request_id})});
        const verified = await api('/curator-jobs/' + encodeURIComponent(saved.id));
        if (state.captureDrafts.get(draftId) === draft && draft.text === snapshot.text && draft.intent === snapshot.intent && draft.request_context === snapshot.request_context && JSON.stringify(draft.source_ids || []) === JSON.stringify(snapshot.source_ids) && !draft.files.length) {
          state.captureDrafts.delete(draftId); state.captureDraftId = 'shared'; persistCaptureDrafts();
        }
        if (version === viewVersion && ['intake', 'library'].includes(state.view)) inspectCuratorJob(verified);
        return;
      }
      if (!text.value.trim() && !attachments.length) throw new Error('Paste text or attach at least one file.');
      if (attachments.length > 20 || attachments.some(file => file.size > 5 * 1024 * 1024) || attachments.reduce((sum, file) => sum + file.size, 0) > 20 * 1024 * 1024) throw new Error('Use up to 20 files, at most 5 MiB each and 20 MiB total. Remove larger files and retry.');
      const files = [];
      for (const file of snapshot.files) files.push({name: file.webkitRelativePath || file.name, media_type: captureMediaType(file), content_base64: await fileBase64(file)});
      const saved = await api(resource, {method: 'POST', body: JSON.stringify({text: snapshot.text, intent: snapshot.intent === 'request' ? 'Request something' : 'Add knowledge', request_context: snapshot.request_context, files, retention_days: 7})});
      const capture = await api(resource + '/' + encodeURIComponent(saved.id));
      if (state.captureDrafts.get(draftId) === draft && draft.text === snapshot.text && draft.intent === snapshot.intent && draft.request_context === snapshot.request_context && draft.files.length === snapshot.files.length && draft.files.every((file, index) => file === snapshot.files[index])) {
        state.captureDrafts.delete(draftId);
        if (state.captureDraftId === draftId) state.captureDraftId = 'shared';
        persistCaptureDrafts();
      }
      if (version !== viewVersion || !['intake', 'library'].includes(state.view)) return;
      setView('intake');
      await inspectCapture(capture);
      await savedCaptures();
    } catch (error) { if (version === viewVersion) showError(error); save.disabled = false; }
  });
  $('content').append(form);
  growComposer(text);
  const foot = el('div', undefined, 'composer-footnote');
  foot.append(el('span', 'Saved locally · reviewed by you'));
  const help = el('a', 'Help');
  help.href = 'https://github.com/NewBww/knowledge-hub/wiki'; help.target = '_blank'; help.rel = 'noopener noreferrer';
  foot.append(help); $('content').append(foot);
}
function inspectCuratorJob(initial) {
  setView('intake');
  const version = viewVersion;
  const render = job => {
    if (version !== viewVersion || state.view !== 'intake') return;
    screen('Curator work', 'Local checkpoints recover when the app reopens. Work pauses on Quit; independent background continuation is not configured.');
    const status = el('p', 'Status: ' + job.status.replaceAll('_', ' ')); status.setAttribute('role', 'status');
    $('content').append(status, el('p', job.instruction), el('p', 'Attempt ' + job.attempt_count + ' of ' + job.max_attempts));
    if (job.error) $('content').append(el('p', 'Needs attention: ' + job.error.replaceAll('_', ' ')));
    if (job.result?.change_id) $('content').append(button('Review proposed knowledge', async () => {
      const changes = await api('/changes');
      if (version !== viewVersion || state.view !== 'intake') return;
      const change = changes.changes.find(change => change.id === job.result.change_id);
      if (!change) throw new Error('The saved proposal is unavailable. Refresh Activity before retrying.');
      renderChange(change);
    }));
    const refresh = async () => {
      const current = await api('/curator-jobs/' + encodeURIComponent(job.id));
      if (version === viewVersion && state.view === 'intake') render(current);
    };
    $('content').append(button('Refresh Curator status', refresh));
    if (['failed', 'blocked', 'retry_wait', 'paused'].includes(job.status)) $('content').append(button('Retry Curator work', async () => {
      await api('/curator-jobs/' + encodeURIComponent(job.id) + '/retry', {method: 'POST', body: '{}'}); await refresh();
    }));
    if (!['review_ready', 'cancelled'].includes(job.status)) $('content').append(button('Cancel Curator work', async () => {
      await api('/curator-jobs/' + encodeURIComponent(job.id) + '/cancel', {method: 'POST', body: '{}'}); await refresh();
    }));
  };
  render(initial);
}
async function savedCaptures() {
  const version = viewVersion;
  $('index-title').textContent = 'Local captures';
  $('topics').replaceChildren(el('p', 'Loading captures…', 'muted'));
  const result = await api(path('/captures'));
  if (version !== viewVersion || state.view !== 'intake') return;
  $('topics').replaceChildren();
  for (const capture of result.captures) {
    const row = button('Review saved capture ' + capture.id.slice(0, 8), async () => {
      const current = await api(path('/captures/' + encodeURIComponent(capture.id)));
      if (version === viewVersion && state.view === 'intake') await inspectCapture(current);
    }, 'topic');
    row.append(el('small', captureState(capture) + ' · expires ' + new Date(capture.expires_at).toLocaleDateString()));
    $('topics').append(row);
  }
  if (!result.captures.length) $('topics').append(el('p', 'No saved captures.', 'muted'));
}
function captureMediaType(file) {
  if (file.type) return file.type;
  const extension = file.name.split('.').pop().toLowerCase();
  return ({txt: 'text/plain', md: 'text/markdown', csv: 'text/csv', json: 'application/json', pdf: 'application/pdf', docx: 'application/vnd.openxmlformats-officedocument.wordprocessingml.document', png: 'image/png', jpg: 'image/jpeg', jpeg: 'image/jpeg', webp: 'image/webp'})[extension] || 'application/octet-stream';
}
function fileBase64(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result).split(',')[1]);
    reader.onerror = () => reject(new Error('Could not read ' + file.name + '. Remove it or choose it again.'));
    reader.readAsDataURL(file);
  });
}
function captureState(capture) {
  if (capture.result) {
    const warehouse = state.changes.find(change => change.id === capture.result.warehouse_change.id);
    const library = (state.libraryChanges || []).filter(change => change.summary === 'Library from capture ' + capture.id);
    if (warehouse?.status === 'approved' && (!capture.result.library_suggestions.length || (library.length && library.every(change => change.status !== 'pending')))) return 'Accepted · source retained until expiry';
  }
  if (capture.status === 'proposed' || capture.result) return 'Ready for review';
  if (capture.status === 'accepted' || capture.status === 'completed') return 'Accepted';
  if (capture.claim && Date.parse(capture.claim.expires_at) > Date.now()) return 'In progress · claimed by an agent';
  return 'Saved locally · waiting for an agent';
}
async function inspectCapture(capture) {
  const version = viewVersion;

  if (version !== viewVersion || state.view !== 'intake') return;
  clearError(); screen('Review capture', 'Saved in local app storage only. Review the source before enabling your connected agent to read it.');
  $('content').append(el('p', 'Expires: ' + capture.expires_at + ' · ' + capture.status, 'muted'));
  if (capture.text) $('content').append(el('h2', 'Pasted text'), el('div', capture.text, 'prose'));
  if (capture.intent) $('content').append(el('h2', 'Organization request'), el('p', capture.intent));
  if (capture.request_context) $('content').append(requestContextView(capture.request_context));
  for (const file of capture.files) {
    const section = el('section', undefined, 'comparison');
    section.append(el('h2', file.name), el('p', file.media_type + ' · ' + file.size + ' bytes · ' + file.status + (file.reason ? ' · ' + file.reason : ''), 'muted'));
    if (file.text) section.append(el('div', file.text, 'prose'));
    if (file.status === 'image') section.append(el('p', `Image ${file.width} × ${file.height}. No local OCR. A connected agent can request original bytes explicitly when you enable shared capture access; its harness decides image support.`, 'muted'));
    if (file.status === 'unprocessed') section.append(el('p', 'No local extraction. Original retained until discard or expiry; an authorized external agent can explicitly retrieve it.', 'muted'));
    $('content').append(section);
  }
  $('content').append(el('p', 'Snapshot: ' + capture.snapshot_sha256, 'locator'));
  if (capture.result) { await renderAgentResult(capture); return; }
  const working = captureState(capture).startsWith('In progress');
  $('content').append(el('h2', working ? 'In progress' : 'Awaiting agent'), el('p', working ? 'An agent has claimed this capture. Its proposal still requires your review.' : 'Saved locally, waiting for an authorized agent. Connecting MCP alone does not start processing. An app-managed Curator runs only when explicitly enabled in Settings.'));
  const actions = el('div', undefined, 'actions');
  actions.append(button('Refresh agent result', async () => {
    const current = await api(path('/captures/' + encodeURIComponent(capture.id)));
    if (version === viewVersion && state.view === 'intake') await inspectCapture(current);
  }), button('Discard capture', async () => {
    const resource = path('/captures/' + encodeURIComponent(capture.id));
    await api(resource, {method: 'DELETE'});
    try { await api(resource); throw new Error('Capture deletion could not be verified.'); }
    catch (error) { if (error.status !== 404) throw error; }
    if (version === viewVersion) intakeView();
  }));
  $('content').append(actions);
  await captureAccess($('content'));
}
async function captureAccess(container) {
  const section = el('section');
  section.append(el('h2', 'External agent access'));
  container.append(section);
  const resource = '/agent/access';
  try {
    const access = await api(resource);
    if (!section.isConnected) return;
    const render = enabled => {
      section.replaceChildren(el('h2', 'External agent access'));
      section.append(el('p', enabled ? 'Agent capture access enabled. This does not prove a harness is connected.' : 'Agent capture access is disabled. Your intake stays queued locally.', 'muted'));
      section.append(el('p', 'This permission covers all captures in the shared workspace, including future captures, until you disable it. Your harness may read original attachments and send them to cloud services. Knowledge Hub cannot enforce downstream model training or retention. Review your harness’s actual configuration first.', 'muted'));
      const label = el('label', undefined, 'check-label');
      const consent = el('input'); consent.type = 'checkbox';
      label.append(consent, el('span', 'I understand my harness may send all captures in the shared workspace to its models'));
      const toggle = button(enabled ? 'Disable agent capture access' : 'Enable agent capture access', async () => {
        toggle.disabled = true;
        try {
          await api(resource, {method: 'POST', body: JSON.stringify({enabled: !enabled})});
          const verified = await api(resource);
          if (verified.enabled !== !enabled) throw new Error('Agent access update could not be verified. Reopen Add knowledge before allowing a read.');
          if (section.isConnected) render(verified.enabled);
        } catch (error) { showError(error); toggle.disabled = !enabled && !consent.checked; }
      });
      toggle.disabled = !enabled;
      consent.addEventListener('change', () => { toggle.disabled = !consent.checked; });
      if (!enabled) section.append(label);
      section.append(toggle);
    };
    render(access.enabled);
  } catch (error) {
    if (section.isConnected) section.append(el('p', 'Agent-access service unavailable. No access change was made. Reopen Add knowledge to retry.', 'muted'));
  }
}
async function finishCapture(resource, retain) {
  try { await api(resource + '/finish', {method: 'POST', body: JSON.stringify({retain_source: retain})}); }
  catch (error) { if (error.status === 404) return; throw error; }
  if (retain) { await api(resource); return; }
  try { await api(resource); }
  catch (error) { if (error.status === 404) return; throw error; }
  throw new Error('Capture deletion could not be verified.');
}
async function renderAgentResult(capture) {
  const version = viewVersion;
  const [changes, libraryChanges] = await Promise.all([api('/changes'), api('/library/changes')]);
  if (version !== viewVersion || state.view !== 'intake') return;
  state.changes = changes.changes;
  state.libraryChanges = libraryChanges.changes;
  updateCount();
  const change = changes.changes.find(change => change.id === capture.result.warehouse_change.id);
  if (!change) throw new Error('The Warehouse proposal is no longer available.');
  if (captureState(capture).startsWith('Accepted')) {
    screen('Accepted', 'Your human decisions are saved. This original source is retained locally until its expiry; it is not queued for processing or a conversation archive.');
    $('content').append(button('Discard retained source', async () => {
      await finishCapture('/captures/' + encodeURIComponent(capture.id), false);
      if (version === viewVersion) await reviewsView();
    }));
    return;
  }
  screen('Agent proposals', 'Organization is a draft, not accepted knowledge. Review the Warehouse change before accepting any facts. Book/page destinations below are suggestions, not publications.');
  $('content').append(el('p', 'Warehouse proposal: ' + change.status, 'muted'), el('h2', change.summary));
  for (const operation of change.operations) $('content').append(el('h3', operation.title), el('div', operation.body, 'prose'));
  $('content').append(el('h2', 'Suggested destinations'));
  for (const suggestion of capture.result.library_suggestions) $('content').append(el('h3', suggestion.book_title + ' → ' + suggestion.page_title), el('div', suggestion.body, 'prose'));
  if (!capture.result.library_suggestions.length) $('content').append(el('p', 'No book/page destination suggested.', 'muted'));
  if (change.status === 'approved' && capture.result.library_suggestions.length) {
    $('content').append(button('Arrange suggested Library pages', () => arrangeCapture(capture), 'primary'));
  } else if (change.status === 'pending') {
    $('content').append(button('Review Warehouse proposal', async () => {
      const knowledge = await api(path('/knowledge'));
      if (version !== viewVersion || state.view !== 'intake') return;
      state.items = knowledge.items; renderChange(change);
    }, 'primary'));
  }
  $('content').append(button('Finish without Library pages', async () => {
    await finishCapture(path('/captures/' + encodeURIComponent(capture.id)), false);
    if (version === viewVersion) intakeView();
  }));
  await savedCaptures();
}
async function arrangeCapture(capture, retainSource = false) {
  const resource = path();
  setView('intake');
  const version = viewVersion;
  screen('Arrange Library pages', 'Warehouse facts are accepted. Review the suggested wording, choose new or existing books, and explicitly cite the accepted facts supporting each factual page. Nothing is published until the next human review.');
  const [knowledge, index, workspace] = await Promise.all([api(path('/knowledge')), api(path('/books')), api('/workspace')]);
  if (version !== viewVersion || state.view !== 'intake') return;
  state.items = knowledge.items;
  const revision = workspace.revision;
  const books = await Promise.all(index.books.filter(book => book.state !== 'archived').map(book => api(path('/books/' + encodeURIComponent(book.id)))));
  if (version !== viewVersion || state.view !== 'intake') return;
  const current = knowledge.items.filter(item => item.state === 'current');
  const form = el('form');
  const rows = [];
  const submit = el('button', 'Preview Library proposal', 'primary'); submit.type = 'submit'; submit.disabled = true;
  const validate = () => { const included = rows.filter(row => row.include.checked); submit.disabled = !included.length || included.some(row => !row.supports.some(support => support.input.checked)); };
  capture.result.library_suggestions.forEach((suggestion, index) => {
    const section = el('fieldset'); section.append(el('legend', 'Suggested page ' + (index + 1)));
    const label = el('label', undefined, 'check-label');
    const include = el('input'); include.type = 'checkbox'; include.checked = true;
    label.append(include, el('span', 'Include ' + suggestion.page_title)); section.append(label);
    const destination = field(section, 'Destination book ' + (index + 1), 'destination_' + index, '', 'select');
    const fresh = el('option', 'Create a new book'); fresh.value = ''; destination.append(fresh);
    for (const book of books) { const option = el('option', book.title); option.value = book.id; destination.append(option); }
    const title = field(section, 'Book title ' + (index + 1), 'book_' + index, suggestion.book_title); title.required = true; title.maxLength = 500;
    const pageTitle = field(section, 'Page title ' + (index + 1), 'page_' + index, suggestion.page_title); pageTitle.required = true; pageTitle.maxLength = 500;
    const body = field(section, 'Page text ' + (index + 1), 'body_' + index, suggestion.body, 'textarea'); body.maxLength = 20000;
    section.append(el('h3', 'Cite accepted Warehouse facts'), el('p', 'Choose only facts that support this wording. A citation is not a guarantee of paraphrase accuracy.', 'muted'));
    const supports = current.map(item => {
      const wrapper = el('label', undefined, 'check-label'); const input = el('input'); input.type = 'checkbox';
      wrapper.append(input, el('span', 'Cite ' + item.title + ' for ' + suggestion.page_title));
      section.append(wrapper, el('p', 'Accepted revision ' + item.revision, 'muted'));
      input.addEventListener('change', validate); return {input, item};
    });
    if (!current.length) section.append(el('p', 'No current accepted facts are available. Resolve Warehouse uncertainty before publishing a factual page.', 'muted'));
    const sync = () => {
      title.disabled = !include.checked || Boolean(destination.value); title.required = include.checked && !destination.value;
      pageTitle.required = include.checked;
      destination.disabled = !include.checked; pageTitle.disabled = !include.checked; body.disabled = !include.checked;
      for (const support of supports) support.input.disabled = !include.checked;
      validate();
    };
    include.addEventListener('change', sync); destination.addEventListener('change', sync);
    rows.push({include, destination, title, pageTitle, body, supports}); form.append(section);
  });
  const retain = el('input'); retain.type = 'checkbox'; retain.checked = retainSource;
  const retainLabel = el('label', undefined, 'check-label'); retainLabel.append(retain, el('span', 'Keep original capture until its expiry'));
  form.append(retainLabel, el('p', 'The source stays local during arrangement and Library review. After the final approve/reject, it is removed unless retained above. You can finish without publishing suggestions.', 'muted'));
  const actions = el('div', undefined, 'actions');
  actions.append(submit, button('Finish without Library pages', async () => {
    await finishCapture(resource + '/captures/' + encodeURIComponent(capture.id), retain.checked);
    if (version === viewVersion) await libraryView();
  })); form.append(actions);
  const key = crypto.randomUUID();
  form.addEventListener('submit', async event => {
    event.preventDefault(); clearError(); submit.disabled = true;
    try {
      const operations = []; const groups = new Map();
      for (const row of rows.filter(row => row.include.checked)) {
        const selected = row.supports.filter(support => support.input.checked);
        if (!selected.length) throw new Error('Cite at least one accepted fact for every included factual page.');
        const groupKey = row.destination.value || 'new:' + row.title.value;
        if (!groups.has(groupKey)) {
          const old = books.find(book => book.id === row.destination.value);
          groups.set(groupKey, old ? {op: 'upsert_book', id: old.id, base_revision: old.revision, title: old.title, purpose: old.purpose, overview: old.overview, state: old.state, page_ids: [...old.page_ids]} : {op: 'upsert_book', id: crypto.randomUUID(), base_revision: 0, title: row.title.value, purpose: 'Organized knowledge', overview: '', state: 'published', page_ids: []});
        }
        const id = crypto.randomUUID(); groups.get(groupKey).page_ids.push(id);
        operations.push({op: 'upsert_page', id, base_revision: 0, title: row.pageTitle.value, state: 'published', sections: [{id: crypto.randomUUID(), kind: 'factual', body: row.body.value, supports: selected.map(({item}) => ({item_id: item.id, revision: item.revision, relationship: 'supports'}))}], links: []});
      }
      operations.push(...groups.values());
      const change = await api(resource + '/library/changes', {method: 'POST', body: JSON.stringify({base_revision: revision, idempotency_key: key, summary: 'Library from capture ' + capture.id, operations})});
      const verified = (await api(resource + '/library/changes')).changes.find(candidate => candidate.id === change.id);
      if (!verified) throw new Error('Library proposal could not be verified. Reopen Review changes before retrying.');
      if (version === viewVersion) await renderLibraryChange(verified, {capture, retain: retain.checked});
    } catch (error) { showError(error); validate(); }
  });
  $('content').append(form);
}
function settingsView() {
  clearError(); setView('settings');
  screen('Settings', 'Connection, human permissions and application updates. Reading and local search need no model.');
  $('breadcrumb').textContent = 'Settings';
  $('content').append(button('Back to Library', openLibrary), el('h2', 'Agent setup'));
  const curator = el('section');
  curator.id = 'curator-settings';
  curator.append(el('h3', 'App-managed Curator'), el('p', 'Loading connection settings…', 'muted'));
  $('content').append(curator);
  curatorSettings(curator).catch(error => { if (curator.isConnected) showError(error); });
  $('content').append(el('h2', 'External agent'), el('p', 'Use your existing MCP-compatible client without setting up a second provider here. Your client owns its models, sign-in and source connectors.'));
  $('content').append(el('pre', '"/Applications/Knowledge Hub.app/Contents/MacOS/Knowledge Hub" mcp'));
  $('content').append(el('p', 'Use your actual app location and the same local data directory. Discover the versioned setup guide through MCP. Adding this command is not evidence that an agent is connected or processing.', 'muted'));
  $('content').append(el('p', 'Both paths prepare pending changes. Only a human can approve or reject knowledge and Library changes.'));
  $('content').append(el('p', 'A connected harness may send selected data to cloud models. Knowledge Hub cannot guarantee downstream training or retention policy.'));
  captureAccess($('content')).catch(showError);
  const updates = el('section');
  updates.id = 'application-updates';
  updates.append(el('h2', 'Application updates'), el('p', 'Check the release configuration before downloading an update.', 'muted'), button('Check for Updates', updatesView));
  $('content').append(updates);
}
const connectionStatus = value => ({unconfigured: 'Not configured', missing_cli: 'CLI not installed', sign_in_required: 'Sign-in required', unsupported_capability: 'Unsupported capability', unchecked: 'Check required', ready: 'Ready', checked: 'Check passed', check_failed: 'Check failed', disabled: 'Disabled', processing: 'Processing', failed: 'Check failed'})[value] || value;
async function curatorSettings(container) {
  const version = viewVersion;
  const [catalog, configuration] = await Promise.all([api('/curator/catalog'), api('/curator')]);
  if (!container.isConnected || version !== viewVersion) return;
  container.replaceChildren(el('h3', 'App-managed Curator'), el('p', 'One connection and one model for knowledge work. The app prepares proposals; it never approves them.'));
  const form = el('form');
  const connection = field(form, 'Connection', 'connection', '', 'select');
  const blank = el('option', 'Choose a connection'); blank.value = ''; connection.append(blank);
  for (const entry of catalog.connections) { const option = el('option', entry.name); option.value = entry.id; connection.append(option); }
  const draft = state.connectionDraft ||= {connection: configuration.connection || '', model: configuration.model || ''};
  connection.value = draft.connection;
  const model = field(form, 'Model', 'model', draft.model);
  model.required = true; model.maxLength = 200;
  model.placeholder = 'Exact model identifier';
  form.append(el('p', 'Use an explicit model supported by this connection. OpenCode and Hermes use their configured underlying provider. The app will not change your global client defaults or silently choose another model.', 'muted'));
  const availability = el('div'); form.append(availability);
  const selectedStatus = el('p');
  const disclosure = el('p', catalog.disclosure || 'Selected task material may be sent to this connection and incur costs. Provider retention and training terms apply. Canonical knowledge remains local.', 'muted');
  form.append(disclosure);
  const consent = el('input'); consent.type = 'checkbox';
  const consentLabel = el('label', undefined, 'check-label'); consentLabel.append(consent, el('span', 'I approve this connection, model and disclosure scope')); form.append(consentLabel);
  const saved = el('p', '', 'muted'); saved.setAttribute('role', 'status');
  const confirm = el('button', 'Confirm connection and model', 'primary'); confirm.type = 'submit';
  form.append(confirm, saved);
  const runtime = el('div');
  const renderRuntime = config => {
    if (config.connection === connection.value) selectedStatus.textContent = connectionStatus(config.status);
    runtime.replaceChildren(el('p', 'Processing: ' + (config.enabled ? 'enabled' : 'disabled'), 'muted'), el('p', 'Connection status: ' + connectionStatus(config.status), 'muted'));
    if (config.last_error) runtime.append(el('p', 'Last check: ' + config.last_error, 'muted'));
    const actions = el('div', undefined, 'actions');
    const check = button('Run synthetic connection check', async () => {
      check.disabled = true;
      clearError();
      let failure;
      try { await api('/curator/check', {method: 'POST', body: '{}'}); }
      catch (error) { failure = error; }
      try {
        const verified = await api('/curator');
        if (runtime.isConnected && version === viewVersion) {
          renderRuntime(verified);
          if (failure) showError(failure);
        }
      } finally { check.disabled = false; }
    });
    check.disabled = !config.connection;
    const toggle = button(config.enabled ? 'Disable processing' : 'Enable processing', async () => {
      toggle.disabled = true;
      try {
        await api('/curator/enable', {method: 'POST', body: JSON.stringify({enabled: !config.enabled})});
        const verified = await api('/curator');
        if (verified.enabled !== !config.enabled) throw new Error('Processing change could not be verified. Refresh Settings before retrying.');
        if (runtime.isConnected && version === viewVersion) renderRuntime(verified);
      } finally { toggle.disabled = false; }
    });
    toggle.disabled = !config.enabled && !['ready', 'checked'].includes(config.status);
    const run = button('Process next capture', async () => {
      run.disabled = true;
      run.textContent = 'Processing one capture…';
      const feedback = el('p', 'Processing one claimed capture. You can disable processing to cancel it.', 'muted');
      feedback.setAttribute('role', 'status'); runtime.append(feedback);
      try {
        const result = await api('/curator/run', {method: 'POST', body: '{}'});
        const verified = await api('/curator');
        const changes = await api('/changes');
        if (!runtime.isConnected || version !== viewVersion) return;
        state.changes = changes.changes; updateCount();
        renderRuntime(verified);
        runtime.append(el('p', result.status === 'ready_for_review' ? 'Proposal ready for human review.' : result.status === 'idle' ? 'No waiting captures are available.' : result.reason === 'request_requires_external_agent' ? 'This request needs your external agent. It remains saved locally.' : 'Work remains pending. Open Activity for its current state.', 'muted'));
      } catch (error) {
        if (runtime.isConnected && version === viewVersion) {
          feedback.textContent = 'Processing stopped. No acceptance was made. Open Activity to inspect the saved capture.';
          showError(error);
        }
      } finally { run.disabled = !config.enabled; run.textContent = 'Process next capture'; }
    });
    run.disabled = !config.enabled;
    actions.append(check, toggle, run);
    runtime.append(el('p', 'The check uses synthetic material, not your knowledge. Enabling permits selected queued capture text to leave the app through this connection. Each proposal still needs your review.', 'muted'), actions);
  };
  const selection = () => {
    draft.connection = connection.value; draft.model = model.value;
    confirm.disabled = !consent.checked || !connection.value || !model.value.trim();
    const entry = catalog.connections.find(entry => entry.id === connection.value);
    availability.replaceChildren();
    if (entry) {
      selectedStatus.textContent = connectionStatus(entry.availability);
      availability.append(selectedStatus, el('p', entry.transport === 'cli' ? 'Official CLI connection' : 'Native HTTPS connection', 'muted'), el('p', entry.reason, 'muted'));
      appendConnectionAuth(availability, entry, renderRuntime);
    }
  };
  connection.addEventListener('change', () => { consent.checked = false; selection(); });
  model.addEventListener('input', () => { consent.checked = false; selection(); });
  consent.addEventListener('change', selection);
  form.addEventListener('submit', async event => {
    event.preventDefault(); clearError(); confirm.disabled = true;
    try {
      const payload = {configuration: {connection: connection.value, model: model.value.trim()}, confirm: true, consent: consent.checked};
      await api('/curator/config', {method: 'POST', body: JSON.stringify(payload)});
      const verified = await api('/curator');
      if (verified.connection !== payload.configuration.connection || verified.model !== payload.configuration.model || verified.enabled) throw new Error('Configuration could not be verified. Refresh Settings before enabling processing.');
      if (!container.isConnected || version !== viewVersion) return;
      saved.textContent = 'Saved. Processing remains disabled.';
      renderRuntime(verified);
    } catch (error) { if (container.isConnected) showError(error); }
    finally { confirm.disabled = !consent.checked; }
  });
  selection(); renderRuntime(configuration);
  container.append(form, runtime);
}

function appendConnectionAuth(container, entry, renderRuntime) {
  const handoff = el('div');
  const signIn = button(entry.id === 'openrouter' ? 'Sign in with OpenRouter' : 'Sign-in instructions', async () => {
    signIn.disabled = true;
    try {
      const result = await api('/curator/auth/start', {method: 'POST', body: JSON.stringify({connection: entry.id})});
      if (!container.isConnected) return;
      handoff.replaceChildren();
      if (result.url) {
        let url;
        try { url = new URL(result.url); } catch { throw new Error('The connection returned an unsafe sign-in link. No external page was opened.'); }
        if (url.protocol !== 'https:' || url.hostname !== 'openrouter.ai' || url.pathname !== '/auth' || url.username || url.password || (url.port && url.port !== '443')) throw new Error('The connection returned an unsafe sign-in link. No external page was opened.');
        const link = el('a', 'Continue to OpenRouter'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        handoff.append(el('p', 'Continue in your browser, then return here. Sign-in does not enable processing.', 'muted'), link);
      } else {
        handoff.append(el('p', result.status === 'missing_cli' ? 'Install the official CLI before signing in.' : 'Sign in through the official CLI. The app does not extract or copy its credentials.', 'muted'));
        handoff.append(el('p', 'Working directory', 'muted'));
        const directory = el('pre', result.cwd); directory.setAttribute('aria-label', 'Sign-in working directory');
        const commands = el('pre', [result.cwd_command, ...(result.display_commands || [])].join('\n'));
        commands.setAttribute('aria-label', 'Sign-in commands');
        handoff.append(directory, el('p', 'Copy these commands into your terminal and run them in order. Nothing is run automatically.', 'muted'), commands);
        if (result.reason) handoff.append(el('p', result.reason, 'muted'));
        handoff.append(el('p', result.execution === 'blocked_tool_denial_unverified'
          ? 'Inference remains blocked: deny-all tool execution has not been verified.'
          : 'After sign-in, confirm the connection/model and disclosure, run the synthetic connection check, then explicitly enable processing.', 'muted'));
      }
    } finally { signIn.disabled = false; }
  });
  container.append(signIn, handoff);
  if (entry.install_url) {
    try {
      const url = new URL(entry.install_url);
      if (url.protocol === 'https:' && !url.username && !url.password) {
        const link = el('a', 'Installation and sign-in guide'); link.href = url.href; link.target = '_blank'; link.rel = 'noopener noreferrer';
        const paragraph = el('p'); paragraph.append(link); container.append(paragraph);
      }
    } catch { /* Invalid guide links are not actionable. */ }
  }
  if (entry.id !== 'openrouter') return;
  const key = field(container, 'OpenRouter API key', 'api_key');
  key.type = 'password'; key.autocomplete = 'off'; key.spellcheck = false;
  const feedback = el('p', '', 'muted'); feedback.setAttribute('role', 'status');
  const save = button('Save key securely', async () => {
    save.disabled = true;
    try {
      if (!key.value) throw new Error('Enter an API key in this local human-only field.');
      await api('/curator/auth/key', {method: 'POST', body: JSON.stringify({connection: 'openrouter', key: key.value})});
      key.value = '';
      const verified = await api('/curator');
      if (!container.isConnected) return;
      feedback.textContent = 'Credential saved in the OS credential store.';
      renderRuntime(verified);
    } finally { save.disabled = false; }
  });
  container.append(el('p', 'Optional alternative to browser sign-in. Enter only here; never share credentials with an agent. The key goes directly to the local OS credential store, not knowledge, exports or MCP.', 'muted'), save, feedback);
}
async function updatesView() {
  clearError();
  const section = $('application-updates');
  section.replaceChildren(el('h2', 'Application updates'), el('p', 'Checking the release configuration…'));
  try {
    const result = await api('/updates/check', {method: 'POST'});
    if (!section.isConnected || state.view !== 'settings') return;
    section.replaceChildren(el('h2', 'Application updates'), el('p', result.reason || 'The update service did not provide a verified release status.'));
    section.append(el('p', 'Installed version: ' + result.current_version));
    if (result.configured) {
      section.append(el('p', 'Native update window opened'), el('p', 'Save unsaved capture drafts and stop your harness’s Knowledge Hub MCP connection before installing. Restart and installation are confirmed in the native window.', 'muted'), button('Check again', updatesView));
    } else {
      section.append(el('p', 'Release hosting has not been selected. No release check or download was sent. This does not mean the installed version is the latest.', 'muted'));
      const actions = el('div', undefined, 'actions');
      const install = button('Update unavailable', () => {});
      install.disabled = true;
      actions.append(button('Check again', updatesView), install);
      section.append(actions);
    }
  } catch (error) {
    if (section.isConnected && state.view === 'settings') {
      section.replaceChildren(el('h2', 'Application updates'), el('p', 'The update check could not be completed. Your installed application and local knowledge have not changed.'), button('Retry update check', updatesView));
      showError(error);
    }
  }
}
start();
