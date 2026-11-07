"""Isolated real Cocoa startup probe; never imported by the application."""
import json
import sys
import threading
from pathlib import Path

import webview
from PyObjCTools import AppHelper
from knowledge_hub.desktop import LocalServer
from knowledge_hub.http import create_app
from knowledge_hub.native_picker import CocoaPicker, DesktopAPI

root = Path(sys.argv[1])
root.mkdir(parents=True, exist_ok=True)
observed: dict = {'begin_count': 0}

class CancelPicker(CocoaPicker):
    def begin(self, window, complete):
        assert threading.current_thread() is threading.main_thread()
        observed['begin_count'] += 1
        complete([])

app = create_app(data_dir=root / 'data', human_token='synthetic-human-token-12345678901234567890', agent_token='synthetic-agent-token-12345678901234567890')
with LocalServer(app) as server:
    picker = CancelPicker()
    api = DesktopAPI(app.state.context_sources, server.url, adapter=picker)
    window = webview.create_window('Synthetic native bridge QA', url=server.url + '#token=synthetic-human-token-12345678901234567890', width=800, height=600)
    api._bind(window)
    window.events.before_show += api._prepare
    window.events.closed += api._close

    def save():
        observed['ready'] = api._ready
        observed['grants'] = app.state.context_sources.sources()
        (root / 'result.json').write_text(json.dumps(observed, indent=2))
        window.destroy()

    def inspect():
        from webview.platforms.cocoa import BrowserView
        view = BrowserView.instances[window.uid].webview
        observed['native'] = {
            'content_is_webview': BrowserView.instances[window.uid].window.contentView() == view,
            'attached': view.window() == BrowserView.instances[window.uid].window,
            'frame': str(view.frame()),
        }
        script = r'''(() => {
          const handler = window.webkit?.messageHandlers?.knowledgeHubContext;
          const value = {handler: typeof handler?.postMessage === 'function',
            generic: typeof window.webkit?.messageHandlers?.jsBridge !== 'undefined',
            rendered: !!document.querySelector('[aria-label="Attach files or local context"]'),
            disclosure: document.body.innerText.includes('Browser: files only')};
          // Fixed test-only string: assert CSP rejects dynamic compilation.
          try { new Function('return 1'); value.evalBlocked = false; } catch (_) { value.evalBlocked = true; }
          if (value.handler) {
            handler.postMessage({path:'/not-authorized'}).then(result => {
              document.documentElement.dataset.invalidReply = JSON.stringify(result);
              return handler.postMessage(null);
            }).then(result => {
              document.documentElement.dataset.pickerReply = JSON.stringify(result);
              document.querySelector('[aria-label="Attach files or local context"]').click();
            });
          }
          return JSON.stringify(value);
        })()'''
        def initial(value, error):
            observed['startup'] = json.loads(str(value)) if value else {'error': str(error)}
            AppHelper.callLater(1, finish)
        def finish():
            def final(value, error):
                observed['replies'] = json.loads(str(value)) if value else {'error': str(error)}
                save()
            view.evaluateJavaScript_completionHandler_("JSON.stringify({invalid:document.documentElement.dataset.invalidReply, picker:document.documentElement.dataset.pickerReply})", final)
        view.evaluateJavaScript_completionHandler_(script, initial)

    def loaded():
        AppHelper.callLater(0.8, inspect)
    window.events.loaded += loaded
    def watchdog():
        observed['timeout'] = True
        save()
    def started():
        AppHelper.callLater(12, watchdog)
    webview.start(func=started, gui='cocoa', debug=False, private_mode=True)
print(json.dumps(observed))
assert not observed.get('timeout'), observed
assert observed['native']['content_is_webview'], observed
assert observed['native']['attached'], observed
assert observed['startup']['handler'], observed
assert observed['startup']['rendered'], observed
assert observed['startup']['evalBlocked'], observed
assert not observed['startup']['generic'], observed
assert not observed['startup']['disclosure'], observed
assert observed['begin_count'] == 2, observed
assert json.loads(observed['replies']['picker']) == {'sources': [], 'cancelled': True}, observed
assert json.loads(observed['replies']['invalid']) == {'error': 'invalid_native_picker_request'}, observed
assert observed['grants'] == [], observed
