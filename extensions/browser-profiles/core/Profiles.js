.pragma library

var ICON = "󰖟"
var SECTION = "Browser profiles"
var SETTINGS = [
  { key: "root", type: "boolean", label: "Show profiles in the main search", "default": true,
    description: "Off: profiles appear only after the profile command or on this extension's screen" }
]

function request(ctx, id) {
  var explicit = !!ctx.command || ctx.scope === id
  var text = String(ctx.command ? ctx.command.rest : ctx.query || "").trim()
  var settings = ctx.settings || {}
  var allowed = explicit || (!ctx.scope && settings.root !== false && text.length >= 2)
  return { explicit: explicit, text: text, allowed: allowed }
}

function argv(helper) { return ["python3", helper] }

function isArgv(value) {
  if (!Array.isArray(value) || !value.length) return false
  for (var i = 0; i < value.length; i++) if (typeof value[i] !== "string" || !value[i]) return false
  return true
}

function isDirName(value) {
  return typeof value === "string" && !!value && value !== "." && value !== ".." && value.indexOf("/") < 0
}

// Drops anything the launch argv could not be built from safely, so rows()
// only ever sees well-formed browsers and profiles.
function parse(text) {
  var value
  try { value = JSON.parse(text) } catch (_) { return { browsers: [], error: "Could not read the browser profile list" } }
  if (!value || !Array.isArray(value.browsers)) return { browsers: [], error: "Could not read the browser profile list" }
  var browsers = []
  for (var i = 0; i < value.browsers.length; i++) {
    var b = value.browsers[i]
    if (!b || typeof b.id !== "string" || typeof b.name !== "string" || !isArgv(b.launch) || !Array.isArray(b.profiles)) continue
    if (b.family !== "chromium" && b.family !== "firefox") continue
    if (typeof b.private !== "string" || !/^--[a-z-]+$/.test(b.private)) continue
    var profiles = []
    for (var j = 0; j < b.profiles.length; j++) {
      var p = b.profiles[j]
      if (!p || typeof p.key !== "string" || !p.key || typeof p.name !== "string" || !p.name) continue
      if (b.family === "chromium" && !isDirName(p.dir)) continue
      if (b.family === "firefox" && p.key.charAt(0) !== "/") continue
      profiles.push({ key: p.key, name: p.name, dir: String(p.dir || ""), account: typeof p.account === "string" ? p.account : "" })
    }
    if (profiles.length) browsers.push({ id: b.id, name: b.name, family: b.family, icon: String(b.icon || ""),
      private: b.private, launch: b.launch.slice(), profiles: profiles })
  }
  return { browsers: browsers, error: typeof value.error === "string" ? value.error : "" }
}

function launch(browser, profile, privateWindow) {
  var out = browser.launch.slice()
  // Firefox by path: the directory the row id names is the one that opens.
  // Its --new-window requires a URL; --browser opens a window without one.
  if (browser.family === "firefox") out.push("--profile", profile.key, privateWindow ? browser.private : "--browser")
  else out.push("--profile-directory=" + profile.dir, privateWindow ? browser.private : "--new-window")
  return out
}

// A failed scan keeps the last list that had profiles; a successful one,
// even an empty one, replaces it.
function merge(previous, next) {
  if (next.error && !next.browsers.length && previous && previous.browsers && previous.browsers.length) return previous
  return next
}

function privateVerb(browser) {
  return browser.private === "--inprivate" ? "InPrivate window" : browser.private === "--incognito" ? "Incognito window" : "Private window"
}

function status(title, subtitle) {
  return { id: "status", title: title, subtitle: subtitle || "", icon: ICON, section: SECTION,
    tier: "item", score: 1, disabled: true, action: { type: "noop" } }
}

// iconFor maps a themed icon name to an image URL ("" when unknown).
function rows(data, req, iconFor) {
  var out = [], browsers = data.browsers || []
  for (var i = 0; i < browsers.length; i++) {
    var b = browsers[i], seen = {}, dup = {}
    for (var d = 0; d < b.profiles.length; d++) {
      var n = b.profiles[d].name.toLowerCase()
      if (seen[n]) dup[n] = true
      seen[n] = true
    }
    var iconSource = iconFor ? String(iconFor(b.icon) || "") : ""
    for (var j = 0; j < b.profiles.length; j++) {
      var p = b.profiles[j], extra = []
      if (p.account) extra.push(p.account)
      if (dup[p.name.toLowerCase()]) extra.push(p.dir || p.key)
      // The browser's name is shared by all its profiles: at the root it would
      // match every one of them, so only the profile command searches by it.
      var keywords = req.explicit ? [b.name, b.id, p.account].join(" ") : p.account
      var row = { id: b.id + ":" + p.key, title: p.name, subtitle: [b.name].concat(extra).join(" · "),
        icon: ICON, iconSource: iconSource, section: SECTION, keywords: keywords,
        tier: "item", order: out.length, remember: true,
        verb: "New window", altVerb: privateVerb(b),
        action: { type: "exec", argv: launch(b, p, false) },
        altAction: { type: "exec", argv: launch(b, p, true) } }
      // An empty query lists everything (frecency first); a typed one is left to the matcher.
      if (!req.text) row.score = 1
      out.push(row)
    }
  }
  if (req.explicit && data.error && !out.length) out.push(status(data.error))
  else if (req.explicit && !out.length) out.push(status("No browser profiles found", "Chromium-family browsers and Firefox-family browsers are supported"))
  return out
}
