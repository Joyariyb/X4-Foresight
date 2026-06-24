// File System Access API flow: directory grant, walking, listing, and
// IndexedDB-backed handle persistence, for the saves folder only - the X4
// install folder is never granted at all, since the language file it would
// have been used for is pre-extracted offline and bundled as a static asset
// instead (see ui/web/extract_language_file.py).
//
// IMPORTANT: showDirectoryPicker() requires a real user gesture (a genuine
// click) - browsers refuse to show it from scripted/automated code. That
// restriction applies only to grantSavesRoot() below; once a handle exists
// (granted or restored from IndexedDB), every other function here - walking
// subfolders, listing files, re-checking permission - has no such
// restriction and can run from anywhere. grantSavesRoot() is called from
// pyodide-bridge.js's trigger_scan(), which is itself the "New Scan" button's
// click handler, so the gesture requirement is satisfied for free.

const HANDLE_DB_NAME = "x4-foresight-handles";
const HANDLE_STORE = "directory-handles";

function openHandleDB() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(HANDLE_DB_NAME, 1);
    req.onupgradeneeded = () => {
      req.result.createObjectStore(HANDLE_STORE);
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

async function persistHandle(key, handle) {
  const db = await openHandleDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(HANDLE_STORE, "readwrite");
    tx.objectStore(HANDLE_STORE).put(handle, key);
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
  });
}

async function restoreHandle(key) {
  const db = await openHandleDB();
  return new Promise((resolve, reject) => {
    const tx = db.transaction(HANDLE_STORE, "readonly");
    const req = tx.objectStore(HANDLE_STORE).get(key);
    req.onsuccess = () => resolve(req.result || null);
    req.onerror = () => reject(req.error);
  });
}

// Re-requests permission on a restored handle. Per the File System Access
// spec this should show a lightweight reconfirmation rather than the full
// picker again - confirming that across a genuine browser restart (not just
// a tab reload) needs a manual check (see task #6), since it can't be
// scripted.
async function ensurePermission(handle, mode = "read") {
  const opts = { mode };
  if ((await handle.queryPermission(opts)) === "granted") return true;
  return (await handle.requestPermission(opts)) === "granted";
}

// ── Fallback for browsers without showDirectoryPicker() ─────────────────
// Firefox doesn't support the File System Access API at all, and Brave
// blocks showDirectoryPicker() by default (shields up). This opens a
// plain <input webkitdirectory> folder picker instead. No persistent
// handles - the folder must be re-selected on each scan.

function grantSavesRootFallback() {
  return new Promise((resolve, reject) => {
    const input = document.createElement("input");
    input.type = "file";
    input.webkitdirectory = true;
    input.onchange = () => resolve(Array.from(input.files || []));
    // The "cancel" event fires when the user closes the picker without
    // choosing. Supported in Chrome 113+, Firefox 91+, Safari 16.4+.
    input.addEventListener("cancel", () =>
      reject(new DOMException("The user aborted a request.", "AbortError"))
    );
    input.click();
  });
}

// Filters the flat FileList from grantSavesRootFallback() down to save
// files only, returning the same shape as listSaveFiles() but with a
// `file` property (a plain File) instead of `handle`.
function listSaveFilesFallback(files) {
  return files
    .filter(f => SAVE_FILE_PATTERN.test(f.name))
    .map(f => ({ name: f.name, file: f, size: f.size, lastModified: f.lastModified }))
    .sort((a, b) => b.lastModified - a.lastModified);
}

// ── Saves directory (File System Access API path) ────────────────────────

// Must be called from a real user gesture (e.g. a button's click handler).
async function grantSavesRoot() {
  const handle = await window.showDirectoryPicker({ startIn: "documents" });
  await persistHandle("savesRoot", handle);
  return handle;
}

const SAVE_FILE_PATTERN = /^(save|autosave)_\d+\.xml(\.gz)?$/i;

// True if a folder directly contains at least one compatible save file -
// cheap existence check (no getFile() calls), used to detect the case where
// the user granted the "save" folder itself.
async function hasCompatibleSaves(dirHandle) {
  for await (const [name, handle] of dirHandle.entries()) {
    if (handle.kind === "file" && SAVE_FILE_PATTERN.test(name)) return true;
  }
  return false;
}

// Mirrors x4_save_scanner.py's _find_game_saves_dir()'s steamid-agnostic
// search: tries every immediate child directory of an "X4" folder for a
// "save" subfolder.
async function findSaveUnderX4(x4Handle) {
  for await (const [name, handle] of x4Handle.entries()) {
    if (handle.kind !== "directory") continue;
    try {
      return await handle.getDirectoryHandle("save");
    } catch (e) {
      // No "save" subfolder under this entry - keep looking.
    }
  }
  throw new Error("No <steamid>/save folder found under Egosoft/X4");
}

// showDirectoryPicker() only opens AT Documents - it doesn't stop the user
// there. In practice people click "Select Folder" at whatever depth feels
// natural, often drilling all the way down into the real "save" folder
// itself rather than stopping at Documents. So instead of assuming one
// fixed depth, try each known depth (save itself, <steamid>, X4, Egosoft,
// Documents-or-higher) until one resolves. No path string, no OS username
// needed - pure folder-name navigation, so (unlike the grant itself) this
// has no gesture requirement and works on a handle restored from IndexedDB.
async function findSavesDir(rootHandle) {
  if (await hasCompatibleSaves(rootHandle)) return rootHandle;
  try {
    return await rootHandle.getDirectoryHandle("save");
  } catch (e) {
    // Not the <steamid> folder - keep trying shallower guesses.
  }
  try {
    return await findSaveUnderX4(rootHandle);
  } catch (e) {
    // Not the "X4" folder - keep trying shallower guesses.
  }
  try {
    const x4 = await rootHandle.getDirectoryHandle("X4");
    return await findSaveUnderX4(x4);
  } catch (e) {
    // Not the "Egosoft" folder - keep trying shallower guesses.
  }
  const egosoft = await rootHandle.getDirectoryHandle("Egosoft");
  const x4 = await egosoft.getDirectoryHandle("X4");
  return await findSaveUnderX4(x4);
}

// Enumerates save_*.xml(.gz) / autosave_*.xml(.gz), newest first - mirrors
// the desktop app's save picker sort order.
async function listSaveFiles(savesDirHandle) {
  const files = [];
  for await (const [name, handle] of savesDirHandle.entries()) {
    if (handle.kind !== "file" || !SAVE_FILE_PATTERN.test(name)) continue;
    const file = await handle.getFile();
    files.push({ name, handle, size: file.size, lastModified: file.lastModified });
  }
  files.sort((a, b) => b.lastModified - a.lastModified);
  return files;
}

window.FSAccess = {
  persistHandle, restoreHandle, ensurePermission,
  grantSavesRoot, findSavesDir, listSaveFiles,
  grantSavesRootFallback, listSaveFilesFallback,
};
