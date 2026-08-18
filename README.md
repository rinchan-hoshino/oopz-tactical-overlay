# Oopz Tactical Link

A private Windows tactical text HUD for Oopz.

## Player-visible behavior

- the transparent history and input bar remain visible by default and pass mouse input through to the game;
- the configured global hotkey (`F8` by default) is the only way to enter input mode; no foreground-process identification is used;
- input mode uses the native Windows/Qt text editor so caret, selection, and glyph geometry stay identical; `Enter` sends non-empty text, while empty `Enter`, `Esc`, opening settings, or switching to another window exits immediately;
- the tray icon opens settings on left click; its right-click menu contains only Exit;
- the Oopz voice server currently occupied by the user is detected and locked; only that server's text channels are selectable;
- sender names come directly from one batched Oopz person-profile lookup and are cached; images, stickers, audio and files use readable placeholders;
- settings apply immediately without any game-process configuration and include a 9–20 pt HUD font-size control;
- settings show the running version and live updater state: checking, current, download percentage, ready to restart, or retry on failure; the tray tooltip mirrors it;
- F8 is the default activation key; existing saved hotkey choices are preserved rather than rewritten;
- stale pending updates are discarded instead of downgrading a newer EXE; target replacement retries while Nuitka's bootstrap releases the file, and a failed apply restarts the old app with a visible retry status rather than trapping startup in a loop;
- v0.4.4 fixes full-controller startup after the updater-status change, records startup exceptions under the app state directory, and makes packaged smoke tests construct the complete controller rather than isolated widgets only;
- v0.5.0 removes all process identification so F8 is universal, and adds a native onefile startup splash plus a versioned extraction cache so activation is immediately visible and later launches are faster;
- v0.5.1 removes HUD drop shadows, pins passive mode to the newest message while preserving active-mode scroll position, and explicitly attaches to the foreground input thread before focusing the editor;
- v0.5.2 uses a true antialiased vector-path outline for HUD and typed text, and keeps geometry, resize affordance and input appearance identical across passive and F8-active states; F8 now changes only focus and input capture;
- v0.6.0 standardizes all UI text on Microsoft YaHei UI, adds a 9–20 pt HUD size setting, thins the message contour, replaces the double-painted custom input with one native editor, removes the active full-screen mouse shield, and exits input mode when focus leaves the overlay;
- v0.6.1 restores a fully transparent input surface, ends and locks input before emitting an Enter submission, and gives history text, input, and drag mode one persisted HUD width while the resize grip floats above that geometry;
- v0.6.2 keeps the transparent input while restoring one true outlined glyph layer aligned from the native cursor rectangle; native invisible glyphs retain selection/hit testing without double paint, while a bright two-pixel active underline and gold caret make activation and insertion position explicit;
- HUD position is changed by dragging the HUD itself; the input window starts at half the previous width and its resize grip persists a custom size;
- Oopz channel sync reuses the current Windows user's local Oopz session. The overlay never asks for an account password.

## Distribution and updates

Canonical download:

`https://acv.k-neco.com/tools/oopz-tactical-overlay/OopzTacticalOverlay.exe`

Update manifest:

`https://acv.k-neco.com/tools/oopz-tactical-overlay/latest.json`

The app checks the manifest after startup. A newer executable is downloaded to the per-user state directory, verified against the manifest size and SHA-256, and applied on the next launch through a temporary copy of the current executable.

## Safety boundary

- Windows only;
- borderless-window games only;
- no DLL injection, process inspection, process-memory access, keyboard hook or microphone routing;
- global hotkey observation uses ordinary Win32 key-state polling;
- the imported Oopz session is stored only in the current user's DPAPI-protected state;
- Oopz integration depends on an unofficial API surface and may need maintenance after Oopz updates.

State path:

`%LOCALAPPDATA%\RinChan\OopzTacticalOverlay\state.bin`

## License

MIT © 2026 RinChan. See [`LICENSE`](LICENSE).
