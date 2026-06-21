// Main-thread RPC proxy to scan-worker.js, which owns the one persistent
// Pyodide instance (and its SQLite DB) for the whole page session. Sets
// window._bridge to the same four-method shape the desktop's QWebChannel
// EmpireBridge has, so ui/js/scan-loader.js needs zero changes beyond the
// window._bridge branch already added there.

let _scanWorker = null;
let _nextRequestId = 1;
const _pending = new Map();

function getScanWorker() {
  if (!_scanWorker) {
    _scanWorker = new Worker("js/scan-worker.js");
    _scanWorker.onmessage = (event) => {
      const { id, type, payload, message } = event.data;
      const entry = _pending.get(id);
      if (!entry) return;
      _pending.delete(id);
      if (type === "error") entry.reject(new Error(message));
      else entry.resolve(payload);
    };
  }
  return _scanWorker;
}

function callWorker(type, payload) {
  return new Promise((resolve, reject) => {
    const id = _nextRequestId++;
    _pending.set(id, { resolve, reject });
    getScanWorker().postMessage({ id, type, payload });
  });
}

// Ensures a saves-directory handle is available, granting one (via a real
// picker dialog) only if no usable persisted handle exists. Only valid
// inside trigger_scan()'s call stack - that's the "New Scan" button's click
// handler, which is the real user gesture showDirectoryPicker() requires.
async function ensureSavesDir() {
  let handle = await FSAccess.restoreHandle("savesRoot");
  if (handle && (await FSAccess.ensurePermission(handle))) {
    return await FSAccess.walkToSavesDir(handle);
  }
  handle = await FSAccess.grantSavesRoot();
  return await FSAccess.walkToSavesDir(handle);
}

window._bridge = {
  trigger_scan(cb) {
    (async () => {
      try {
        const savesDir = await ensureSavesDir();
        const files = await FSAccess.listSaveFiles(savesDir);
        if (files.length === 0) {
          cb(JSON.stringify({ ok: false, error: "No save files found in the granted folder." }));
          return;
        }
        const chosen = await showSavePickerDialog(files);
        if (!chosen) {
          cb(JSON.stringify({ ok: false, cancelled: true }));
          return;
        }
        const result = await callWorker("trigger_scan", { fileHandle: chosen.handle });
        cb(result);
      } catch (e) {
        cb(JSON.stringify({ ok: false, error: String(e) }));
      }
    })();
  },

  get_empire_data(scanId, cb) {
    callWorker("get_empire_data", { scanId })
      .then(cb)
      .catch(e => cb(JSON.stringify({ error: String(e) })));
  },

  list_scans(cb) {
    callWorker("list_scans", {})
      .then(cb)
      .catch(e => cb(JSON.stringify({ error: String(e) })));
  },

  delete_scan(scanId, cb) {
    callWorker("delete_scan", { scanId })
      .then(cb)
      .catch(e => cb(JSON.stringify({ error: String(e) })));
  },
};
