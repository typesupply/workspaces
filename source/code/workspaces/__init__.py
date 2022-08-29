import os
from copy import deepcopy
import pprint
import re
import AppKit
import vanilla
from vanilla import vanillaBase
from vanilla import dialogs
import ezui
from mojo.extensions import (
    getExtensionDefault,
    setExtensionDefault
)
from mojo.tools import CallbackWrapper
from mojo import events
from mojo import UI
from mojo.roboFont import OpenFont

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
"""

DEBUG = ".robofontext" not in __file__.lower()

extensionIdentifier = "com.typesupply.Workspaces"
workspacesDefaultsKey = extensionIdentifier + ".workspaces"

# -----------------------
# Backwards Compatibility
# -----------------------

"""
Storage Format:

{
    workspace name : [
        (window identifier, {
            position : (x, y),
            size : (w, h)
        )
    ]
}
"""

def convertDefaults0():
    """
    Alpha 0.1 Storage Format:
        {
            workspace name : {
                window identifier : {
                    position : (x, y),
                    size : (w, h)
                }
            }
        }
    """
    stored = getExtensionDefault(workspacesDefaultsKey, {})
    if stored is not None:
        neededConversion = False
        converted = {}
        for workspaceName, workspace in stored.items():
            if isinstance(workspace, (dict, AppKit.NSDictionary)):
                neededConversion = True
                l = []
                for windowIdentifier in sorted(workspace.keys()):
                    windowData = workspace[windowIdentifier]
                    l.append((windowIdentifier, windowData))
                workspace = l
            converted[workspaceName] = workspace
        if neededConversion:
            setExtensionDefault(workspacesDefaultsKey, converted)

convertDefaults0()

# -------
# Strings
# -------

def workspaceToString(workspace):
    lines = []
    for window, data in workspace:
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
    workspace = []
    currentData = None
    for line in string.splitlines():
        line = line.strip()
        line = line.split("#")[0]
        line = line.strip()
        if not line:
            continue
        # window
        if line.startswith("+"):
            line = line[1:].strip()
            windowIdentifier = line
            currentData = {}
            workspace.append((windowIdentifier, currentData))
            continue
        # position
        s = "position:"
        if line.startswith(s):
            line = line[len(s):].strip()
            m = coordinateRE.match(line)
            if m is not None:
                currentData["position"] = (int(m.group(1)), int(m.group(2)))
            continue
        # size
        s = "size:"
        if line.startswith(s):
            line = line[len(s):].strip()
            m = coordinateRE.match(line)
            if m is not None:
                currentData["size"] = (int(m.group(1)), int(m.group(2)))
            continue
    # sanitize
    sanitized = []
    for windowIdentifier, windowData in workspace:
        if not windowIdentifier:
            continue
        if "position" not in windowData:
            continue
        elif "size" not in windowData:
            continue
        sanitized.append((windowIdentifier, windowData))
    return sanitized

# -------
# Storage
# -------

def readWorkspacesFromDefaults():
    return getExtensionDefault(workspacesDefaultsKey, {})

def writeWorkspacesToDefaults(workspaces):
    setExtensionDefault(workspacesDefaultsKey, workspaces)

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

def getWorkspaceWindowIdentifier(window):
    delegate = window.delegate()
    if delegate is None:
        return None
    if hasattr(delegate, "workspaceWindowIdentifier"):
        return delegate.workspaceWindowIdentifier
    return None

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

# Single Window

def isSingleWindow(window):
    return hasVanillaWrapperWithClassName(window, "DoodleSingleModeWindow")

registerWindowTypeLookup("Single Window", isSingleWindow)

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

# -------
# Openers
# -------

windowOpenerRegistry = {}

def registerWindowOpener(windowIdentifier, constructor):
    """
    The constructor must not require any args or kwargs.
    The constructor must return the vanilla Window (or
    subclass) object OR have the vanilla Window object
    located at the `w` attribute of the returned object.
    """
    windowOpenerRegistry[windowIdentifier] = constructor

def openWindowWithIdentifier(windowIdentifier):
    events.postEvent(
        "Workspaces.RegisterWindowOpeners",
        register=registerWindowOpener
    )
    if windowIdentifier not in windowOpenerRegistry:
        return None
    window = windowOpenerRegistry[windowIdentifier]()
    if hasattr(window, "w"):
        window = window.w
    return window.getNSWindow()

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
    workspace = []
    unknown = []
    for window in app.windows():
        # have the standard identifier?
        windowIdentifier = getWorkspaceWindowIdentifier(window)
        if windowIdentifier:
            location = getWindowLocation(window)
            workspace.append((windowIdentifier, location))
            continue
        # skip it?
        if shouldSkipWindow(window):
            continue
        # work through the heuristics.
        found = False
        for windowTypeName, lookup in windowTypeLookupRegistry.items():
            if lookup(window):
                found = True
                location = getWindowLocation(window)
                workspace.append((windowTypeName, location))
                break
        if not found:
            unknown.append(window)
            if DEBUG:
                dumpUnknownWindowData(window)
    return workspace

def applyWorkspace(workspace):
    app = AppKit.NSApp()
    searching = []
    for windowIdentifier, windowData in workspace:
        searching.append((windowIdentifier, dict(windowData)))
    matched = []
    for window in app.windows():
        # have the standard identifier?
        windowIdentifier = getWorkspaceWindowIdentifier(window)
        if windowIdentifier:
            found = False
            for i, (wantedIdentifier, windowData) in enumerate(searching):
                if wantedIdentifier == windowIdentifier:
                    if not window.isVisible():
                        window.makeKeyAndOrderFront_(None)
                    matched.append((window, windowData))
                    del searching[i]
                    found = True
                    break
            if found:
                continue
        # skip it?
        if shouldSkipWindow(window):
            continue
        # work through the heuristics.
        for windowTypeName, lookup in windowTypeLookupRegistry.items():
            if lookup(window):
                found = False
                for i, (wantedIdentifier, windowData) in enumerate(searching):
                    if wantedIdentifier == windowTypeName:
                        matched.append((window, windowData))
                        del searching[i]
                        found = True
                        break
                if found:
                    break
    # open necessary windows
    for windowIdentifier, windowData in searching:
        window = openWindowWithIdentifier(windowIdentifier)
        if hasattr(window, "w"):
            window = window.w
        if window is not None:
            matched.append((window, windowData))
    # apply workspace settings
    screenFrame = AppKit.NSScreen.mainScreen().frame()
    for window, data in matched:
        position = data["position"]
        size = data["size"]
        posSize = (position, size)
        windowFrame = vanillaBase._calcFrame(screenFrame, posSize, absolutePositioning=True)
        window.setFrame_display_animate_(windowFrame, True, False)

def applyWorkspaceWithName(name):
    workspaces = readWorkspacesFromDefaults()
    if name not in workspaces:
        print("No workspace with name:", name)
        return
    workspace = workspaces[name]
    applyWorkspace(workspace)

# ----
# Menu
# ----

class WorkspacesMenuController:

    def __init__(self):
        self.editWindow = None
        mainMenu = AppKit.NSApp().mainMenu()
        # Window > Workspaces
        title = "Workspaces"
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
            windowMenu.insertItem_atIndex_(AppKit.NSMenuItem.separatorItem(), 0)
            windowMenu.insertItem_atIndex_(self.workspacesItem, 0)
            windowMenu.insertItem_atIndex_(AppKit.NSMenuItem.separatorItem(), 0)
        # File > Open in Workspace…
        title = "Open in Workspace…"
        fileMenu = mainMenu.itemWithTitle_("File")
        fileMenu = fileMenu.submenu()
        self.openInWorkspaceItem = fileMenu.itemWithTitle_(title)
        if not self.openInWorkspaceItem:
            self.openInWorkspaceItemTarget = CallbackWrapper(self.openInWorkspaceItemCallback)
            self.openInWorkspaceItem = AppKit.NSMenuItem.alloc().initWithTitle_action_keyEquivalent_(
                title,
                "action:",
                "o"
            )
            self.openInWorkspaceItem.setKeyEquivalentModifierMask_(
                AppKit.NSEventModifierFlagCommand |
                AppKit.NSEventModifierFlagShift |
                AppKit.NSEventModifierFlagControl
            )
            self.openInWorkspaceItem.setTarget_(self.openInWorkspaceItemTarget)
            index = fileMenu.indexOfItemWithTitle_("Open…") + 1
            fileMenu.insertItem_atIndex_(self.openInWorkspaceItem, index)
        # build the workspace items
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

    def openInWorkspaceItemCallback(self, sender):
        workspaces = list(sorted(self.workspaces.keys(), key=str.casefold))
        self.openInWorkspaceAccessoryView = vanilla.Group(
            (0, 0, 200, 50)
        )
        self.openInWorkspaceAccessoryView.workspacesPopUpButton = vanilla.PopUpButton(
            (10, 10, -10, 22),
            workspaces
        )
        paths = dialogs.getFile(
            allowsMultipleSelection=True,
            fileTypes=["ufo", "ufoz", "otf", "ttf"],
            accessoryView=self.openInWorkspaceAccessoryView
        )
        if paths:
            for path in paths:
                OpenFont(path, showInterface=True)
            workspace = self.openInWorkspaceAccessoryView.workspacesPopUpButton.get()
            workspace = workspaces[workspace]
            applyWorkspaceWithName(workspace)
            del self.openInWorkspaceAccessoryView

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
        path = os.path.dirname(__file__)
        path = os.path.dirname(path)
        path = os.path.dirname(path)
        path = os.path.join(path, "html", "index.html")
        UI.HelpWindow(
            path
        )

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
                columnDescriptions=[dict(identifier="name", editable=True)]
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

    def tableEditCallback(self, sender):
        self.writeWorkspaces()

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
