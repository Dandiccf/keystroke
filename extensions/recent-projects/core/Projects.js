.pragma library

var ICON = "󰨞"
var SECTION = "Recent projects"
var SETTINGS = [
  { key: "root", type: "boolean", label: "Show projects in the main search", "default": true,
    description: "Off: projects appear only after the proj command or on this extension's screen" },
  { key: "files", type: "boolean", label: "Include recent files", "default": false,
    description: "On: single files the editors opened are listed too, not only folders and workspaces" }
]
var KINDS = { folder: "--folder-uri", workspace: "--file-uri", file: "--file-uri" }

function request(ctx, id) {
  var explicit = !!ctx.command || ctx.scope === id
  var text = String(ctx.command ? ctx.command.rest : ctx.query || "").trim()
  var settings = ctx.settings || {}
  var allowed = explicit || (!ctx.scope && settings.root !== false && text.length >= 2)
  return { explicit: explicit, text: text, allowed: allowed, files: settings.files === true }
}

function argv(helper) { return ["python3", helper] }

function isArgv(value) {
  if (!Array.isArray(value)) return false
  for (var i = 0; i < value.length; i++) if (typeof value[i] !== "string" || !value[i]) return false
  return true
}

function str(value, fallback) { return typeof value === "string" ? value : fallback }

// Drops anything the launch argv could not be built from safely, so rows()
// only ever sees well-formed editors and entries. A URI always starts with a
// scheme, so it can never read as a flag.
function parse(text) {
  var value
  try { value = JSON.parse(text) } catch (_) { return { editors: [], error: "Could not read the recent project list" } }
  if (!value || !Array.isArray(value.editors)) return { editors: [], error: "Could not read the recent project list" }
  var editors = []
  for (var i = 0; i < value.editors.length; i++) {
    var e = value.editors[i]
    if (!e || typeof e.id !== "string" || typeof e.name !== "string" || !isArgv(e.launch) || !e.launch.length || !Array.isArray(e.entries)) continue
    var entries = []
    for (var j = 0; j < e.entries.length; j++) {
      var p = e.entries[j]
      if (!p || !KINDS.hasOwnProperty(p.kind) || typeof p.uri !== "string" || !/^[a-z][a-z0-9+.-]*:\/\//i.test(p.uri)) continue
      if (typeof p.title !== "string" || !p.title) continue
      var dir = str(p.dir, "")
      if (dir && dir.charAt(0) !== "/") continue
      entries.push({ kind: p.kind, uri: p.uri, title: p.title, where: str(p.where, ""), dir: dir, remote: str(p.remote, "") })
    }
    if (entries.length) editors.push({ id: e.id, name: e.name, launch: e.launch.slice(),
      icons: isArgv(e.icons) ? e.icons.slice() : [], terminal: isArgv(e.terminal) ? e.terminal.slice() : [], entries: entries })
  }
  return { editors: editors, error: typeof value.error === "string" ? value.error : "" }
}

function launch(editor, entry) { return editor.launch.concat([KINDS[entry.kind], entry.uri]) }

// A terminal in the folder itself, or in the folder that holds a file or workspace.
function terminal(editor, entry) {
  if (!editor.terminal.length || !entry.dir) return null
  return editor.terminal.concat(["--dir=" + entry.dir])
}

// A failed scan keeps the last list that had entries; a successful one,
// even an empty one, replaces it.
function merge(previous, next) {
  if (next.error && !next.editors.length && previous && previous.editors && previous.editors.length) return previous
  return next
}

function status(title, subtitle) {
  return { id: "status", title: title, subtitle: subtitle || "", icon: ICON, section: SECTION,
    tier: "item", score: 1, disabled: true, action: { type: "noop" } }
}

// iconFor maps a list of themed icon names to an image URL ("" when none is known).
function rows(data, req, iconFor) {
  var out = [], editors = data.editors || []
  for (var i = 0; i < editors.length; i++) {
    var e = editors[i]
    var iconSource = iconFor ? String(iconFor(e.icons) || "") : ""
    for (var j = 0; j < e.entries.length; j++) {
      var p = e.entries[j]
      if (p.kind === "file" && !req.files) continue
      var name = p.kind === "workspace" ? p.title + " (Workspace)" : p.title
      // The path is shared by every project under one folder ("git" would match
      // all of ~/git), so only the command and this screen search by it.
      var keywords = req.explicit ? [p.where, p.remote, e.name].join(" ") : ""
      var row = { id: e.id + ":" + p.uri, title: name,
        subtitle: [p.remote, p.where, e.name].filter(function(s) { return !!s }).join(" · "),
        icon: ICON, iconSource: iconSource, section: SECTION, keywords: keywords,
        tier: "item", order: out.length, remember: true,
        verb: "Open in " + e.name, action: { type: "exec", argv: launch(e, p) } }
      var term = terminal(e, p)
      if (term) { row.altVerb = "Open terminal"; row.altAction = { type: "exec", argv: term } }
      // An empty query lists everything (the editors' own order, frecency first); a typed one is left to the matcher.
      if (!req.text) row.score = 1
      out.push(row)
    }
  }
  if (req.explicit && data.error && !out.length) out.push(status(data.error))
  else if (req.explicit && !out.length) out.push(status("No recent projects found", "VS Code, VSCodium, Cursor and Windsurf are supported"))
  return out
}
