# flashcards-obsidian

Turn `==highlighted==` text (and other markers) in your Obsidian notes into Anki cards. Fork of [reuseman/flashcards-obsidian](https://github.com/reuseman/flashcards-obsidian) — see the upstream wiki for full feature docs.

## Install

1. Copy this folder into your vault's plugins folder:
   ```bash
   cp -r obsidian-plugins/flashcards-obsidian /path/to/your/vault/.obsidian/plugins/
   ```
2. Install [Anki](https://apps.ankiweb.net/) and the [AnkiConnect](https://ankiweb.net/shared/info/2055492159) add-on. Anki must be running for the plugin to work.
3. In Obsidian: Settings → Community plugins → enable "Flashcards".
4. Open the plugin's settings to pick the deck, note type, and field mappings you want cards to land in.

## Quick usage

- `==highlighted text==` becomes a cloze card
- `Question::Answer` becomes a basic card
- `Question:::Answer` becomes a reversed card
- Tag a note (or block) with `#card` to make a basic card
- Run the "Flashcards: Generate for the current file" command to push cards to Anki

Full feature list and syntax reference: https://github.com/reuseman/flashcards-obsidian/wiki

## License

MIT — see `LICENSE`. Original copyright Alex Colucci 2020.
