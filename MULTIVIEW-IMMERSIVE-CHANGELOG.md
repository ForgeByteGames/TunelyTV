# TunelyTV Multi-View v0.9.1 — immersive display

- Full-viewport screen: opening Multi-View hides the original player and covers the channel sidebar, page header, and the rest of the web page. Scrolling the page is disabled until exit.
- Two-pane landscape side-by-side and two-pane portrait stacked layouts. Four-pane 2×2 grid on desktop and mobile.
- Player tiles stretch to consume available grid height and width, while the original video is `object-fit:contain` to avoid stretching/cropping programming. Aspect-ratio mismatch may therefore create black bars.
- Channel selector appears on demand by clicking Channels or the unoccupied pane. Compact audio and stop controls are overlaid on each tile, rather than reducing video height.
- Native fullscreen is optional and browser-dependent; full-viewport CSS layout works without native fullscreen. Exit restores document scrolling, stops Multi-View stream connections, and returns the single-view player.
- Provider authorization, HTTPS/CORS/codec support, device decoding power and simultaneous connection limits still apply; no channels bundled.

## Validation
Test full-viewport coverage, per-pane size on mobile/desktop, layout switching, channel selection, single active audio, exit, scroll restore, fullscreen controls, and all existing backend tests. Real live authorized sources still require end-to-end testing after deployment.
