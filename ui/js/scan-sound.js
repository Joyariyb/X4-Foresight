  // Core role: Plays the "scan complete" voice cue, shared by both shells.

  // The two shells live at different folder depths (ui/ui.html vs
  // ui/web/index.html), so a path relative to the *document* would resolve
  // differently in each build. Resolving against this script's own URL instead
  // gives one correct absolute URL in both - scan-sound.js and the asset keep a
  // fixed relationship (ui/js -> ui/assets) no matter which shell loaded us.
  // currentScript is read at top-level execution because it's only valid while
  // the script body is running synchronously, not later inside play().
  const _scanSoundUrl = new URL("../assets/scan_complete.wav", document.currentScript.src).href;

  // Preloaded once so the cue fires instantly on scan completion rather than
  // racing a fetch. Kept module-scoped (single instance) - replaying just
  // rewinds it, which is fine since two scans can't complete on the same frame.
  const _scanSound = new Audio(_scanSoundUrl);
  _scanSound.preload = "auto";

  // Called from requestNewScan()'s success branch. The .play() promise is
  // swallowed because it can reject (e.g. browser autoplay policy) - the cue is
  // a nicety, never worth surfacing an error or blocking the scan flow. In
  // practice it's always inside the New Scan click's user-gesture context, so
  // the policy permits it.
  function playScanComplete() {
    try {
      _scanSound.currentTime = 0;
      const p = _scanSound.play();
      if (p && p.catch) p.catch(() => {});
    } catch (e) { /* no audio device / unsupported - stay silent */ }
  }
