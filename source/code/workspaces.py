"""
---------------
IMPORTANT NOTES
---------------

This thing will be a kludge and there is no way around it.

Why?

1. Window types have to be found via fuzzy heuristics.
2. Identifying specific screens via AppKit is hard.

So, you know, I'm not worried about this code being:

1. Pretty.
2. Future proof.

It is what it is.


-----
To Do
-----

- where should "Workspaces" go in the menu?
  does it need a divider?
- add a common attribute search to the NSWindow.delegate()
  (aka self.w) for future use. something like vanillaWindowIdentifier.
- add a way to register a window opening function.
  this can be used when a desired window type isn't open.
"""

from copy import deepcopy
import pprint
import re
import AppKit
import vanilla
from vanilla import vanillaBase
import ezui
from mojo.extensions import (
    getExtensionDefault,
    setExtensionDefault
)
from mojo.tools import CallbackWrapper

DEBUG = True

extensionIdentifier = "com.typesupply.Workspaces"
defaultsKey = extensionIdentifier + ".workspaces"

# -------
# Strings
# -------

def workspaceToString(workspace):
    lines = []
    for window in sorted(workspace.keys(), key=str.casefold):
        data = workspace[window]
        x, y = data["position"]
        w, h = data["size"]
        lines.append(f"+ {window}")
        lines.append(f"position: ({x}, {y})")
        lines.append(f"size: ({w}, {h})")
        lines.append("")
    return "\n".join(lines).strip()

coordinateRE = re.compile(
    "\\("
    "(-{0,1}\\d+)"
    ",\\s*"
    "(-{0,1}\\d+)"
    "\\)"
)

def parseWorkspaceString(string):
    data = {}
    window = None
    for line in string.splitlines():
        line = line.strip()
        line = line.split("#")[0]
        line = line.strip()
        if not line:
            continue
        # window
        if line.startswith("+"):
            line = line[1:].strip()
            window = line
            data[window] = {}
            continue
        # position
        s = "position:"
        if line.startswith(s):
            line = line[len(s):].strip()
            m = coordinateRE.match(line)
            if m is not None:
                data[window]["position"] = (int(m.group(1)), int(m.group(2)))
            continue
        # size
        s = "size:"
        if line.startswith(s):
            line = line[len(s):].strip()
            m = coordinateRE.match(line)
            if m is not None:
                data[window]["size"] = (int(m.group(1)), int(m.group(2)))
            continue
    # sanitize
    for window, d in list(data.items()):
        if not window:
            del data[window]
        if "position" not in d:
            del data[window]
        elif "size" not in d:
            del data[window]
    return data

# -------
# Storage
# -------

def readWorkspacesFromDefaults():
    return getExtensionDefault(defaultsKey, {})

def writeWorkspacesToDefaults(workspaces):
    setExtensionDefault(defaultsKey, workspaces)

def getNewWorkspaceName():
    existing = list(readWorkspacesFromDefaults().keys())
    name = "New Workspace"
    if name not in existing:
        return name
    for i in range(1, 1000):
        name = f"New Workspace {i}"
        if name not in existing:
            return name
    return "Uh. You have too many unnamed workspaces."

# -----
# Tools
# -----

def getVanillaWindow(window):
    delegate = window.delegate()
    if delegate is None:
        return None
    if not isinstance(delegate, vanilla.Window):
        return None
    return delegate

def getVanillaWrapper(window):
    vanillaWindow = getVanillaWindow(window)
    if vanillaWindow is None:
        return None
    if not hasattr(vanillaWindow, "vanillaWrapper"):
        return None
    return vanillaWindow.vanillaWrapper()

def hasVanillaWrapperWithClassName(window, className):
    wrapper = getVanillaWrapper(window)
    if wrapper is None:
        return False
    if wrapper.__class__.__name__ == className:
        return True
    return False

def hasAutosaveName(window, name):
    return window.frameAutosaveName() == name

def hasTitle(window, title):
    t = window.title()
    if isinstance(title, re.Pattern):
        return bool(title.match(t))
    return title == t

def hasDocumentWithClassName(window, className):
    document = window.document()
    if document is None:
        return False
    return document.__class__.__name__ == className

# ------------
# Type Lookups
# ------------

windowTypeLookupRegistry = {}

def registerWindowTypeLookup(name, function):
    windowTypeLookupRegistry[name] = function

def shouldSkipWindow(window):
    if not window.title() and not window.frameAutosaveName():
        return True
    if hasAutosaveName(window, "NSColorPanel"):
        return True
    if hasAutosaveName(window, "NSNavPanelAutosaveName"):
        return True
    return False

# Output

def isOutput(window):
    return hasVanillaWrapperWithClassName(window, "Debugger")

registerWindowTypeLookup("Output", isOutput)

# Font Overview

def isFontOverview(window):
    return hasVanillaWrapperWithClassName(window, "DoodleFontWindow")

registerWindowTypeLookup("Font Overview", isFontOverview)

# Glyph Editor

def isGlyphEditor(window):
    return hasVanillaWrapperWithClassName(window, "DoodleGlyphWindow")

registerWindowTypeLookup("Glyph Editor", isGlyphEditor)

# Inspector

def isInspector(window):
    return hasAutosaveName(window, "DoodleInspectorWindow")

registerWindowTypeLookup("Inspector", isInspector)

# Space Center

def isSpaceCenter(window):
    return hasVanillaWrapperWithClassName(window, "DoodleSpacingWindow")

registerWindowTypeLookup("Space Center", isSpaceCenter)

def isFeatures(window):
    return hasDocumentWithClassName(window, "FeatureDocument")

registerWindowTypeLookup("Features", isFeatures)

# Script

def isScript(window):
    return hasDocumentWithClassName(window, "PyDocument")

registerWindowTypeLookup("Script", isScript)

# Preferences

def isPreferences(window):
    return hasAutosaveName(window, "DoodlePreferencesWindow")

registerWindowTypeLookup("Preferences", isPreferences)

# Batch

def isBatch(window):
    return hasTitle(window, "Batch")

registerWindowTypeLookup("Batch", isBatch)

# MetricsMachine

def isMetricsMachine(window):
    return hasVanillaWrapperWithClassName(window, "MMDocumentWindowController")

registerWindowTypeLookup("MetricsMachine", isMetricsMachine)

# Prepolator Next

def isPrepolatorNext(window):
    return hasTitle(window, "Prepolator Next")

registerWindowTypeLookup("Prepolator Next", isPrepolatorNext)

# RoboREPL

def isRoboREPL(window):
    return hasTitle(window, "RoboREPL")

registerWindowTypeLookup("RoboREPL", isRoboREPL)

# Unknown

def dumpUnknownWindowData(window):
    print("Unknown:")
    print("- title:", window.title())
    print("- frameAutosaveName:", window.frameAutosaveName())
    wrapper = getVanillaWrapper(window)
    if wrapper is not None:
        print("-", wrapper.__class__.__name__)

# ----------------
# Wokspace Actions
# ----------------

def getWindowLocation(window):
    screen = window.screen()
    screenFrame = screen.frame()
    windowFrame = window.frame()
    x, y, w, h = vanillaBase._flipFrame(screenFrame, windowFrame)
    x = int(x)
    y = int(y)
    w = int(w)
    h = int(h)
    data = dict(
        position=(x, y),
        size=(w, h)
    )
    return data

def getCurrentWorkspace():
    app = AppKit.NSApp()
    workspace = {}
    unknown = []
    for window in app.windows():
        if shouldSkipWindow(window):
            continue
        found = False
        for windowTypeName, lookup in windowTypeLookupRegistry.items():
            if lookup(window):
                found = True
                location = getWindowLocation(window)
                workspace[windowTypeName] = location
                break
        if not found:
            unknown.append(window)
            if DEBUG:
                dumpUnknownWindowData(window)
    return workspace

def applyWorkspace(workspace):
    app = AppKit.NSApp()
    matches = []
    for window in app.windows():
        if shouldSkipWindow(window):
            continue
        for windowTypeName, lookup in windowTypeLookupRegistry.items():
            if lookup(window):
                if windowTypeName in workspace:
                    matches.append((window, workspace[windowTypeName]))
                break
    screenFrame = AppKit.NSScreen.mainScreen().frame()
    for window, data in matches:
        position = data["position"]
        size = data["size"]
        posSize = (position, size)
        windowFrame = vanillaBase._calcFrame(screenFrame, posSize, absolutePositioning=True)
        window.setFrame_display_animate_(windowFrame, True, False)

# ----
# Menu
# ----

"""
> Workspace
  Name 1
  Name 2
  Name 3
  ----
  Save Workspace...
  Edit Workspaces...
  ----
  Help
"""

class WorkspacesMenuController:

    def __init__(self):
        self.editWindow = None
        title = "Workspaces"
        mainMenu = AppKit.NSApp().mainMenu()
        windowMenu = mainMenu.itemWithTitle_("Window")
        windowMenu = windowMenu.submenu()
        self.workspacesItem = windowMenu.itemWithTitle_(title)
        if not self.workspacesItem:
            self.workspacesItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title,
                None,
                ""
            )
            submenu = AppKit.NSMenu.alloc().initWithTitle_(title)
            self.workspacesItem.setSubmenu_(submenu)
            windowMenu.insertItem_atIndex_(self.workspacesItem, 0)
        self.buildMenuItems()

    def buildMenuItems(self):
        self.workspaces = readWorkspacesFromDefaults()
        # set up the targets
        self.workspaceItemTarget = CallbackWrapper(self.workspaceItemCallback)
        self.saveWorkspaceItemTarget = CallbackWrapper(self.saveWorkspaceItemCallback)
        self.editWorkspacesItemTarget = CallbackWrapper(self.editWorkspacesItemCallback)
        self.helpItemTarget = CallbackWrapper(self.helpItemCallback)
        # build the item descriptions
        items = []
        for name in sorted(self.workspaces.keys(), key=str.casefold):
            items.append(dict(
                title=name,
                target=self.workspaceItemTarget
            ))
        items += [
            "---",
            dict(
                title="Save Workspace...",
                target=self.saveWorkspaceItemTarget
            ),
            dict(
                title="Edit Workspaces...",
                target=self.editWorkspacesItemTarget
            ),
            "---",
            dict(
                title="Help",
                target=self.helpItemTarget
            )
        ]
        # prep the submenu
        submenu = self.workspacesItem.submenu()
        submenu.removeAllItems()
        # populate the submenu
        for description in items:
            if description == "---":
                item = AppKit.NSMenuItem.separatorItem()
            else:
                item = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                    description["title"],
                    "action:",
                    ""
                )
                item.setTarget_(description["target"])
            submenu.addItem_(item)

    def workspaceItemCallback(self, sender):
        name = sender.title()
        workspaces = readWorkspacesFromDefaults()
        if name in workspaces:
            workspace = workspaces[name]
            applyWorkspace(workspace)

    def saveWorkspaceItemCallback(self, sender):
        name = getNewWorkspaceName()
        workspace = getCurrentWorkspace()
        workspaces = readWorkspacesFromDefaults()
        workspaces[name] = workspace
        writeWorkspacesToDefaults(workspaces)
        self.buildMenuItems()
        workspaces = readWorkspacesFromDefaults()
        self.openEditWorkspacesWindow(readWorkspacesFromDefaults(), name)

    def editWorkspacesItemCallback(self, sender):
        self.openEditWorkspacesWindow(self.workspaces)

    def helpItemCallback(self, sender):
        print("helpItemCallback")

    def openEditWorkspacesWindow(self, workspaces, selected=None):
        if self.editWindow is not None:
            self.editWindow.set(workspaces, selected)
        else:
            self.editWindow = EditWorkspacesWindowController(workspaces, selected)

# ------
# Window
# ------

class EditWorkspacesWindowController(ezui.WindowController):

    def build(self,
            workspaces,
            selected=None
        ):
        content = """
        = HorizontalStack
        |-----------------------------| @table
        |                             |
        |-----------------------------|
        > (+-)    @tableAddRemoveButton
        > (Apply) @tableApplyButton

        [[_ _]] @editor
        """
        descriptionData = dict(
            table=dict(
                width=150,
                allowsMultipleSelection=False,
                allowsEmptySelection=False,
                showColumnTitles=False,
                columnDescriptions=[dict(identifier="name")]
            ),
            editor=dict(
                width=300
            )
        )
        self.w = ezui.EZWindow(
            title="Workspaces",
            size=("auto", 300),
            content=content,
            descriptionData=descriptionData,
            controller=self
        )
        self.set(workspaces, selected)

    def started(self):
        self.w.open()

    def terminate(self):
        GlobalWorkspacesMenuController.editWindow = None

    def set(self, workspaces, selected):
        items = []
        for name in sorted(workspaces.keys(), key=str.casefold):
            workspace = workspaces[name]
            item = dict(
                name=name,
                workspace=workspace
            )
            items.append(item)
        table = self.w.getItem("table")
        table.set(items)
        if selected is not None:
            for index, item in enumerate(items):
                if item["name"] == selected:
                    table.setSelectedIndexes([index])
                    table.scrollToIndex(index)
                    break

    def writeWorkspaces(self, items=None):
        if items is None:
            table = self.w.getItem("table")
            items = table.get()
        workspaces = {}
        for item in items:
            name = item["name"]
            workspace = item["workspace"]
            workspaces[name] = workspace
        writeWorkspacesToDefaults(workspaces)
        GlobalWorkspacesMenuController.buildMenuItems()

    def tableSelectionCallback(self, sender):
        items = sender.getSelectedItems()
        if not items:
            text = ""
        else:
            item = items[0]
            workspace = item["workspace"]
            text = workspaceToString(workspace)
        editor = self.w.getItem("editor")
        editor.set(text)

    def tableAddRemoveButtonAddCallback(self, sender):
        table = self.w.getItem("table")
        items = list(table.get())
        name = getNewWorkspaceName()
        item = dict(
            name=name,
            workspace={}
        )
        items.append(item)
        self.writeWorkspaces(items)
        self.set(readWorkspacesFromDefaults(), name)

    def tableAddRemoveButtonRemoveCallback(self, sender):
        table = self.w.getItem("table")
        indexes = table.getSelectedIndexes()
        if not indexes:
            return
        items = list(table.get())
        for i in reversed(indexes):
            del items[i]
        self.writeWorkspaces(items)
        self.set(readWorkspacesFromDefaults(), None)

    def tableApplyButtonCallback(self, sender):
        table = self.w.getItem("table")
        items = table.getSelectedItems()
        if not items:
            return
        item = items[0]
        workspace = item["workspace"]
        applyWorkspace(workspace)

    def editorCallback(self, sender):
        table = self.w.getItem("table")
        items = table.getSelectedItems()
        if not items:
            return
        item = items[0]
        text = sender.get()
        item["workspace"] = parseWorkspaceString(text)
        self.writeWorkspaces()

# --
# Go
# --

GlobalWorkspacesMenuController = WorkspacesMenuController()