import QtQuick
import QtTest
import "../core/Profiles.js" as Profiles

TestCase {
  name: "BrowserProfiles"

  readonly property string sample: JSON.stringify({ browsers: [
    { id: "microsoft-edge", name: "Microsoft Edge", family: "chromium", icon: "microsoft-edge", private: "--inprivate",
      launch: ["uwsm-app", "--", "/usr/bin/microsoft-edge-stable"],
      profiles: [ { key: "Default", dir: "Default", name: "Work", account: "me@example.org" },
                  { key: "Profile 1", dir: "Profile 1", name: "Personal", account: "" },
                  { key: "Profile 2", dir: "Profile 2", name: "personal", account: "" },
                  { key: "../x", dir: "../x", name: "Escape", account: "" },
                  { key: "..", dir: "..", name: "Parent", account: "" } ] },
    { id: "firefox", name: "Firefox", family: "firefox", icon: "firefox", private: "--private-window",
      launch: ["/usr/bin/firefox"], profiles: [ { key: "/home/me/.mozilla/firefox/abc.default", dir: "", name: "-P evil" },
                                           { key: "relative.default", dir: "", name: "Relative" } ] },
    { id: "bad", name: "Bad", family: "chromium", private: "--incognito; rm", launch: ["x"], profiles: [ { key: "a", dir: "a", name: "A" } ] },
    { id: "empty", name: "Empty", family: "chromium", private: "--incognito", launch: [], profiles: [ { key: "a", dir: "a", name: "A" } ] }
  ] })

  function test_request() {
    compare(Profiles.request({ query: "w", scope: "" }, "browser-profiles").allowed, false)
    verify(Profiles.request({ query: "wo", scope: "" }, "browser-profiles").allowed)
    verify(!Profiles.request({ query: "work", scope: "", settings: { root: false } }, "browser-profiles").allowed)
    verify(!Profiles.request({ query: "work", scope: "files" }, "browser-profiles").allowed)
    var cmd = Profiles.request({ query: "profile ", command: { rest: "" }, scope: "", settings: { root: false } }, "browser-profiles")
    verify(cmd.allowed && cmd.explicit)
    compare(cmd.text, "")
    verify(Profiles.request({ query: "", scope: "browser-profiles" }, "browser-profiles").explicit)
  }

  function test_parse_filters_unsafe_entries() {
    var data = Profiles.parse(sample)
    compare(data.browsers.length, 2)
    compare(data.browsers[0].profiles.length, 3)
    compare(data.browsers[1].profiles.length, 1)
    verify(Profiles.parse("nope").error.length > 0)
    verify(Profiles.parse('{"browsers":{}}').error.length > 0)
  }

  function test_launch_argv() {
    var data = Profiles.parse(sample), edge = data.browsers[0], fx = data.browsers[1]
    compare(Profiles.launch(edge, edge.profiles[1], false),
            ["uwsm-app", "--", "/usr/bin/microsoft-edge-stable", "--profile-directory=Profile 1", "--new-window"])
    compare(Profiles.launch(edge, edge.profiles[1], true),
            ["uwsm-app", "--", "/usr/bin/microsoft-edge-stable", "--profile-directory=Profile 1", "--inprivate"])
    // Firefox opens the directory the row id names, never a name that could collide or read as a flag.
    compare(Profiles.launch(fx, fx.profiles[0], false), ["/usr/bin/firefox", "--profile", "/home/me/.mozilla/firefox/abc.default", "--browser"])
    compare(Profiles.launch(fx, fx.profiles[0], true), ["/usr/bin/firefox", "--profile", "/home/me/.mozilla/firefox/abc.default", "--private-window"])
  }

  function test_rows() {
    var data = Profiles.parse(sample)
    var listed = Profiles.rows(data, { explicit: true, text: "" }, function(name) { return "file:///icons/" + name + ".png" })
    compare(listed.length, 4)
    compare(listed[0].id, "microsoft-edge:Default")
    compare(listed[0].subtitle, "Microsoft Edge · me@example.org")
    compare(listed[0].score, 1)
    compare(listed[0].iconSource, "file:///icons/microsoft-edge.png")
    verify(listed[0].remember)
    compare(listed[0].verb, "New window")
    compare(listed[0].altVerb, "InPrivate window")
    compare(listed[3].altVerb, "Private window")
    // Two profiles with the same name are told apart by their directory.
    compare(listed[1].subtitle, "Microsoft Edge · Profile 1")
    compare(listed[2].subtitle, "Microsoft Edge · Profile 2")
    verify(listed[0].keywords.indexOf("Microsoft Edge") >= 0)
    // At the root the browser name is not a keyword: "edge" must not match every Edge profile.
    var typed = Profiles.rows(data, { explicit: false, text: "work" }, null)
    compare(typed[0].keywords, "me@example.org")
    compare(typed[1].keywords, "")
    compare(typed[0].score, undefined)
    compare(typed[0].iconSource, "")
    compare(typed[0].id, listed[0].id)
  }

  function test_merge() {
    var good = { browsers: [{ id: "a", profiles: [{}] }], error: "" }
    var empty = { browsers: [], error: "" }
    var failed = { browsers: [], error: "Timed out" }
    compare(Profiles.merge(good, failed), good)           // a failed rescan keeps the last list
    compare(Profiles.merge(good, empty), empty)           // an empty success replaces it
    compare(Profiles.merge(null, failed), failed)         // a first failure is shown
    compare(Profiles.merge(empty, failed), failed)
    var other = { browsers: [{ id: "b", profiles: [{}] }], error: "" }
    compare(Profiles.merge(good, other), other)
  }

  function test_empty_and_errors() {
    compare(Profiles.rows({ browsers: [] }, { explicit: false, text: "wo" }), [])
    compare(Profiles.rows({ browsers: [] }, { explicit: true, text: "" })[0].title, "No browser profiles found")
    compare(Profiles.rows({ browsers: [], error: "Broken" }, { explicit: true, text: "" })[0].title, "Broken")
    verify(Profiles.rows({ browsers: [] }, { explicit: true, text: "" })[0].disabled)
  }
}
