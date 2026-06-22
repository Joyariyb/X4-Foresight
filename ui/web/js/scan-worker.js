// Dedicated Web Worker owning the one persistent Pyodide instance (and its
// SQLite DB) for the whole page session. Required, not optional: an 80s+
// synchronous scan fully blocks whatever thread runs it (confirmed in the
// Pyodide port spikes - the main thread became unresponsive to even a
// devtools eval call mid-parse), so the scan - and every other Python call,
// to keep them all talking to the same DB connection's MEMFS - happens here
// instead of on the page's main thread.
//
// Paths below are relative to THIS SCRIPT's own location (ui/web/js/), not
// to whatever page created the worker - that's how worker-relative fetch()
// resolution works, unlike a page's own <script>.

importScripts("https://cdn.jsdelivr.net/pyodide/v0.27.0/full/pyodide.js");

const APP_ROOT = "/home/pyodide/app";
const STAGED_LANG_PATH = "/staged/lang_0001-l044.xml";
const STAGED_SAVE_PATH = "/staged/current_save.xml.gz";

let pyodideReady = null;

async function bootPyodide() {
  const pyodide = await loadPyodide();
  await pyodide.loadPackage(["lxml", "sqlite3"]);

  // "no-cache" forces a conditional revalidation (ETag check) against the
  // server on every load instead of trusting the browser's HTTP cache - the
  // Python source tree changes on every deploy, and a stale cached manifest
  // or source file previously caused a fixed bug to keep reappearing.
  const manifest = await (await fetch("../py-manifest.json", { cache: "no-cache" })).json();
  pyodide.FS.mkdirTree(APP_ROOT);
  for (const relPath of manifest) {
    // This worker script lives at ui/web/js/ - three levels below the repo
    // root, not two (a worker's fetch() resolves relative to its own script
    // location, same as a page does to its own URL - but this script sits
    // one directory deeper than ui/web/index.html does).
    const response = await fetch("../../../" + relPath, { cache: "no-cache" });
    // A 404 here (e.g. a host silently dropping a file) must not be staged
    // as if it were real source - that previously wrote the host's HTML
    // error page in place of the .py file, surfacing as a baffling Python
    // SyntaxError instead of a clear "file missing" message.
    if (!response.ok) {
      throw new Error(`Failed to fetch staged file "${relPath}": HTTP ${response.status}`);
    }
    const text = await response.text();
    const fullPath = APP_ROOT + "/" + relPath;
    pyodide.FS.mkdirTree(fullPath.substring(0, fullPath.lastIndexOf("/")));
    pyodide.FS.writeFile(fullPath, text);
  }
  pyodide.runPython(`
import sys
if "${APP_ROOT}" not in sys.path:
    sys.path.insert(0, "${APP_ROOT}")
`);

  const langBuf = await (await fetch("../assets/lang_0001-l044.xml")).arrayBuffer();
  pyodide.FS.mkdirTree("/staged");
  pyodide.FS.writeFile(STAGED_LANG_PATH, new Uint8Array(langBuf));

  return pyodide;
}

function getPyodide() {
  if (!pyodideReady) pyodideReady = bootPyodide();
  return pyodideReady;
}

async function handleTriggerScan(pyodide, payload) {
  const file = await payload.fileHandle.getFile();
  const buf = await file.arrayBuffer();
  pyodide.FS.writeFile(STAGED_SAVE_PATH, new Uint8Array(buf));

  pyodide.globals.set("_save_path", STAGED_SAVE_PATH);
  pyodide.globals.set("_lang_path", STAGED_LANG_PATH);
  // Pyodide auto-wraps a JS function set into globals as a callable Python
  // can invoke directly. Sent as its own message type (no request `id`) so
  // it doesn't get routed through the id-keyed request/response map in
  // pyodide-bridge.js - that map only resolves one promise per id, but a
  // single scan call needs to emit several of these along the way.
  pyodide.globals.set("_progress_cb", (stage) => {
    self.postMessage({ type: "progress", payload: { stage } });
  });
  return await pyodide.runPythonAsync(`
import pyweb.web_entry as web_entry
web_entry.run_scan_from_staged(_save_path, _lang_path, progress=_progress_cb)
`);
}

self.onmessage = async (event) => {
  const { id, type, payload } = event.data;
  try {
    const pyodide = await getPyodide();
    let result;
    switch (type) {
      case "trigger_scan":
        result = await handleTriggerScan(pyodide, payload);
        break;
      case "get_empire_data":
        pyodide.globals.set("_scan_id", payload.scanId);
        result = pyodide.runPython(`
import pyweb.web_entry as web_entry
web_entry.get_empire_data(_scan_id)
`);
        break;
      case "get_resource_library":
        result = pyodide.runPython(`
import pyweb.web_entry as web_entry
web_entry.get_resource_library()
`);
        break;
      case "list_scans":
        result = pyodide.runPython(`
import pyweb.web_entry as web_entry
web_entry.list_scans()
`);
        break;
      case "delete_scan":
        pyodide.globals.set("_scan_id", payload.scanId);
        result = pyodide.runPython(`
import pyweb.web_entry as web_entry
web_entry.delete_scan(_scan_id)
`);
        break;
      default:
        throw new Error("Unknown message type: " + type);
    }
    self.postMessage({ id, type: "result", payload: result });
  } catch (e) {
    self.postMessage({ id, type: "error", message: String(e) + "\n" + (e.stack || "") });
  }
};
