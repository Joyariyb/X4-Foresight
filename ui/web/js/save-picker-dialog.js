// Minimal modal listing save files for the user to pick from, replacing the
// desktop app's native SaveSelectDialog. Self-contained (injects its own
// styles) so Phase 5 doesn't need new CSS files wired into ui/web/index.html.

function showSavePickerDialog(files) {
  return new Promise((resolve) => {
    const overlay = document.createElement("div");
    overlay.style.cssText =
      "position:fixed;inset:0;background:rgba(0,0,0,0.6);z-index:9999;" +
      "display:flex;align-items:center;justify-content:center;font-family:sans-serif";

    const box = document.createElement("div");
    box.style.cssText =
      "background:#161b22;border:1px solid #30363d;border-radius:8px;" +
      "min-width:360px;max-width:480px;max-height:70vh;overflow:auto;" +
      "color:#e6edf3;padding:16px";

    const title = document.createElement("div");
    title.textContent = "Choose a save file";
    title.style.cssText = "font-size:15px;font-weight:600;margin-bottom:12px";
    box.appendChild(title);

    function close(result) {
      document.body.removeChild(overlay);
      resolve(result);
    }

    if (files.length === 0) {
      const empty = document.createElement("div");
      empty.textContent = "No save files found.";
      empty.style.cssText = "opacity:0.7;padding:8px 0";
      box.appendChild(empty);
    }

    for (const file of files) {
      const row = document.createElement("div");
      row.style.cssText =
        "padding:10px 12px;border-radius:6px;cursor:pointer;margin-bottom:4px;" +
        "display:flex;justify-content:space-between;gap:12px";
      row.onmouseenter = () => { row.style.background = "#21262d"; };
      row.onmouseleave = () => { row.style.background = "transparent"; };
      row.onclick = () => close(file);

      const name = document.createElement("span");
      name.textContent = file.name;
      const when = document.createElement("span");
      when.textContent = new Date(file.lastModified).toLocaleString();
      when.style.cssText = "opacity:0.6;font-size:12px";

      row.appendChild(name);
      row.appendChild(when);
      box.appendChild(row);
    }

    const cancelBtn = document.createElement("button");
    cancelBtn.textContent = "Cancel";
    cancelBtn.style.cssText =
      "margin-top:12px;padding:6px 14px;background:#21262d;border:1px solid #30363d;" +
      "border-radius:6px;color:#e6edf3;cursor:pointer";
    cancelBtn.onclick = () => close(null);
    box.appendChild(cancelBtn);

    overlay.appendChild(box);
    document.body.appendChild(overlay);
  });
}
