# Workspaces

Save and restore window positions.

## Applying Workspaces

To apply a saved workspace, select the desired workspace
from the Windows > Workspaces menu.

If a window in the workspace is not open and Workspaces
knows how to open the window, the window will be opened.

## Saving Workspaces

To save the current workspace, use the Windows > Workspaces >
Save Workspace... menu item. This will store the current
workspace and open it within the workspace editor.

## Editing Workspaces

To edit the available workspaces or change the settings
for a particular workspace, use the the Windows > Workspaces >
Edit Workspaces... menu item. The available workspaces will
be listed and the text editor allows editing. This is the
syntax:

```
+ Window Identifier
position: (x, y)
size: (x, y)
```

## Developer Notes

Scripts and extensions can improve the behavior of their
windows within Workspaces by providing some small bits
of data to help with the window identification process.

### Setting a Window Identifier

Windows are identified through a set of heuristics. The most
reliable way to make sure that a window is correctly identified
is to have a `workspaceWindowIdentifier` attribute set on the
vanilla `Window` (or subclass) object that defined the window.
Scripts and extensions can do this by including the following
when windows are defined:


```python
self.w.workspaceWindowIdentifier = "My Extension Window"
```

### Registering a Window Opener

To register a window opener, observe the event shown below and,
when it is posted, register a window constructor as shown.
The window contructor must return an object that is either
a vanilla `Window` (or subclass) or an object with a vanilla
`Window` object located at the `w` attribute.


```python
from mojo import events

class MyWindowController:

    def __init__(self):
        self.w = vanilla.Window((200, 200))
        self.w.workspaceWindowIdentifier = "My Window"
        self.w.open()

class MyWorkspacesObserver:

    def __init__(self):
        events.addObserver(self, "register", "Workspaces.RegisterWindowOpeners")

    def register(self, info):
        info["register"]("My Window", MyWindowController)

PreviewWorkspacesObserver()
```

### Applying A Workspace With Code

Workspaces can be applied with code. Like this:

```python
import workspaces
workspaces.applyWorkspaceWithName("My Workspace")
```