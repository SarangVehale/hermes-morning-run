'use strict';

const obsidian = require('obsidian');

class UnreadDotPlugin extends obsidian.Plugin {

  async onload() {
    this._refreshScheduled = false;
    this.app.workspace.onLayoutReady(() => {
      this.refreshAllDots();
    });

    // Command: copy current callout to clipboard with "expand on this" prompt
    this.addCommand({
      id: 'copy-callout-to-claude',
      name: 'Copy callout to clipboard for Claude',
      editorCallback: (editor) => {
        const cursor = editor.getCursor();
        const lineCount = editor.lineCount();
        let startLine = cursor.line;
        let endLine = cursor.line;

        // Find callout start — walk up to find "> [!"
        while (startLine > 0 && !editor.getLine(startLine).match(/^>\s*\[!/)) {
          startLine--;
        }

        // If we didn't find a callout, just copy the current line
        if (!editor.getLine(startLine).match(/^>\s*\[!/)) {
          navigator.clipboard.writeText(editor.getLine(cursor.line));
          new obsidian.Notice('Line copied to clipboard');
          return;
        }

        // Find callout end — walk down while lines start with >
        endLine = startLine + 1;
        while (endLine < lineCount && editor.getLine(endLine).match(/^>/)) {
          endLine++;
        }

        // Extract callout content
        const lines = [];
        for (let i = startLine; i < endLine; i++) {
          lines.push(editor.getLine(i));
        }

        // Build clipboard text with prompt
        const calloutText = lines.join('\n');
        const title = lines[0].replace(/^>\s*\[!.*?\]-?\s*/, '');
        const clipText = `Expand on this:\n\n${title}\n\n${calloutText}`;

        navigator.clipboard.writeText(clipText);
        new obsidian.Notice('Copied to clipboard — paste into Claude');
      }
    });

    // Dim past days' callouts in reading view
    this.registerMarkdownPostProcessor((el) => {
      this.dimPastDays(el);
    });

    // Also dim on layout change (switching views)
    this.registerEvent(
      this.app.workspace.on('active-leaf-change', () => {
        setTimeout(() => this.dimPastDaysInActiveView(), 300);
      })
    );

    // When a file is opened, mark it as read
    this.registerEvent(
      this.app.workspace.on('file-open', (file) => {
        if (file) this.onFileOpen(file);
      })
    );

    // When frontmatter changes, update dots for that file + parent folders
    this.registerEvent(
      this.app.metadataCache.on('changed', (file) => {
        this.refreshDotForPath(file.path);
        this.refreshFolderDots();
      })
    );

    // Re-apply dots when layout rebuilds the file explorer DOM (debounced to avoid infinite loop)
    this.registerEvent(
      this.app.workspace.on('layout-change', () => {
        this.scheduleRefresh();
      })
    );

    // Re-apply on file create/delete/rename
    this.registerEvent(this.app.vault.on('create', () => this.scheduleRefresh()));
    this.registerEvent(this.app.vault.on('delete', () => this.scheduleRefresh()));
    this.registerEvent(this.app.vault.on('rename', () => this.scheduleRefresh()));

    // Right-click context menu: "Mark all as read" on folders
    this.registerEvent(
      this.app.workspace.on('file-menu', (menu, abstractFile) => {
        if (!(abstractFile instanceof obsidian.TFolder)) return;
        const unreadFiles = this.getUnreadFilesInFolder(abstractFile);
        if (unreadFiles.length === 0) return;

        menu.addItem((item) => {
          item
            .setTitle(`Mark all as read (${unreadFiles.length})`)
            .setIcon('check-check')
            .onClick(async () => {
              for (const file of unreadFiles) {
                try {
                  await this.app.fileManager.processFrontMatter(file, (fm) => {
                    fm.unread = false;
                  });
                } catch (e) {
                  console.error('unread-dot: failed to mark as read', file.path, e);
                }
              }
              this.refreshAllDots();
              new obsidian.Notice(`Marked ${unreadFiles.length} files as read`);
            });
        });
      })
    );
  }

  onunload() {
    document.querySelectorAll('.unread-dot').forEach(el => el.remove());
  }

  getFileExplorer() {
    const leaves = this.app.workspace.getLeavesOfType('file-explorer');
    if (leaves.length === 0) return null;
    return leaves[0].view;
  }

  isUnread(file) {
    if (!(file instanceof obsidian.TFile)) return false;
    if (file.extension !== 'md') return false;
    const cache = this.app.metadataCache.getFileCache(file);
    return cache?.frontmatter?.unread === true;
  }

  // Get all unread .md files inside a folder (recursively)
  getUnreadFilesInFolder(folder) {
    const unread = [];
    for (const child of folder.children) {
      if (child instanceof obsidian.TFile && this.isUnread(child)) {
        unread.push(child);
      } else if (child instanceof obsidian.TFolder) {
        unread.push(...this.getUnreadFilesInFolder(child));
      }
    }
    return unread;
  }

  // Check if a folder has any unread files (recursively)
  folderHasUnread(folder) {
    for (const child of folder.children) {
      if (child instanceof obsidian.TFile && this.isUnread(child)) {
        return true;
      } else if (child instanceof obsidian.TFolder && this.folderHasUnread(child)) {
        return true;
      }
    }
    return false;
  }

  scheduleRefresh() {
    if (this._refreshScheduled) return;
    this._refreshScheduled = true;
    setTimeout(() => {
      this._refreshScheduled = false;
      this.refreshAllDots();
    }, 200);
  }

  refreshAllDots() {
    const explorer = this.getFileExplorer();
    if (!explorer || !explorer.fileItems) return;

    for (const path in explorer.fileItems) {
      if (!Object.prototype.hasOwnProperty.call(explorer.fileItems, path)) continue;
      const item = explorer.fileItems[path];
      if (!item?.selfEl) continue;

      // Remove existing dot
      const existing = item.selfEl.querySelector('.unread-dot');
      if (existing) existing.remove();

      const abstractFile = this.app.vault.getAbstractFileByPath(path);
      if (!abstractFile) continue;

      // File: show dot if unread
      if (abstractFile instanceof obsidian.TFile && this.isUnread(abstractFile)) {
        this.addDot(item.selfEl);
      }
      // Folder: show dot if any child is unread
      else if (abstractFile instanceof obsidian.TFolder && this.folderHasUnread(abstractFile)) {
        this.addDot(item.selfEl);
      }
    }
  }

  // Refresh only folder dots (called after a single file changes)
  refreshFolderDots() {
    const explorer = this.getFileExplorer();
    if (!explorer || !explorer.fileItems) return;

    for (const path in explorer.fileItems) {
      if (!Object.prototype.hasOwnProperty.call(explorer.fileItems, path)) continue;
      const abstractFile = this.app.vault.getAbstractFileByPath(path);
      if (!(abstractFile instanceof obsidian.TFolder)) continue;

      const item = explorer.fileItems[path];
      if (!item?.selfEl) continue;

      const existing = item.selfEl.querySelector('.unread-dot');
      if (existing) existing.remove();

      if (this.folderHasUnread(abstractFile)) {
        this.addDot(item.selfEl);
      }
    }
  }

  addDot(el) {
    const dot = document.createElement('span');
    dot.classList.add('unread-dot');
    el.appendChild(dot);
  }

  async onFileOpen(file) {
    if (!(file instanceof obsidian.TFile)) return;
    if (file.extension !== 'md') return;

    // Check if file is currently unread
    const cache = this.app.metadataCache.getFileCache(file);
    if (cache?.frontmatter?.unread !== true) return;

    // Mark as read
    try {
      await this.app.fileManager.processFrontMatter(file, (fm) => {
        fm.unread = false;
      });
    } catch (e) {
      console.error('unread-dot: failed to update frontmatter', e);
    }

    // Remove the dot immediately and update folder dots
    this.refreshDotForPath(file.path);
    this.refreshFolderDots();
  }

  getTodayStr() {
    const d = new Date();
    const yyyy = d.getFullYear();
    const mm = String(d.getMonth() + 1).padStart(2, '0');
    const dd = String(d.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
  }

  dimPastDays(el) {
    const today = this.getTodayStr();
    // Find internal links that look like dates (YYYY-MM-DD)
    const links = el.querySelectorAll('a.internal-link');
    links.forEach(link => {
      const text = link.getAttribute('data-href') || link.textContent || '';
      const match = text.match(/^\d{4}-\d{2}-\d{2}$/);
      if (!match) return;
      const dateStr = match[0];

      if (dateStr < today) {
        // Walk up to find the list item container, then dim all callouts inside it
        let listItem = link.closest('li');
        if (listItem) {
          listItem.classList.add('past-day');
        }
        // Also dim sibling callouts that follow this list item
        if (listItem) {
          let sibling = listItem.nextElementSibling;
          while (sibling) {
            if (sibling.classList && sibling.classList.contains('callout')) {
              sibling.classList.add('past-day');
            }
            // Stop if we hit another list item (next day)
            if (sibling.tagName === 'LI') break;
            sibling = sibling.nextElementSibling;
          }
        }
      }
    });

    // Also handle callouts that are direct siblings after the list
    const callouts = el.querySelectorAll('.callout');
    callouts.forEach(callout => {
      // Check if a preceding list item has .past-day
      let prev = callout.previousElementSibling;
      while (prev) {
        if (prev.classList && prev.classList.contains('past-day')) {
          callout.classList.add('past-day');
          break;
        }
        if (prev.tagName === 'LI' || (prev.tagName === 'UL' || prev.tagName === 'OL')) {
          // Check inside the list for past-day items
          const pastItems = prev.querySelectorAll('.past-day');
          if (pastItems.length > 0) {
            callout.classList.add('past-day');
          }
          break;
        }
        if (prev.classList && prev.classList.contains('callout') && !prev.classList.contains('past-day')) {
          break;
        }
        prev = prev.previousElementSibling;
      }
    });
  }

  dimPastDaysInActiveView() {
    const view = this.app.workspace.getActiveViewOfType(obsidian.MarkdownView);
    if (!view) return;
    const container = view.contentEl;
    if (container) {
      this.dimPastDays(container);
    }
  }

  refreshDotForPath(path) {
    const explorer = this.getFileExplorer();
    if (!explorer || !explorer.fileItems) return;

    const item = explorer.fileItems[path];
    if (!item?.selfEl) return;

    const existing = item.selfEl.querySelector('.unread-dot');
    if (existing) existing.remove();

    const abstractFile = this.app.vault.getAbstractFileByPath(path);
    if (abstractFile && this.isUnread(abstractFile)) {
      this.addDot(item.selfEl);
    }
  }
}

module.exports = UnreadDotPlugin;
