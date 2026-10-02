# Repair the received-plate integration

Larkspur is a fictional amateur observatory. Its Plate Desk retains the earlier
field registrations after an observer replaces the finder/plate pairs in the
provider inbox. The labeled overlay, identification ledger and target offsets
no longer agree with the received photographic plates.

Reconcile the received-plate integration for both observation editions. Inspect
the original Finder and Plate sheets through the prepared app; the Guide
explains the registration and measurement contract. Preserve the complete
viewer, live draft editing, Undo/Cancel/Save, notes, reload, independent editions
and Reset. A repair may use a different internal representation.

The app is a mobile web page at 400×800, not a native phone app. Both conditions
have the full ordinary client source and build inputs. The external provider
inbox is imported into the isolated running app, not included in the coding
workspace. Outside that prepared runtime a new app has an empty inbox. Ordinary
reload keeps imported inputs and saved data. A source rebuild explicitly resets
the isolated scene. No network dependencies are required; build with
`sh build.sh`. All ordinary files except the build wrapper may be edited.
