# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project status

A shopping list web app (add / edit / delete / check items). All 4 stages (skeleton, features, UI design, Playwright review) are done. In `style.css`, colors are `:root` variables with a `prefers-color-scheme: dark` override; the checkbox box is drawn with per-theme SVG data URIs (`--box*`) because SVG can't read CSS variables, so color changes must be made in both places. Edit/delete buttons hide their text with `font-size: 0` and show a masked icon, relying on `aria-label`. Planning docs:

- `PRD.md` — the source of truth for requirements (features F1–F6, data model, wireframe, acceptance criteria in section 9).
- `PROMPTS.md` — the PRD split into 4 staged prompts: 1) skeleton, 2) features, 3) UI design, 4) Playwright review. Work is expected to proceed in that order; don't implement later-stage concerns early (e.g. no feature logic in stage 1, no logic changes in stage 3).

The docs and the user's communication are in Korean; keep UI text and user-facing replies in Korean.

## Running

No build step, no dependencies, no package manager. Open `index.html` directly in a browser, or serve the folder with `python -m http.server 5500` (configured as `shopping-list` in `.claude/launch.json`) and open http://localhost:5500. Use the server for Playwright: it blocks `file://` URLs. There is no test runner or package.json. `tests/playwright-review.js` is a Playwright scenario (39 checks: PRD acceptance criteria, F1–F6 details, edge cases, keyboard/a11y, 360px layout) written as a function of `page`; with the server running, pass it to the Playwright MCP `browser_run_code_unsafe` tool as `filename: "tests/playwright-review.js"`. It returns JSON with `failed` listing any failing checks. It clears localStorage. `tests/screenshots/` holds reference screenshots.

## Architecture

Plain HTML + CSS + vanilla JS, three files: `index.html`, `style.css`, `app.js` (loaded with `<script defer>`).

`app.js` uses a single-state, re-render-everything pattern:

- State is one `items` array of `{ id, name, checked, createdAt }`, persisted as JSON in `localStorage` under the key `"shopping-list-items"`.
- Mutations go through `addItem`, `updateItem`, `deleteItem`, `toggleItem`, `clearChecked`; each mutates `items`, calls `saveItems()`, then `render()`. `render()` rebuilds the `<ul id="list">` and the "전체 N개 · 완료 M개" counter / empty-state message from state.
- List interactions are handled by event delegation on the `<ul>`, not per-item listeners.
- Only one item may be in edit mode at a time: `editingId` decides whether `render()` draws an item in view or edit form. The in-progress text lives in `editDraft` (updated on `input`), not in the DOM, so a re-render caused by touching another item doesn't wipe it.
- Every render replaces the list DOM, so any handler that re-renders must restore focus itself (`focusInItem(id, selector)`); otherwise keyboard focus drops to `<body>`. `render()` itself never moves focus — `startEditing` focuses the edit input.
- The edit-input Enter/Esc handler ignores `isComposing` / keyCode 229 so Korean IME composition doesn't trigger a save.

## Streamlit version

`streamlit_app.py` is a Python port of the same app. Run with `streamlit run streamlit_app.py` (or the `shopping-list-streamlit` launch config, port 8501). Differences from the web version:

- `shopping_list.json` (next to the script) is the source of truth, shared by every browser tab/session. Each run calls `refresh_items()`, and every mutation goes through `with mutate_items():` (lock → re-read file → modify → save). Never mutate `st.session_state.shopping_items` outside that block or cache it across runs — a stale session saving its whole list overwrites other tabs' changes. (The key is `shopping_items`, not `items`, which collides with the dict method.)
- Checkbox widget state is overwritten from the file before each render (`st.session_state[f"check_{id}"] = ...`), so don't also pass `value=`.
- All mutations are widget `on_click`/`on_change` callbacks, so state is updated before the rerun renders. Add and edit are `st.form`s so Enter submits; Esc-to-cancel isn't possible. The add form must use `clear_on_submit=True`; clearing `st.session_state.new_item` in the callback instead leaves the old value in the browser form and re-submits it on the next Enter.
- `tests/streamlit-review.js` is the Playwright review for this version (same `browser_run_code_unsafe` usage). It resets by deleting every item through the UI, so it wipes `shopping_list.json`. Known expected failures are Streamlit limitations: Esc, double-click-to-edit, focus moving after reruns, and pasting >100 chars (rejected instead of truncated).
- Checkbox labels are rendered as Markdown, so item names go through `escape_markdown()`, which backslash-escapes syntax and inserts U+2060 to break auto-links (`http://`, `www.`, emails).
- Mobile layout relies on injected CSS that stops Streamlit from stacking columns below 640px and targets widgets via `st-key-<key>` classes (`edit_*`, `delete_*`, `add_button`). Renaming those keys breaks the layout.

## Constraints that are easy to violate

- Render user input with `textContent`, never `innerHTML` (XSS — explicitly tested in stage 4).
- Wrap `localStorage` access and `JSON.parse` in try/catch; corrupt or unavailable storage must fall back to an empty list without breaking the app.
- Item names are trimmed, must be non-empty, max 100 chars. Saving an empty edit keeps the original value.
- Must work at 360px width without horizontal scroll, be fully keyboard-operable, and give icon buttons `aria-label`s (e.g. "우유 삭제").
