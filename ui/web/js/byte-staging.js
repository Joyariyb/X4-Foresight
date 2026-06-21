// Copies bytes from a File System Access API file handle into Pyodide's
// virtual filesystem, so the existing Python open()/gzip.open()/pathlib
// calls (scanner/language.py's open_save(), etc.) work completely
// unmodified against the staged path - no Python-side I/O changes needed.

async function stageFileHandleIntoPyodide(pyodide, fileHandle, destPath) {
  const file = await fileHandle.getFile();
  const buf = await file.arrayBuffer();
  const dir = destPath.substring(0, destPath.lastIndexOf("/"));
  if (dir) pyodide.FS.mkdirTree(dir);
  pyodide.FS.writeFile(destPath, new Uint8Array(buf));
  return { bytesWritten: buf.byteLength, sourceFileSize: file.size };
}

window.ByteStaging = { stageFileHandleIntoPyodide };
