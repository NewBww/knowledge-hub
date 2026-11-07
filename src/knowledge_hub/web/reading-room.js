'use strict';
/* Reading-only state is personal to this browser; canonical edits use the API. */
let restoringRoute = false;
let activeReading = null;
let passageSelection = null;
function rememberReadingRoute(route) {
  if (restoringRoute) return;
  const query = new URLSearchParams(route).toString();
  const url = location.pathname + (query ? '?' + query : '');
  if (url !== location.pathname + location.search) history.pushState({route}, '', url);
}
async function restoreReadingRoute(search = location.search) {
  const query = new URLSearchParams(search);
  restoringRoute = true;
  try {
    if (query.get('view') === 'settings') { settingsView(); return; }
    if (query.get('view') === 'warehouse') { await readView(); return; }
    const book = state.books?.find(book => book.id === query.get('book'));
    if (book) {
      const page = book.pages.find(page => page.id === query.get('page'));
      if (page) renderPage(page, book); else renderBook(book);
    } else if (query.get('view') === 'library' || !query.get('view')) { await openLibrary(); }
  } finally { restoringRoute = false; }
}
window.addEventListener('popstate', () => restoreReadingRoute().catch(showError));
function setupReadingRoom(book, page) {
  activeReading = {book, page};
  $('app').dataset.reading = 'true';
  rememberReadingRoute({view: 'reader', book: book.id, ...(page ? {page: page.id} : {})});
  const content = $('content');
  const returns = el('div', undefined, 'reader-returns');
  returns.append(button('Back to Library', openLibrary), button('Warehouse', () => readView()),
    el('span', book.pages.length + (book.pages.length === 1 ? ' page total' : ' pages total'), 'book-page-total'));
  content.prepend(returns);
  // The return destinations live in one sticky place, not in every outline.
  for (const control of content.querySelectorAll(':scope > button')) {
    if (['Back to Library', 'About this book'].includes(control.textContent)) control.remove();
  }
  const controls = el('div', undefined, 'reader-tools');
  const outline = el('aside', undefined, 'reading-outline');
  outline.setAttribute('aria-label', 'Book outline');
  outline.id = 'reading-outline';
  const showOutline = button('Hide outline', () => toggleOutline());
  showOutline.setAttribute('aria-controls', outline.id);
  const toggleOutline = () => {
    outline.hidden = !outline.hidden;
    showOutline.textContent = outline.hidden ? 'Show outline' : 'Hide outline';
    showOutline.setAttribute('aria-expanded', String(!outline.hidden));
  };
  outline.append(button('Close outline', () => { if (!outline.hidden) toggleOutline(); }));
  const children = el('div', undefined, 'outline-children');
  const root = el('div', undefined, 'outline-row');
  const chevron = button('', () => {
    children.hidden = !children.hidden;
    chevron.setAttribute('aria-expanded', String(!children.hidden));
  }, 'outline-chevron');
  chevron.setAttribute('aria-label', 'Expand or collapse ' + book.title);
  chevron.setAttribute('aria-expanded', 'true');
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('viewBox', '0 0 16 16'); svg.setAttribute('aria-hidden', 'true');
  const path = document.createElementNS(svg.namespaceURI, 'path'); path.setAttribute('d', 'm4 6 4 4 4-4'); svg.append(path); chevron.append(svg);
  const title = button(book.title, () => renderBook(book), 'outline-title');
  root.append(chevron, title); outline.append(root, children);
  for (const child of book.pages) {
    const row = button(child.title, () => renderPage(child, book), 'outline-page');
    row.dataset.pageId = child.id;
    if (page?.id === child.id) row.setAttribute('aria-current', 'page');
    children.append(row);
  }
  if (book.pages.length > 1) { showOutline.setAttribute('aria-expanded', 'true'); controls.append(showOutline); content.append(outline); }
  const review = el('aside', undefined, 'reading-review'); review.id = 'reading-review'; review.hidden = true;
  review.setAttribute('aria-label', 'Page review');
  const relevant = (state.libraryChanges || []).filter(change => change.status === 'pending' && change.operations.some(operation => operation.id === (page?.id || book.id)));
  const reviewToggle = button('Review · ' + relevant.length, () => {
    review.hidden = !review.hidden; reviewToggle.setAttribute('aria-expanded', String(!review.hidden));
  });
  reviewToggle.setAttribute('aria-expanded', 'false'); reviewToggle.setAttribute('aria-controls', review.id);
  review.append(button('Close review', () => { review.hidden = true; reviewToggle.setAttribute('aria-expanded', 'false'); }), el('h2', 'Review'));
  if (!relevant.length) review.append(el('p', 'No pending proposals for this page.', 'muted'));
  for (const change of relevant) {
    const card = el('section', undefined, 'review-summary');
    card.append(el('small', 'Suggestion · human review required'), el('h3', change.summary), button('Compare before and after', () => renderLibraryChange(change)));
    review.append(card);
  }
  controls.append(reviewToggle); content.insertBefore(controls, returns.nextSibling); content.append(review);
  if (page) {
    const metadata = content.querySelector('.metadata');
    metadata?.append(el('span', 'Personal marks do not change shared knowledge.'));
    applyPersonalMarks(page);
  }
  const draft = state.captureDrafts?.get('passage');
  if (draft) {
    const resume = button('Resume passage request', () => openPassageAsk(draft.request_context), 'resume-passage');
    resume.id = 'resume-passage'; document.body.append(resume);
  }
}
function personalMarks() {
  try { return JSON.parse(localStorage.getItem('kh-reading-marks') || '[]'); } catch { return []; }
}
function applyPersonalMarks(page) {
  let stale = false;
  for (const mark of personalMarks().filter(mark => mark.page_id === page.id)) {
    const prose = [...$('content').querySelectorAll('[data-section-id]')].find(block => block.dataset.sectionId === mark.section_id)?.querySelector('.prose');
    if (!prose || mark.page_revision !== page.revision || prose.textContent.slice(mark.start, mark.end) !== mark.passage) { stale = true; continue; }
    const range = textOffsetRange(prose, mark.start, mark.end);
    if (!range) continue;
    const wrapper = el('span', undefined, 'personal-' + mark.kind);
    wrapper.append(range.extractContents()); range.insertNode(wrapper);
  }
  if (stale) $('content').append(el('p', 'Some personal marks belong to an older revision and could not be reanchored. The original marks are retained locally.', 'muted'));
}
function textOffsetRange(root, start, end) {
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT);
  let offset = 0, node, first, last;
  while ((node = walker.nextNode())) {
    const next = offset + node.length;
    if (!first && start >= offset && start < next) first = [node, start - offset];
    if (end > offset && end <= next) { last = [node, end - offset]; break; }
    offset = next;
  }
  if (!first || !last) return null;
  const range = document.createRange(); range.setStart(...first); range.setEnd(...last); return range;
}
document.addEventListener('selectionchange', () => {
  if (!activeReading?.page || $('app')?.dataset.reading !== 'true') return;
  const selection = getSelection();
  if (!selection?.rangeCount || selection.isCollapsed) return;
  const range = selection.getRangeAt(0);
  const node = range.startContainer.nodeType === 1 ? range.startContainer : range.startContainer.parentElement;
  const prose = node.closest?.('[data-section-id] .prose');
  if (!prose || !prose.contains(range.endContainer)) return;
  const passage = selection.toString(); if (!passage.trim() || passage.length > 10000) return;
  const prefix = range.cloneRange(); prefix.selectNodeContents(prose); prefix.setEnd(range.startContainer, range.startOffset);
  const previousSelection = passageSelection;
  passageSelection = {page_id: activeReading.page.id, page_revision: activeReading.page.revision,
    section_id: prose.closest('[data-section-id]').dataset.sectionId, passage, start: prefix.toString().length, end: prefix.toString().length + passage.length};
  if ($('selection-tools') && JSON.stringify(previousSelection) === JSON.stringify(passageSelection)) return;
  document.getElementById('selection-tools')?.remove();
  const tools = el('div', undefined, 'selection-tools'); tools.id = 'selection-tools'; tools.setAttribute('role', 'toolbar'); tools.setAttribute('aria-label', 'Selected passage');
  tools.addEventListener('pointerdown', event => event.preventDefault());
  const snapshot = {...passageSelection};
  tools.append(button('Ask', () => { tools.remove(); openPassageAsk(snapshot); }));
  for (const [label, kind] of [['Highlight', 'highlight'], ['Bold', 'bold'], ['Underline', 'underline'], ['Strikethrough', 'strike'], ['Clear marks', 'clear']]) tools.append(button(label, () => {
    const marks = personalMarks().filter(mark => !(mark.page_id === snapshot.page_id && mark.section_id === snapshot.section_id && mark.start < snapshot.end && mark.end > snapshot.start));
    if (kind !== 'clear') marks.push({...snapshot, kind});
    try { localStorage.setItem('kh-reading-marks', JSON.stringify(marks)); }
    catch { throw new Error('Personal marks could not be saved. Browser storage may be full.'); }
    tools.remove(); renderPage(activeReading.page, activeReading.book);
    $('status').textContent = kind === 'clear' ? 'Personal marks cleared' : 'Personal mark saved';
  }));
  document.body.append(tools);
  const box = range.getBoundingClientRect();
  tools.style.left = Math.max(8, Math.min(box.left, innerWidth - tools.offsetWidth - 8)) + 'px';
  tools.style.top = Math.max(80, Math.min(box.top - tools.offsetHeight - 8, innerHeight - tools.offsetHeight - 8)) + 'px';
});
function openPassageAsk(selection) {
  const context = {page_id: selection.page_id, page_revision: selection.page_revision, section_id: selection.section_id, passage: selection.passage};
  state.captureDrafts ||= new Map();
  let draft = state.captureDrafts.get('passage');
  if (draft && JSON.stringify(draft.request_context) !== JSON.stringify(context)) throw new Error('Finish or clear your existing passage request before selecting a different passage. Your original draft is preserved.');
  if (!draft) { draft = {text: '', intent: 'request', files: [], request_context: context}; state.captureDrafts.set('passage', draft); }
  persistCaptureDrafts();
  $('passage-ask')?.remove(); $('resume-passage')?.remove();
  const panel = el('section', undefined, 'passage-ask'); panel.id = 'passage-ask'; panel.setAttribute('aria-label', 'Ask about this passage');
  panel.append(el('strong', 'Ask about this passage'), button('Close passage request', () => {
    panel.remove(); const resume = button('Resume passage request', () => openPassageAsk(context), 'resume-passage'); resume.id = 'resume-passage'; document.body.append(resume);
  }), el('blockquote', context.passage));
  const input = el('textarea'); input.setAttribute('aria-label', 'Passage request'); input.placeholder = 'What would you like clarified or changed?'; input.value = draft.text;
  input.addEventListener('input', () => { draft.text = input.value; persistCaptureDrafts(); growComposer(input); });
  panel.append(input);
  const actions = el('div', undefined, 'actions');
  const send = button('Send passage request', async () => {
    if (!draft.text.trim()) throw new Error('Write your request before sending.');
    send.disabled = true;
    const text = draft.text;
    try {
      const saved = await api('/captures', {method: 'POST', body: JSON.stringify({text, intent: 'Request something', files: [], request_context: context, retention_days: 7})});
      const verified = await api('/captures/' + encodeURIComponent(saved.id));
      if (state.captureDrafts.get('passage') === draft && draft.text === text) { state.captureDrafts.delete('passage'); persistCaptureDrafts(); }
      panel.remove(); setView('intake'); await inspectCapture(verified);
    } finally { send.disabled = false; }
  }, 'primary');
  actions.append(button('Expand request', () => { state.captureDraftId = 'passage'; persistCaptureDrafts(); intakeView(); $('content').querySelector('[name=capture]').focus(); }), send,
    button('Clear passage draft', () => { state.captureDrafts.delete('passage'); state.captureDraftId = 'shared'; persistCaptureDrafts(); panel.remove(); }));
  panel.append(actions, el('small', 'Saved locally first. Any proposed shared change still requires your approval.'));
  let composing = false;
  input.addEventListener('compositionstart', () => { composing = true; }); input.addEventListener('compositionend', () => { composing = false; });
  input.addEventListener('keydown', event => { if (event.key === 'Enter' && !event.shiftKey && !event.isComposing && !composing && event.keyCode !== 229) { event.preventDefault(); send.click(); } });
  document.body.append(panel); growComposer(input); input.focus({preventScroll: true});
}
