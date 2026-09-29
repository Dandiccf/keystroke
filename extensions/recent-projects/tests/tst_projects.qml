import QtQuick
import QtTest
import "../core/Projects.js" as Projects

TestCase {
  name: "RecentProjects"

  readonly property string sample: JSON.stringify({ editors: [
    { id: "cursor", name: "Cursor", icons: ["co.anysphere.cursor", "cursor"],
      launch: ["uwsm-app", "--", "/usr/bin/cursor"], terminal: ["uwsm-app", "--", "/usr/bin/xdg-terminal-exec"],
      entries: [ { kind: "folder", uri: "file:///home/me/git/app", title: "app", where: "~/git/app", dir: "/home/me/git/app", remote: "" },
                 { kind: "workspace", uri: "file:///home/me/work/team.code-workspace", title: "team", where: "~/work/team.code-workspace", dir: "/home/me/work", remote: "" },
                 { kind: "file", uri: "file:///home/me/notes/todo.md", title: "todo.md", where: "~/notes/todo.md", dir: "/home/me/notes", remote: "" },
                 { kind: "folder", uri: "vscode-remote://ssh-remote%2Bbox/srv/api", title: "api", where: "/srv/api", dir: "", remote: "SSH: box" },
                 { kind: "folder", uri: "--help", title: "Flag" },
                 { kind: "folder", uri: "file:///x", title: "Relative dir", dir: "x" },
                 { kind: "shell", uri: "file:///x", title: "Unknown kind" },
                 { kind: "folder", uri: "file:///x", title: "" } ] },
    { id: "vscode", name: "Visual Studio Code", launch: ["/usr/bin/code"],
      entries: [ { kind: "folder", uri: "file:///home/me/git/app", title: "app", where: "~/git/app", dir: "/home/me/git/app" } ] },
    { id: "bad", name: "Bad", launch: [], entries: [ { kind: "folder", uri: "file:///a", title: "a" } ] },
    { id: "bad2", name: "Bad", launch: ["x", ""], entries: [ { kind: "folder", uri: "file:///a", title: "a" } ] }
  ] })

  function test_request() {
    compare(Projects.request({ query: "a", scope: "" }, "recent-projects").allowed, false)
    verify(Projects.request({ query: "ap", scope: "" }, "recent-projects").allowed)
    verify(!Projects.request({ query: "app", scope: "", settings: { root: false } }, "recent-projects").allowed)
    verify(!Projects.request({ query: "app", scope: "files" }, "recent-projects").allowed)
    var cmd = Projects.request({ query: "proj ", command: { rest: "" }, scope: "", settings: { root: false } }, "recent-projects")
    verify(cmd.allowed && cmd.explicit && !cmd.files)
    compare(cmd.text, "")
    verify(Projects.request({ query: "", scope: "recent-projects", settings: { files: true } }, "recent-projects").files)
  }

  function test_parse_filters_unsafe_entries() {
    var data = Projects.parse(sample)
    compare(data.editors.length, 2)
    compare(data.editors[0].entries.length, 4)
    compare(data.editors[1].terminal, [])
    compare(data.editors[1].icons, [])
    verify(Projects.parse("nope").error.length > 0)
    verify(Projects.parse('{"editors":{}}').error.length > 0)
  }

  function test_launch_argv() {
    var cursor = Projects.parse(sample).editors[0]
    compare(Projects.launch(cursor, cursor.entries[0]), ["uwsm-app", "--", "/usr/bin/cursor", "--folder-uri", "file:///home/me/git/app"])
    // A workspace opens as a workspace when handed over as a file.
    compare(Projects.launch(cursor, cursor.entries[1]), ["uwsm-app", "--", "/usr/bin/cursor", "--file-uri", "file:///home/me/work/team.code-workspace"])
    compare(Projects.launch(cursor, cursor.entries[3]), ["uwsm-app", "--", "/usr/bin/cursor", "--folder-uri", "vscode-remote://ssh-remote%2Bbox/srv/api"])
    compare(Projects.terminal(cursor, cursor.entries[1]), ["uwsm-app", "--", "/usr/bin/xdg-terminal-exec", "--dir=/home/me/work"])
    compare(Projects.terminal(cursor, cursor.entries[3]), null)
  }

  function test_rows() {
    var data = Projects.parse(sample)
    var icons = function(names) { return names.length ? "file:///icons/" + names[1] + ".png" : "" }
    var listed = Projects.rows(data, { explicit: true, text: "", files: false }, icons)
    compare(listed.map(function(r) { return r.title }), ["app", "team (Workspace)", "api", "app"])
    compare(listed[0].id, "cursor:file:///home/me/git/app")
    compare(listed[3].id, "vscode:file:///home/me/git/app")
    compare(listed[0].subtitle, "~/git/app · Cursor")
    compare(listed[2].subtitle, "SSH: box · /srv/api · Cursor")
    compare(listed[0].score, 1)
    compare(listed[0].iconSource, "file:///icons/cursor.png")
    compare(listed[3].iconSource, "")
    verify(listed[0].remember)
    compare(listed[0].verb, "Open in Cursor")
    compare(listed[0].altVerb, "Open terminal")
    compare(listed[0].altAction.argv[3], "--dir=/home/me/git/app")
    compare(listed[2].altAction, undefined)
    compare(listed[3].altAction, undefined)   // no terminal found
    verify(listed[0].keywords.indexOf("~/git/app") >= 0)
    // At the root the path is not a keyword: "git" must not match every project under ~/git.
    var typed = Projects.rows(data, { explicit: false, text: "app", files: false }, null)
    compare(typed[0].keywords, "")
    compare(typed[0].score, undefined)
    compare(typed[0].id, listed[0].id)
    var files = Projects.rows(data, { explicit: true, text: "", files: true }, null)
    compare(files.length, 5)
    compare(files[2].title, "todo.md")
    compare(files[2].action.argv.slice(3), ["--file-uri", "file:///home/me/notes/todo.md"])
  }

  function test_merge() {
    var good = { editors: [{ id: "a", entries: [{}] }], error: "" }
    var empty = { editors: [], error: "" }
    var failed = { editors: [], error: "Timed out" }
    compare(Projects.merge(good, failed), good)           // a failed rescan keeps the last list
    compare(Projects.merge(good, empty), empty)           // an empty success replaces it
    compare(Projects.merge(null, failed), failed)         // a first failure is shown
    compare(Projects.merge(empty, failed), failed)
  }

  function test_empty_and_errors() {
    compare(Projects.rows({ editors: [] }, { explicit: false, text: "ap" }), [])
    compare(Projects.rows({ editors: [] }, { explicit: true, text: "" })[0].title, "No recent projects found")
    compare(Projects.rows({ editors: [], error: "Broken" }, { explicit: true, text: "" })[0].title, "Broken")
    verify(Projects.rows({ editors: [] }, { explicit: true, text: "" })[0].disabled)
  }
}
