'use strict';

var obsidian = require('obsidian');

/******************************************************************************
Copyright (c) Microsoft Corporation.

Permission to use, copy, modify, and/or distribute this software for any
purpose with or without fee is hereby granted.

THE SOFTWARE IS PROVIDED "AS IS" AND THE AUTHOR DISCLAIMS ALL WARRANTIES WITH
REGARD TO THIS SOFTWARE INCLUDING ALL IMPLIED WARRANTIES OF MERCHANTABILITY
AND FITNESS. IN NO EVENT SHALL THE AUTHOR BE LIABLE FOR ANY SPECIAL, DIRECT,
INDIRECT, OR CONSEQUENTIAL DAMAGES OR ANY DAMAGES WHATSOEVER RESULTING FROM
LOSS OF USE, DATA OR PROFITS, WHETHER IN AN ACTION OF CONTRACT, NEGLIGENCE OR
OTHER TORTIOUS ACTION, ARISING OUT OF OR IN CONNECTION WITH THE USE OR
PERFORMANCE OF THIS SOFTWARE.
***************************************************************************** */
/* global Reflect, Promise, SuppressedError, Symbol, Iterator */

var extendStatics = function(d, b) {
    extendStatics = Object.setPrototypeOf ||
        ({ __proto__: [] } instanceof Array && function (d, b) { d.__proto__ = b; }) ||
        function (d, b) { for (var p in b) if (Object.prototype.hasOwnProperty.call(b, p)) d[p] = b[p]; };
    return extendStatics(d, b);
};

function __extends(d, b) {
    if (typeof b !== "function" && b !== null)
        throw new TypeError("Class extends value " + String(b) + " is not a constructor or null");
    extendStatics(d, b);
    function __() { this.constructor = d; }
    d.prototype = b === null ? Object.create(b) : (__.prototype = b.prototype, new __());
}

function __awaiter(thisArg, _arguments, P, generator) {
    function adopt(value) { return value instanceof P ? value : new P(function (resolve) { resolve(value); }); }
    return new (P || (P = Promise))(function (resolve, reject) {
        function fulfilled(value) { try { step(generator.next(value)); } catch (e) { reject(e); } }
        function rejected(value) { try { step(generator["throw"](value)); } catch (e) { reject(e); } }
        function step(result) { result.done ? resolve(result.value) : adopt(result.value).then(fulfilled, rejected); }
        step((generator = generator.apply(thisArg, _arguments || [])).next());
    });
}

function __generator(thisArg, body) {
    var _ = { label: 0, sent: function() { if (t[0] & 1) throw t[1]; return t[1]; }, trys: [], ops: [] }, f, y, t, g = Object.create((typeof Iterator === "function" ? Iterator : Object).prototype);
    return g.next = verb(0), g["throw"] = verb(1), g["return"] = verb(2), typeof Symbol === "function" && (g[Symbol.iterator] = function() { return this; }), g;
    function verb(n) { return function (v) { return step([n, v]); }; }
    function step(op) {
        if (f) throw new TypeError("Generator is already executing.");
        while (g && (g = 0, op[0] && (_ = 0)), _) try {
            if (f = 1, y && (t = op[0] & 2 ? y["return"] : op[0] ? y["throw"] || ((t = y["return"]) && t.call(y), 0) : y.next) && !(t = t.call(y, op[1])).done) return t;
            if (y = 0, t) op = [op[0] & 2, t.value];
            switch (op[0]) {
                case 0: case 1: t = op; break;
                case 4: _.label++; return { value: op[1], done: false };
                case 5: _.label++; y = op[1]; op = [0]; continue;
                case 7: op = _.ops.pop(); _.trys.pop(); continue;
                default:
                    if (!(t = _.trys, t = t.length > 0 && t[t.length - 1]) && (op[0] === 6 || op[0] === 2)) { _ = 0; continue; }
                    if (op[0] === 3 && (!t || (op[1] > t[0] && op[1] < t[3]))) { _.label = op[1]; break; }
                    if (op[0] === 6 && _.label < t[1]) { _.label = t[1]; t = op; break; }
                    if (t && _.label < t[2]) { _.label = t[2]; _.ops.push(op); break; }
                    if (t[2]) _.ops.pop();
                    _.trys.pop(); continue;
            }
            op = body.call(thisArg, _);
        } catch (e) { op = [6, e]; y = 0; } finally { f = t = 0; }
        if (op[0] & 5) throw op[1]; return { value: op[0] ? op[1] : void 0, done: true };
    }
}

function __values(o) {
    var s = typeof Symbol === "function" && Symbol.iterator, m = s && o[s], i = 0;
    if (m) return m.call(o);
    if (o && typeof o.length === "number") return {
        next: function () {
            if (o && i >= o.length) o = void 0;
            return { value: o && o[i++], done: !o };
        }
    };
    throw new TypeError(s ? "Object is not iterable." : "Symbol.iterator is not defined.");
}

typeof SuppressedError === "function" ? SuppressedError : function (error, suppressed, message) {
    var e = new Error(message);
    return e.name = "SuppressedError", e.error = error, e.suppressed = suppressed, e;
};

var DEFAULT_SETTINGS = {
    deck: "Default",
    noteType: "Cloze",
    textField: "Text",
    extraField: "Extra",
    includeParagraph: false,
    ankiConnectPort: 8765,
};

var Anki = /** @class */ (function () {
    function Anki(port) {
        if (port === void 0) { port = 8765; }
        this.port = port;
    }
    Anki.prototype.addNote = function (params) {
        return __awaiter(this, void 0, void 0, function () {
            return __generator(this, function (_a) {
                return [2 /*return*/, this.invoke("addNote", 6, {
                        note: {
                            deckName: params.deckName,
                            modelName: params.modelName,
                            fields: params.fields,
                            tags: params.tags,
                            options: { allowDuplicate: false },
                        },
                    })];
            });
        });
    };
    Anki.prototype.ping = function () {
        return __awaiter(this, void 0, void 0, function () {
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, this.invoke("version", 6)];
                    case 1: return [2 /*return*/, (_a.sent()) === 6];
                }
            });
        });
    };
    Anki.prototype.invoke = function (action, version, params) {
        var _this = this;
        if (version === void 0) { version = 6; }
        if (params === void 0) { params = {}; }
        return new Promise(function (resolve, reject) {
            var xhr = new XMLHttpRequest();
            xhr.addEventListener("error", function () {
                return reject("Failed to connect to AnkiConnect. Is Anki running?");
            });
            xhr.addEventListener("load", function () {
                try {
                    var response = JSON.parse(xhr.responseText);
                    if (response.error) {
                        throw response.error;
                    }
                    resolve(response.result);
                }
                catch (e) {
                    reject(e);
                }
            });
            xhr.timeout = 5000;
            xhr.addEventListener("timeout", function () {
                return reject("AnkiConnect request timed out");
            });
            xhr.open("POST", "http://127.0.0.1:".concat(_this.port));
            xhr.send(JSON.stringify({ action: action, version: version, params: params }));
        });
    };
    return Anki;
}());

var SettingsTab = /** @class */ (function (_super) {
    __extends(SettingsTab, _super);
    function SettingsTab() {
        return _super !== null && _super.apply(this, arguments) || this;
    }
    SettingsTab.prototype.display = function () {
        var containerEl = this.containerEl;
        var plugin = this.plugin;
        containerEl.empty();
        containerEl.createEl("h1", { text: "Flashcards - Settings" });
        new obsidian.Setting(containerEl)
            .setName("Test Anki connection")
            .setDesc("Check that AnkiConnect is reachable.")
            .addButton(function (btn) {
            btn.setButtonText("Test").onClick(function () {
                new Anki(plugin.settings.ankiConnectPort)
                    .ping()
                    .then(function () { return new obsidian.Notice("Anki connected ✓"); })
                    .catch(function () { return new obsidian.Notice("Cannot reach Anki. Is it running?"); });
            });
        });
        containerEl.createEl("h2", { text: "Anki" });
        new obsidian.Setting(containerEl)
            .setName("Deck name")
            .setDesc("The deck where cards will be added.")
            .addText(function (text) {
            return text
                .setValue(plugin.settings.deck)
                .setPlaceholder("Default")
                .onChange(function (value) {
                plugin.settings.deck = value || "Default";
                plugin.saveData(plugin.settings);
            });
        });
        new obsidian.Setting(containerEl)
            .setName("Note type")
            .setDesc("The Anki note type to use (must be a cloze type).")
            .addText(function (text) {
            return text
                .setValue(plugin.settings.noteType)
                .setPlaceholder("Cloze")
                .onChange(function (value) {
                plugin.settings.noteType = value || "Cloze";
                plugin.saveData(plugin.settings);
            });
        });
        containerEl.createEl("h2", { text: "Field mapping" });
        new obsidian.Setting(containerEl)
            .setName("Text field name")
            .setDesc("The field that receives the cloze text.")
            .addText(function (text) {
            return text
                .setValue(plugin.settings.textField)
                .setPlaceholder("Text")
                .onChange(function (value) {
                plugin.settings.textField = value || "Text";
                plugin.saveData(plugin.settings);
            });
        });
        new obsidian.Setting(containerEl)
            .setName("Extra field name")
            .setDesc("The field that receives the source link (and optionally the surrounding paragraph).")
            .addText(function (text) {
            return text
                .setValue(plugin.settings.extraField)
                .setPlaceholder("Extra")
                .onChange(function (value) {
                plugin.settings.extraField = value || "Extra";
                plugin.saveData(plugin.settings);
            });
        });
        new obsidian.Setting(containerEl)
            .setName("Include surrounding paragraph")
            .setDesc("Add the full paragraph to the Extra field alongside the source link.")
            .addToggle(function (toggle) {
            return toggle
                .setValue(plugin.settings.includeParagraph)
                .onChange(function (value) {
                plugin.settings.includeParagraph = value;
                plugin.saveData(plugin.settings);
            });
        });
        containerEl.createEl("h2", { text: "Advanced" });
        new obsidian.Setting(containerEl)
            .setName("AnkiConnect port")
            .setDesc("The port AnkiConnect listens on.")
            .addText(function (text) {
            return text
                .setValue(String(plugin.settings.ankiConnectPort))
                .setPlaceholder("8765")
                .onChange(function (value) {
                var port = parseInt(value, 10);
                if (port > 0 && port <= 65535) {
                    plugin.settings.ankiConnectPort = port;
                    plugin.saveData(plugin.settings);
                }
            });
        });
    };
    return SettingsTab;
}(obsidian.PluginSettingTab));

var PreviewModal = /** @class */ (function (_super) {
    __extends(PreviewModal, _super);
    function PreviewModal(app, cards, settings, tag, onDone) {
        var _this = _super.call(this, app) || this;
        _this.cards = cards;
        _this.settings = settings;
        _this.tag = tag;
        _this.onDone = onDone;
        return _this;
    }
    PreviewModal.prototype.onOpen = function () {
        var _this = this;
        var contentEl = this.contentEl;
        contentEl.empty();
        contentEl.addClass("flashcards-preview-modal");
        var style = contentEl.createEl("style");
        style.textContent = "\n      .flashcards-preview-modal { padding: 0; }\n      .flashcards-preview-modal .modal-header {\n        display: flex; justify-content: space-between; align-items: center;\n        padding: 12px 16px; border-bottom: 1px solid var(--background-modifier-border);\n      }\n      .flashcards-preview-modal .modal-header h2 { margin: 0; font-size: 1.1em; }\n      .flashcards-preview-modal .card-list {\n        max-height: 60vh; overflow-y: auto; padding: 8px 16px;\n      }\n      .flashcards-preview-modal .card-item {\n        display: flex; gap: 10px; align-items: flex-start;\n        padding: 10px 0; border-bottom: 1px solid var(--background-modifier-border);\n      }\n      .flashcards-preview-modal .card-item:last-child { border-bottom: none; }\n      .flashcards-preview-modal .card-item.disabled { opacity: 0.4; }\n      .flashcards-preview-modal .card-checkbox { margin-top: 6px; flex-shrink: 0; }\n      .flashcards-preview-modal .card-content { flex: 1; min-width: 0; }\n      .flashcards-preview-modal .card-header {\n        display: flex; justify-content: space-between; align-items: center;\n        margin-bottom: 4px;\n      }\n      .flashcards-preview-modal .card-num {\n        font-size: 0.75em; color: var(--text-muted);\n      }\n      .flashcards-preview-modal .card-tabs {\n        display: flex; gap: 0;\n      }\n      .flashcards-preview-modal .card-tab {\n        font-size: 0.75em; padding: 2px 10px; cursor: pointer;\n        border: 1px solid var(--background-modifier-border);\n        background: var(--background-secondary);\n        color: var(--text-muted);\n      }\n      .flashcards-preview-modal .card-tab:first-child {\n        border-radius: 4px 0 0 4px;\n      }\n      .flashcards-preview-modal .card-tab:last-child {\n        border-radius: 0 4px 4px 0;\n        border-left: none;\n      }\n      .flashcards-preview-modal .card-tab.active {\n        background: var(--interactive-accent);\n        color: var(--text-on-accent);\n        border-color: var(--interactive-accent);\n      }\n      .flashcards-preview-modal .card-textarea {\n        width: 100%; min-height: 60px; resize: vertical;\n        font-family: var(--font-interface); font-size: 0.85em;\n        padding: 8px; border: 1px solid var(--background-modifier-border);\n        border-radius: 4px; background: var(--background-primary);\n        color: var(--text-normal);\n      }\n      .flashcards-preview-modal .card-textarea:focus {\n        border-color: var(--interactive-accent); outline: none;\n      }\n      .flashcards-preview-modal .modal-footer {\n        display: flex; justify-content: space-between; align-items: center;\n        padding: 12px 16px; border-top: 1px solid var(--background-modifier-border);\n      }\n      .flashcards-preview-modal .send-btn {\n        background: var(--interactive-accent); color: var(--text-on-accent);\n        border: none; padding: 6px 16px; border-radius: 4px;\n        cursor: pointer; font-size: 0.9em;\n      }\n      .flashcards-preview-modal .send-btn:hover { opacity: 0.9; }\n      .flashcards-preview-modal .count-label {\n        font-size: 0.85em; color: var(--text-muted);\n      }\n    ";
        // Header
        var header = contentEl.createDiv({ cls: "modal-header" });
        header.createEl("h2", { text: "Flashcard Preview" });
        var selectAll = header.createEl("label");
        var selectAllCheckbox = selectAll.createEl("input", { type: "checkbox" });
        selectAllCheckbox.checked = true;
        selectAll.appendText(" Select all");
        selectAllCheckbox.addEventListener("change", function () {
            var checked = selectAllCheckbox.checked;
            _this.cards.forEach(function (c) { return (c.enabled = checked); });
            _this.renderCards(cardList);
            _this.updateCount(countLabel);
        });
        // Card list
        var cardList = contentEl.createDiv({ cls: "card-list" });
        this.renderCards(cardList);
        // Footer
        var footer = contentEl.createDiv({ cls: "modal-footer" });
        var countLabel = footer.createSpan({ cls: "count-label" });
        this.updateCount(countLabel);
        var sendBtn = footer.createEl("button", {
            cls: "send-btn",
            text: "Send to Anki",
        });
        sendBtn.addEventListener("click", function () { return _this.sendCards(); });
    };
    PreviewModal.prototype.renderCards = function (container) {
        var _this = this;
        container.empty();
        this.cards.forEach(function (card, idx) {
            var item = container.createDiv({
                cls: "card-item".concat(card.enabled ? "" : " disabled"),
            });
            var checkbox = item.createEl("input", {
                type: "checkbox",
                cls: "card-checkbox",
            });
            checkbox.checked = card.enabled;
            checkbox.addEventListener("change", function () {
                card.enabled = checkbox.checked;
                item.toggleClass("disabled", !card.enabled);
                _this.updateCount(_this.contentEl.querySelector(".count-label"));
            });
            var content = item.createDiv({ cls: "card-content" });
            // Header row: card number + tabs
            var cardHeader = content.createDiv({ cls: "card-header" });
            cardHeader.createDiv({ cls: "card-num", text: "Card ".concat(idx + 1) });
            var tabs = cardHeader.createDiv({ cls: "card-tabs" });
            var frontTab = tabs.createDiv({ cls: "card-tab active", text: "Front" });
            var backTab = tabs.createDiv({ cls: "card-tab", text: "Back" });
            // Front: editable textarea
            var textarea = content.createEl("textarea", { cls: "card-textarea" });
            textarea.value = card.clozeText;
            textarea.addEventListener("input", function () {
                card.clozeText = textarea.value;
            });
            // Back: editable textarea
            var extraTextarea = content.createEl("textarea", { cls: "card-textarea" });
            extraTextarea.value = card.displayExtra;
            extraTextarea.addEventListener("input", function () {
                card.extraContent = extraTextarea.value;
            });
            extraTextarea.style.display = "none";
            // Tab switching
            frontTab.addEventListener("click", function () {
                frontTab.addClass("active");
                backTab.removeClass("active");
                textarea.style.display = "";
                extraTextarea.style.display = "none";
            });
            backTab.addEventListener("click", function () {
                backTab.addClass("active");
                frontTab.removeClass("active");
                textarea.style.display = "none";
                extraTextarea.style.display = "";
                // Auto-resize back textarea when shown
                extraTextarea.style.height = "auto";
                extraTextarea.style.height =
                    extraTextarea.scrollHeight + "px";
            });
            // Auto-resize textarea
            var autoResize = function () {
                textarea.style.height = "auto";
                textarea.style.height =
                    textarea.scrollHeight + "px";
            };
            textarea.addEventListener("input", autoResize);
            setTimeout(autoResize, 0);
        });
    };
    PreviewModal.prototype.updateCount = function (label) {
        var enabled = this.cards.filter(function (c) { return c.enabled; }).length;
        label.textContent = "".concat(enabled, " of ").concat(this.cards.length, " cards selected");
    };
    PreviewModal.prototype.sendCards = function () {
        return __awaiter(this, void 0, void 0, function () {
            var enabled, anki, added, skipped, errors, enabled_1, enabled_1_1, card, fields, e_1, msg, e_2_1, notice;
            var e_2, _a;
            return __generator(this, function (_b) {
                switch (_b.label) {
                    case 0:
                        enabled = this.cards.filter(function (c) { return c.enabled; });
                        if (enabled.length === 0) {
                            new obsidian.Notice("No cards selected.");
                            return [2 /*return*/];
                        }
                        anki = new Anki(this.settings.ankiConnectPort);
                        added = 0;
                        skipped = 0;
                        errors = [];
                        _b.label = 1;
                    case 1:
                        _b.trys.push([1, 8, 9, 10]);
                        enabled_1 = __values(enabled), enabled_1_1 = enabled_1.next();
                        _b.label = 2;
                    case 2:
                        if (!!enabled_1_1.done) return [3 /*break*/, 7];
                        card = enabled_1_1.value;
                        fields = {};
                        fields[this.settings.textField] = card.clozeText;
                        fields[this.settings.extraField] = card.extraContent;
                        _b.label = 3;
                    case 3:
                        _b.trys.push([3, 5, , 6]);
                        return [4 /*yield*/, anki.addNote({
                                deckName: this.settings.deck,
                                modelName: this.settings.noteType,
                                fields: fields,
                                tags: this.tag ? [this.tag] : [],
                            })];
                    case 4:
                        _b.sent();
                        added++;
                        return [3 /*break*/, 6];
                    case 5:
                        e_1 = _b.sent();
                        msg = String(e_1);
                        if (msg.includes("duplicate")) {
                            skipped++;
                        }
                        else {
                            errors.push(msg);
                        }
                        return [3 /*break*/, 6];
                    case 6:
                        enabled_1_1 = enabled_1.next();
                        return [3 /*break*/, 2];
                    case 7: return [3 /*break*/, 10];
                    case 8:
                        e_2_1 = _b.sent();
                        e_2 = { error: e_2_1 };
                        return [3 /*break*/, 10];
                    case 9:
                        try {
                            if (enabled_1_1 && !enabled_1_1.done && (_a = enabled_1.return)) _a.call(enabled_1);
                        }
                        finally { if (e_2) throw e_2.error; }
                        return [7 /*endfinally*/];
                    case 10:
                        notice = "Added ".concat(added, " card").concat(added !== 1 ? "s" : "");
                        if (skipped > 0)
                            notice += ", ".concat(skipped, " duplicate").concat(skipped !== 1 ? "s" : "", " skipped");
                        if (errors.length > 0)
                            notice += ", ".concat(errors.length, " error").concat(errors.length !== 1 ? "s" : "");
                        new obsidian.Notice(notice);
                        if (errors.length > 0)
                            console.error("Flashcards errors:", errors);
                        this.close();
                        this.onDone();
                        return [2 /*return*/];
                }
            });
        });
    };
    PreviewModal.prototype.onClose = function () {
        this.contentEl.empty();
    };
    return PreviewModal;
}(obsidian.Modal));

var FlashcardsPlugin = /** @class */ (function (_super) {
    __extends(FlashcardsPlugin, _super);
    function FlashcardsPlugin() {
        return _super !== null && _super.apply(this, arguments) || this;
    }
    FlashcardsPlugin.prototype.onload = function () {
        return __awaiter(this, void 0, void 0, function () {
            var _a, _b, _c, _d, anki, statusBar;
            var _this = this;
            return __generator(this, function (_e) {
                switch (_e.label) {
                    case 0:
                        _a = this;
                        _c = (_b = Object).assign;
                        _d = [{},
                            DEFAULT_SETTINGS];
                        return [4 /*yield*/, this.loadData()];
                    case 1:
                        _a.settings = _c.apply(_b, _d.concat([_e.sent()]));
                        anki = new Anki(this.settings.ankiConnectPort);
                        statusBar = this.addStatusBarItem();
                        this.addCommand({
                            id: "create-cloze-from-highlights",
                            name: "Create cloze from highlights",
                            editorCallback: function (editor) {
                                _this.createClozeFromHighlights(editor);
                            },
                        });
                        this.addSettingTab(new SettingsTab(this.app, this));
                        this.registerInterval(window.setInterval(function () {
                            return anki
                                .ping()
                                .then(function () { return statusBar.setText("Anki ⚡️"); })
                                .catch(function () { return statusBar.setText(""); });
                        }, 15 * 1000));
                        return [2 /*return*/];
                }
            });
        });
    };
    FlashcardsPlugin.prototype.onunload = function () {
        return __awaiter(this, void 0, void 0, function () {
            return __generator(this, function (_a) {
                switch (_a.label) {
                    case 0: return [4 /*yield*/, this.saveData(this.settings)];
                    case 1:
                        _a.sent();
                        return [2 /*return*/];
                }
            });
        });
    };
    FlashcardsPlugin.prototype.stripMarkdown = function (text) {
        // [[alias|display]] → display
        var result = text.replace(/\[\[([^\]]*?\|)(.*?)\]\]/g, "$2");
        // [[page]] → page
        result = result.replace(/\[\[(.*?)\]\]/g, "$1");
        // [text](url) → text
        result = result.replace(/\[([^\]]*)\]\([^)]*\)/g, "$1");
        // Footnote references [^14] → remove
        result = result.replace(/\[\^[^\]]*\]/g, "");
        // **bold** and *italic*
        result = result.replace(/\*\*(.+?)\*\*/g, "$1");
        result = result.replace(/\*(.+?)\*/g, "$1");
        // __bold__ and _italic_
        result = result.replace(/__(.+?)__/g, "$1");
        result = result.replace(/\b_(.+?)_\b/g, "$1");
        return result;
    };
    FlashcardsPlugin.prototype.splitIntoSentences = function (text) {
        // Tokenize: protect URLs, footnotes, markdown links, and decimals from
        // being split on their internal periods.
        // Replace protected periods with a placeholder, split, then restore.
        var placeholder = "\x00";
        var protected_ = text;
        // Protect URLs (http://..., https://..., www.)
        protected_ = protected_.replace(/https?:\/\/[^\s)\]]+/g, function (m) {
            return m.replace(/\./g, placeholder);
        });
        // Protect footnote refs like [^14]
        protected_ = protected_.replace(/\[\^[^\]]+\]/g, function (m) {
            return m.replace(/\./g, placeholder);
        });
        // Protect decimals (digit.digit)
        protected_ = protected_.replace(/(\d)\.(\d)/g, "$1".concat(placeholder, "$2"));
        // Now split on sentence-ending punctuation followed by:
        // - whitespace then an uppercase letter or bracket/paren (new sentence), OR
        // - end of string
        var sentences = [];
        var re = /.*?[.?!。？！]+(?:\[\^[^\]]*\])?(?=\s+[A-Z\[\("'""]|\s*$)/g;
        var m;
        var lastIndex = 0;
        while ((m = re.exec(protected_)) !== null) {
            var restored = m[0].replace(new RegExp(placeholder, "g"), ".").trim();
            if (restored)
                sentences.push(restored);
            lastIndex = re.lastIndex;
        }
        var remainder = protected_
            .slice(lastIndex)
            .replace(new RegExp(placeholder, "g"), ".")
            .trim();
        if (remainder)
            sentences.push(remainder);
        // If splitting produced nothing useful, return the whole text as one sentence
        if (sentences.length === 0 && text.trim()) {
            sentences.push(text.trim());
        }
        return sentences;
    };
    FlashcardsPlugin.prototype.createClozeFromHighlights = function (editor) {
        return __awaiter(this, void 0, void 0, function () {
            var fullText, allLines, paraGroups, groupStart, i, cardSentences, _loop_1, this_1, i, activeFile, noteTitle, vaultName, obsidianUri, tag, cards, _loop_2, this_2, cardSentences_1, cardSentences_1_1, _a, sentence, paragraph;
            var e_1, _b;
            var _this = this;
            return __generator(this, function (_c) {
                fullText = editor.getValue();
                // Check if there are any highlights at all
                if (!/==.+?==/g.test(fullText)) {
                    new obsidian.Notice("No ==highlights== found on this page.");
                    return [2 /*return*/];
                }
                allLines = fullText.split("\n");
                paraGroups = [];
                groupStart = -1;
                for (i = 0; i < allLines.length; i++) {
                    if (allLines[i].trim() !== "") {
                        if (groupStart === -1)
                            groupStart = i;
                    }
                    else {
                        if (groupStart !== -1) {
                            paraGroups.push({ start: groupStart, end: i - 1 });
                            groupStart = -1;
                        }
                    }
                }
                if (groupStart !== -1)
                    paraGroups.push({ start: groupStart, end: allLines.length - 1 });
                cardSentences = [];
                _loop_1 = function (i) {
                    var e_2, _d;
                    var line = allLines[i].trim();
                    if (!line)
                        return "continue";
                    // Strip leading list markers (- , * , 1. ) for sentence extraction
                    var stripped = line.replace(/^\s*(?:[-*]\s+|\d+\.\s+)/, "");
                    var sentences = this_1.splitIntoSentences(stripped);
                    try {
                        for (var sentences_1 = (e_2 = void 0, __values(sentences)), sentences_1_1 = sentences_1.next(); !sentences_1_1.done; sentences_1_1 = sentences_1.next()) {
                            var sentence = sentences_1_1.value;
                            if (/==.+?==/.test(sentence)) {
                                // Find which paragraph group this line belongs to
                                var group = paraGroups.find(function (g) { return i >= g.start && i <= g.end; });
                                var paragraph = group
                                    ? allLines.slice(group.start, group.end + 1).join("\n")
                                    : line;
                                cardSentences.push({ sentence: sentence, paragraph: paragraph });
                            }
                        }
                    }
                    catch (e_2_1) { e_2 = { error: e_2_1 }; }
                    finally {
                        try {
                            if (sentences_1_1 && !sentences_1_1.done && (_d = sentences_1.return)) _d.call(sentences_1);
                        }
                        finally { if (e_2) throw e_2.error; }
                    }
                };
                this_1 = this;
                for (i = 0; i < allLines.length; i++) {
                    _loop_1(i);
                }
                if (cardSentences.length === 0) {
                    new obsidian.Notice("No ==highlights== found on this page.");
                    return [2 /*return*/];
                }
                activeFile = this.app.workspace.getActiveFile();
                if (!activeFile) {
                    new obsidian.Notice("No active file.");
                    return [2 /*return*/];
                }
                noteTitle = activeFile.basename;
                vaultName = this.app.vault.getName();
                obsidianUri = "obsidian://open?vault=".concat(encodeURIComponent(vaultName), "&file=").concat(encodeURIComponent(activeFile.path));
                tag = noteTitle
                    .replace(/\s+/g, "_")
                    .replace(/[^\w\u3000-\u9FFF\uF900-\uFAFF_-]/g, "");
                cards = [];
                _loop_2 = function (sentence, paragraph) {
                    var cleaned = this_2.stripMarkdown(sentence);
                    var clozeNum = 0;
                    var clozeText = cleaned.replace(/==(.+?)==/g, function (_match, inner) {
                        clozeNum++;
                        return "{{c".concat(clozeNum, "::").concat(_this.stripMarkdown(inner), "}}");
                    });
                    if (clozeNum === 0)
                        return "continue";
                    var extraContent = "<a href=\"".concat(obsidianUri, "\">").concat(noteTitle, "</a>");
                    var displayExtra = noteTitle;
                    if (this_2.settings.includeParagraph) {
                        var cleanParagraph = this_2.stripMarkdown(paragraph.replace(/==(.+?)==/g, "$1"));
                        extraContent += "<br><br>".concat(cleanParagraph);
                        displayExtra += "\n\n".concat(cleanParagraph);
                    }
                    cards.push({ clozeText: clozeText, extraContent: extraContent, displayExtra: displayExtra, enabled: true });
                };
                this_2 = this;
                try {
                    for (cardSentences_1 = __values(cardSentences), cardSentences_1_1 = cardSentences_1.next(); !cardSentences_1_1.done; cardSentences_1_1 = cardSentences_1.next()) {
                        _a = cardSentences_1_1.value, sentence = _a.sentence, paragraph = _a.paragraph;
                        _loop_2(sentence, paragraph);
                    }
                }
                catch (e_1_1) { e_1 = { error: e_1_1 }; }
                finally {
                    try {
                        if (cardSentences_1_1 && !cardSentences_1_1.done && (_b = cardSentences_1.return)) _b.call(cardSentences_1);
                    }
                    finally { if (e_1) throw e_1.error; }
                }
                if (cards.length === 0) {
                    new obsidian.Notice("No ==highlights== found on this page.");
                    return [2 /*return*/];
                }
                new PreviewModal(this.app, cards, this.settings, tag, function () { }).open();
                return [2 /*return*/];
            });
        });
    };
    return FlashcardsPlugin;
}(obsidian.Plugin));

module.exports = FlashcardsPlugin;
//# sourceMappingURL=data:application/json;charset=utf-8;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoibWFpbi5qcyIsInNvdXJjZXMiOlsibm9kZV9tb2R1bGVzL3RzbGliL3RzbGliLmVzNi5qcyIsInNyYy9jb25mL3NldHRpbmdzLnRzIiwic3JjL3NlcnZpY2VzL2Fua2kudHMiLCJzcmMvZ3VpL3NldHRpbmdzLXRhYi50cyIsInNyYy9ndWkvcHJldmlldy1tb2RhbC50cyIsIm1haW4udHMiXSwic291cmNlc0NvbnRlbnQiOm51bGwsIm5hbWVzIjpbIlNldHRpbmciLCJOb3RpY2UiLCJQbHVnaW5TZXR0aW5nVGFiIiwiTW9kYWwiLCJQbHVnaW4iXSwibWFwcGluZ3MiOiI7Ozs7QUFBQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBO0FBQ0E7QUFDQTtBQUNBLElBQUksYUFBYSxHQUFHLFNBQVMsQ0FBQyxFQUFFLENBQUMsRUFBRTtBQUNuQyxJQUFJLGFBQWEsR0FBRyxNQUFNLENBQUMsY0FBYztBQUN6QyxTQUFTLEVBQUUsU0FBUyxFQUFFLEVBQUUsRUFBRSxZQUFZLEtBQUssSUFBSSxVQUFVLENBQUMsRUFBRSxDQUFDLEVBQUUsRUFBRSxDQUFDLENBQUMsU0FBUyxHQUFHLENBQUMsQ0FBQyxFQUFFLENBQUM7QUFDcEYsUUFBUSxVQUFVLENBQUMsRUFBRSxDQUFDLEVBQUUsRUFBRSxLQUFLLElBQUksQ0FBQyxJQUFJLENBQUMsRUFBRSxJQUFJLE1BQU0sQ0FBQyxTQUFTLENBQUMsY0FBYyxDQUFDLElBQUksQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLENBQUMsQ0FBQyxHQUFHLENBQUMsQ0FBQyxDQUFDLENBQUMsQ0FBQyxFQUFFLENBQUM7QUFDMUcsSUFBSSxPQUFPLGFBQWEsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLENBQUM7QUFDL0IsQ0FBQyxDQUFDO0FBQ0Y7QUFDTyxTQUFTLFNBQVMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxFQUFFO0FBQ2hDLElBQUksSUFBSSxPQUFPLENBQUMsS0FBSyxVQUFVLElBQUksQ0FBQyxLQUFLLElBQUk7QUFDN0MsUUFBUSxNQUFNLElBQUksU0FBUyxDQUFDLHNCQUFzQixHQUFHLE1BQU0sQ0FBQyxDQUFDLENBQUMsR0FBRywrQkFBK0IsQ0FBQyxDQUFDO0FBQ2xHLElBQUksYUFBYSxDQUFDLENBQUMsRUFBRSxDQUFDLENBQUMsQ0FBQztBQUN4QixJQUFJLFNBQVMsRUFBRSxHQUFHLEVBQUUsSUFBSSxDQUFDLFdBQVcsR0FBRyxDQUFDLENBQUMsRUFBRTtBQUMzQyxJQUFJLENBQUMsQ0FBQyxTQUFTLEdBQUcsQ0FBQyxLQUFLLElBQUksR0FBRyxNQUFNLENBQUMsTUFBTSxDQUFDLENBQUMsQ0FBQyxJQUFJLEVBQUUsQ0FBQyxTQUFTLEdBQUcsQ0FBQyxDQUFDLFNBQVMsRUFBRSxJQUFJLEVBQUUsRUFBRSxDQUFDLENBQUM7QUFDekYsQ0FBQztBQW9GRDtBQUNPLFNBQVMsU0FBUyxDQUFDLE9BQU8sRUFBRSxVQUFVLEVBQUUsQ0FBQyxFQUFFLFNBQVMsRUFBRTtBQUM3RCxJQUFJLFNBQVMsS0FBSyxDQUFDLEtBQUssRUFBRSxFQUFFLE9BQU8sS0FBSyxZQUFZLENBQUMsR0FBRyxLQUFLLEdBQUcsSUFBSSxDQUFDLENBQUMsVUFBVSxPQUFPLEVBQUUsRUFBRSxPQUFPLENBQUMsS0FBSyxDQUFDLENBQUMsRUFBRSxDQUFDLENBQUMsRUFBRTtBQUNoSCxJQUFJLE9BQU8sS0FBSyxDQUFDLEtBQUssQ0FBQyxHQUFHLE9BQU8sQ0FBQyxFQUFFLFVBQVUsT0FBTyxFQUFFLE1BQU0sRUFBRTtBQUMvRCxRQUFRLFNBQVMsU0FBUyxDQUFDLEtBQUssRUFBRSxFQUFFLElBQUksRUFBRSxJQUFJLENBQUMsU0FBUyxDQUFDLElBQUksQ0FBQyxLQUFLLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxPQUFPLENBQUMsRUFBRSxFQUFFLE1BQU0sQ0FBQyxDQUFDLENBQUMsQ0FBQyxFQUFFLEVBQUU7QUFDbkcsUUFBUSxTQUFTLFFBQVEsQ0FBQyxLQUFLLEVBQUUsRUFBRSxJQUFJLEVBQUUsSUFBSSxDQUFDLFNBQVMsQ0FBQyxPQUFPLENBQUMsQ0FBQyxLQUFLLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxPQUFPLENBQUMsRUFBRSxFQUFFLE1BQU0sQ0FBQyxDQUFDLENBQUMsQ0FBQyxFQUFFLEVBQUU7QUFDdEcsUUFBUSxTQUFTLElBQUksQ0FBQyxNQUFNLEVBQUUsRUFBRSxNQUFNLENBQUMsSUFBSSxHQUFHLE9BQU8sQ0FBQyxNQUFNLENBQUMsS0FBSyxDQUFDLEdBQUcsS0FBSyxDQUFDLE1BQU0sQ0FBQyxLQUFLLENBQUMsQ0FBQyxJQUFJLENBQUMsU0FBUyxFQUFFLFFBQVEsQ0FBQyxDQUFDLEVBQUU7QUFDdEgsUUFBUSxJQUFJLENBQUMsQ0FBQyxTQUFTLEdBQUcsU0FBUyxDQUFDLEtBQUssQ0FBQyxPQUFPLEVBQUUsVUFBVSxJQUFJLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxDQUFDLENBQUM7QUFDOUUsS0FBSyxDQUFDLENBQUM7QUFDUCxDQUFDO0FBQ0Q7QUFDTyxTQUFTLFdBQVcsQ0FBQyxPQUFPLEVBQUUsSUFBSSxFQUFFO0FBQzNDLElBQUksSUFBSSxDQUFDLEdBQUcsRUFBRSxLQUFLLEVBQUUsQ0FBQyxFQUFFLElBQUksRUFBRSxXQUFXLEVBQUUsSUFBSSxDQUFDLENBQUMsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxFQUFFLE1BQU0sQ0FBQyxDQUFDLENBQUMsQ0FBQyxDQUFDLENBQUMsT0FBTyxDQUFDLENBQUMsQ0FBQyxDQUFDLENBQUMsRUFBRSxFQUFFLElBQUksRUFBRSxFQUFFLEVBQUUsR0FBRyxFQUFFLEVBQUUsRUFBRSxFQUFFLENBQUMsRUFBRSxDQUFDLEVBQUUsQ0FBQyxFQUFFLENBQUMsR0FBRyxNQUFNLENBQUMsTUFBTSxDQUFDLENBQUMsT0FBTyxRQUFRLEtBQUssVUFBVSxHQUFHLFFBQVEsR0FBRyxNQUFNLEVBQUUsU0FBUyxDQUFDLENBQUM7QUFDck0sSUFBSSxPQUFPLENBQUMsQ0FBQyxJQUFJLEdBQUcsSUFBSSxDQUFDLENBQUMsQ0FBQyxFQUFFLENBQUMsQ0FBQyxPQUFPLENBQUMsR0FBRyxJQUFJLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLFFBQVEsQ0FBQyxHQUFHLElBQUksQ0FBQyxDQUFDLENBQUMsRUFBRSxPQUFPLE1BQU0sS0FBSyxVQUFVLEtBQUssQ0FBQyxDQUFDLE1BQU0sQ0FBQyxRQUFRLENBQUMsR0FBRyxXQUFXLEVBQUUsT0FBTyxJQUFJLENBQUMsRUFBRSxDQUFDLEVBQUUsQ0FBQyxDQUFDO0FBQ2hLLElBQUksU0FBUyxJQUFJLENBQUMsQ0FBQyxFQUFFLEVBQUUsT0FBTyxVQUFVLENBQUMsRUFBRSxFQUFFLE9BQU8sSUFBSSxDQUFDLENBQUMsQ0FBQyxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUMsRUFBRSxDQUFDLEVBQUU7QUFDdEUsSUFBSSxTQUFTLElBQUksQ0FBQyxFQUFFLEVBQUU7QUFDdEIsUUFBUSxJQUFJLENBQUMsRUFBRSxNQUFNLElBQUksU0FBUyxDQUFDLGlDQUFpQyxDQUFDLENBQUM7QUFDdEUsUUFBUSxPQUFPLENBQUMsS0FBSyxDQUFDLEdBQUcsQ0FBQyxFQUFFLEVBQUUsQ0FBQyxDQUFDLENBQUMsS0FBSyxDQUFDLEdBQUcsQ0FBQyxDQUFDLENBQUMsRUFBRSxDQUFDLEVBQUUsSUFBSTtBQUN0RCxZQUFZLElBQUksQ0FBQyxHQUFHLENBQUMsRUFBRSxDQUFDLEtBQUssQ0FBQyxHQUFHLEVBQUUsQ0FBQyxDQUFDLENBQUMsR0FBRyxDQUFDLEdBQUcsQ0FBQyxDQUFDLFFBQVEsQ0FBQyxHQUFHLEVBQUUsQ0FBQyxDQUFDLENBQUMsR0FBRyxDQUFDLENBQUMsT0FBTyxDQUFDLEtBQUssQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLFFBQVEsQ0FBQyxLQUFLLENBQUMsQ0FBQyxJQUFJLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLElBQUksQ0FBQyxJQUFJLENBQUMsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLElBQUksQ0FBQyxDQUFDLEVBQUUs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TyxDQUFDLEVBQUUsRUFBRSxFQUFFLEdBQUcsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxDQUFDLENBQUMsQ0FBQyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEVBQUUsU0FBUyxFQUFFLENBQUMsR0FBRyxDQUFDLEdBQUcsQ0FBQyxDQUFDLEVBQUU7QUFDbEUsUUFBUSxJQUFJLEVBQUUsQ0FBQyxDQUFDLENBQUMsR0FBRyxDQUFDLEVBQUUsTUFBTSxFQUFFLENBQUMsQ0FBQyxDQUFDLENBQUMsQ0FBQyxPQUFPLEVBQUUsS0FBSyxFQUFFLEVBQUUsQ0FBQyxDQUFDLENBQUMsR0FBRyxFQUFFLENBQUMsQ0FBQyxDQUFDLEdBQUcsS0FBSyxDQUFDLEVBQUUsSUFBSSxFQUFFLElBQUksRUFBRSxDQUFDO0FBQ3pGLEtBQUs7QUFDTCxDQUFDO0FBaUJEO0FBQ08sU0FBUyxRQUFRLENBQUMsQ0FBQyxFQUFFO0FBQzVCLElBQUksSUFBSSxDQUFDLEdBQUcsT0FBTyxNQUFNLEtBQUssVUFBVSxJQUFJLE1BQU0sQ0FBQyxRQUFRLEVBQUUsQ0FBQyxHQUFHLENBQUMsSUFBSSxDQUFDLENBQUMsQ0FBQyxDQUFDLEVBQUUsQ0FBQyxHQUFHLENBQUMsQ0FBQztBQUNsRixJQUFJLElBQUksQ0FBQyxFQUFFLE9BQU8sQ0FBQyxDQUFDLElBQUksQ0FBQyxDQUFDLENBQUMsQ0FBQztBQUM1QixJQUFJLElBQUksQ0FBQyxJQUFJLE9BQU8sQ0FBQyxDQUFDLE1BQU0sS0FBSyxRQUFRLEVBQUUsT0FBTztBQUNsRCxRQUFRLElBQUksRUFBRSxZQUFZO0FBQzFCLFlBQVksSUFBSSxDQUFDLElBQUksQ0FBQyxJQUFJLENBQUMsQ0FBQyxNQUFNLEVBQUUsQ0FBQyxHQUFHLEtBQUssQ0FBQyxDQUFDO0FBQy9DLFlBQVksT0FBTyxFQUFFLEtBQUssRUFBRSxDQUFDLElBQUksQ0FBQyxDQUFDLENBQUMsRUFBRSxDQUFDLEVBQUUsSUFBSSxFQUFFLENBQUMsQ0FBQyxFQUFFLENBQUM7QUFDcEQsU0FBUztBQUNULEtBQUssQ0FBQztBQUNOLElBQUksTUFB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LENBQUEsTUFBQSxDQUFBLFNBQVMsU0FBTSxDQUFDO29CQUMvRCxJQUFJLFlBQVksR0FBRyxTQUFTLENBQUM7QUFDN0Isb0JBQUEsSUFBSSxNQUFLLENBQUEsUUFBUSxDQUFDLGdCQUFnQixFQUFFO0FBQ2xDLHdCQUFBLElBQU0sY0FBYyxHQUFHLE1BQUssQ0FBQSxhQUFhLENBQ3ZDLFNBQVMsQ0FBQyxPQUFPLENBQUMsWUFBWSxFQUFFLElBQUksQ0FBQyxDQUN0QyxDQUFDO0FBQ0Ysd0JBQUEsWUFBWSxJQUFJLFVBQUEsQ0FBQSxNQUFBLENBQVcsY0FBYyxDQUFFLENBQUM7QUFDNUMsd0JBQUEsWUFBWSxJQUFJLE1BQUEsQ0FBQSxNQUFBLENBQU8sY0FBYyxDQUFFLENBQUM7cUJBQ3pDO0FBRUQsb0JBQUEsS0FBSyxDQUFDLElBQUksQ0FBQyxFQUFFLFNBQVMsRUFBQSxTQUFBLEVBQUUsWUFBWSxFQUFBLFlBQUEsRUFBRSxZQUFZLGNBQUEsRUFBRSxPQUFPLEVBQUUsSUFBSSxFQUFFLENBQUMsQ0FBQzs7OztvQkFyQnZFLEtBQXNDLGVBQUEsR0FBQSxRQUFBLENBQUEsYUFBYSxDQUFBLEVBQUEsaUJBQUEsR0FBQSxlQUFBLENBQUEsSUFBQSxFQUFBLEVBQUEsQ0FBQSxpQkFBQSxDQUFBLElBQUEsRUFBQSxpQkFBQSxHQUFBLGVBQUEsQ0FBQSxJQUFBLEVBQUEsRUFBQTtBQUF4Qyx3QkFBQSxFQUFBLEdBQUEsaUJBQUEsQ0FBQSxLQUF1QixFQUFyQixRQUFRLEdBQUEsRUFBQSxDQUFBLFFBQUEsRUFBRSxTQUFTLEdBQUEsRUFBQSxDQUFBLFNBQUEsQ0FBQTtBQUFuQix3QkFBQSxPQUFBLENBQUEsUUFBUSxFQUFFLFNBQVMsQ0FBQSxDQUFBO0FBc0IvQixxQkFBQTs7Ozs7Ozs7O0FBRUQsZ0JBQUEsSUFBSSxLQUFLLENBQUMsTUFBTSxLQUFLLENBQUMsRUFBRTtBQUN0QixvQkFBQSxJQUFJQSxlQUFNLENBQUMsdUNBQXVDLENBQUMsQ0FBQztvQkFDcEQsT0FBTyxDQUFBLENBQUEsWUFBQSxDQUFBO2lCQUNSO2dCQUVELElBQUksWUFBWSxDQUFDLElBQUksQ0FBQyxHQUFHLEVBQUUsS0FBSyxFQUFFLElBQUksQ0FBQyxRQUFRLEVBQUUsR0FBRyxFQUFFLFlBQU8sR0FBQyxDQUFDLENBQUMsSUFBSSxFQUFFLENBQUM7Ozs7QUFDeEUsS0FBQSxDQUFBO0lBQ0gsT0FBQyxnQkFBQSxDQUFBO0FBQUQsQ0EzTUEsQ0FBOENHLGVBQU0sQ0EyTW5EOzs7OyIsInhfZ29vZ2xlX2lnbm9yZUxpc3QiOlswXX0=
