  // Loads the shared body.html into #app-root, then loads scriptPaths in
  // order (each waits for the previous to finish, same as static <script>
  // tags would) before any of them run. Lets ui.html and ui/web/index.html
  // share one body markup file instead of two hand-synced copies - this is
  // the only thing both shells load identically; everything else (the
  // <head>, and this very script list) still differs per shell on purpose.
  function loadShell(bodyPath, scriptPaths) {
    return fetch(bodyPath)
      .then(r => r.text())
      .then(html => {
        document.getElementById("app-root").innerHTML = html;
        return scriptPaths.reduce((chain, src) => chain.then(() => new Promise((resolve, reject) => {
          const s = document.createElement("script");
          s.src = src;
          s.onload = resolve;
          s.onerror = () => reject(new Error("Failed to load " + src));
          document.body.appendChild(s);
        })), Promise.resolve());
      });
  }
