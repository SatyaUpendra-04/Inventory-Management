import QtQuick
import QtQuick.Controls.Basic
import "../components"

// A work order: open one, move it along, record the work, and sign off the return to service.
Sheet {
    id: sheet

    property bool isNew: true
    property string assetId: ""
    property string assetTag: ""
    property var taskIds: []
    property var defectIds: []
    property string completing: ""   // "complete" while entering the work done
    readonly property var o: Maintenance.order
    readonly property bool loaded: !isNew && o.workOrderId !== undefined

    width: Math.min(700, parent ? parent.width - 64 : 700)
    title: isNew ? qsTr("Open work order") : (loaded ? o.number + "  ·  " + o.title : qsTr("Loading…"))
    subtitle: isNew ? qsTr("For %1. Opening it takes the item into maintenance.").arg(assetTag)
                    : (loaded ? o.tag + "  ·  " + o.type : "")

    function openNew(asset, tag, suggestedTitle, tasks, defects) {
        isNew = true
        completing = ""
        assetId = asset; assetTag = tag
        taskIds = tasks || []; defectIds = defects || []
        titleField.text = suggestedTitle || ""
        Maintenance.clearError()
        open()
    }
    function show(workOrderId) {
        isNew = false
        completing = ""
        Maintenance.clearError()
        Maintenance.openOrder(workOrderId)
        open()
    }
    onClosed: if (!isNew) Maintenance.closeOrder()

    Connections {
        target: Maintenance
        function onSaved() { if (sheet.opened && sheet.isNew) sheet.close(); sheet.completing = "" }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md

        AppTextField { id: titleField; visible: sheet.isNew; width: parent.width; label: qsTr("Title"); placeholder: qsTr("e.g. 50 h inspection") }

        Column {
            visible: sheet.loaded
            width: parent.width
            spacing: Theme.space.sm
            Row {
                spacing: Theme.space.xs
                StatusPill { kind: sheet.o.stateKind || "neutral"; text: sheet.o.stateLabel || "" }
                Txt { anchors.verticalCenter: parent.verticalCenter; muted: true
                      text: qsTr("Opened %1 by %2").arg(sheet.o.opened || "").arg(sheet.o.openedBy || "") }
            }
            Txt { visible: (sheet.o.tasks || []).length > 0; text: qsTr("Scheduled tasks"); variant: "bodyStrong" }
            Repeater {
                model: sheet.o.tasks || []
                delegate: Txt { required property var modelData; text: "•  " + modelData.name + "  ·  " + modelData.intervals }
            }
            Txt { visible: (sheet.o.defects || []).length > 0; text: qsTr("Defects"); variant: "bodyStrong" }
            Repeater {
                model: sheet.o.defects || []
                delegate: Row {
                    required property var modelData
                    spacing: Theme.space.sm
                    Txt { text: "•  " + modelData.number + "  " + modelData.description }
                    StatusPill { kind: modelData.stateKind; text: modelData.stateLabel }
                }
            }
            Txt { visible: !!sheet.o.workDone; width: parent.width; wrapMode: Text.WordWrap
                  text: qsTr("Work done: %1").arg(sheet.o.workDone || "") + (sheet.o.completedBy ? qsTr(" (%1)").arg(sheet.o.completedBy) : "") }
            Txt { visible: !!sheet.o.parts; width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Parts: %1").arg(sheet.o.parts || "") }
            Txt { visible: !!sheet.o.note; width: parent.width; wrapMode: Text.WordWrap; muted: true; text: sheet.o.note || "" }
            Txt { visible: !!sheet.o.certifiedBy; text: qsTr("Signed off by %1").arg(sheet.o.certifiedBy || ""); color: Theme.colors.successText }
            Rectangle {
                visible: (sheet.o.blockers || []).length > 0
                width: parent.width
                height: blockerCol.implicitHeight + Theme.space.md * 2
                radius: Theme.radius.md
                color: Theme.colors.dangerBg
                border.width: 1
                border.color: Theme.colors.dangerBorder
                Column {
                    id: blockerCol
                    x: Theme.space.md; y: Theme.space.md
                    width: parent.width - Theme.space.md * 2
                    spacing: 4
                    Txt { text: qsTr("It cannot return to service yet"); variant: "bodyStrong"; color: Theme.colors.dangerText }
                    Repeater {
                        model: sheet.o.blockers || []
                        delegate: Txt { required property string modelData; width: blockerCol.width; wrapMode: Text.WordWrap; text: "•  " + modelData; color: Theme.colors.dangerText }
                    }
                }
            }
        }

        Column {
            visible: sheet.completing === "complete"
            width: parent.width
            spacing: Theme.space.sm
            AppTextField { id: workDone; width: parent.width; label: qsTr("Work done (required)") }
            AppTextField { id: parts; width: parent.width; label: qsTr("Parts used (optional)") }
        }
        AppTextField { id: moveNote; visible: sheet.completing === "move"; width: parent.width; label: qsTr("Note") }
        ErrorBanner { text: Maintenance.error }
    }

    property string pendingMove: ""

    actions: [
        AppButton { text: sheet.completing ? qsTr("Back") : (sheet.isNew ? qsTr("Cancel") : qsTr("Close"))
                    onClicked: sheet.completing ? sheet.completing = "" : sheet.close() },
        AppButton {
            visible: sheet.isNew
            variant: "primary"
            text: qsTr("Open work order")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Maintenance.openWorkOrder(sheet.assetId, titleField.text, sheet.taskIds, sheet.defectIds)
        },
        Repeater {
            model: sheet.loaded && !sheet.completing ? sheet.o.moves : []
            delegate: AppButton {
                required property var modelData
                text: modelData.label
                variant: modelData.value === "cancelled" ? "ghost" : "secondary"
                onClicked: {
                    if (modelData.value === "cancelled" || sheet.o.state === "completed") {
                        sheet.pendingMove = modelData.value; sheet.completing = "move"; moveNote.text = ""
                    } else Maintenance.moveOrder(sheet.o.workOrderId, sheet.o.version, modelData.value, "")
                }
            }
        },
        AppButton {
            visible: sheet.loaded && !!sheet.o.canComplete && !sheet.completing
            variant: "primary"
            text: qsTr("Record work done…")
            onClicked: { sheet.completing = "complete"; workDone.text = ""; parts.text = "" }
        },
        AppButton {
            visible: sheet.completing === "complete"
            variant: "primary"
            text: qsTr("Complete")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Maintenance.completeOrder(sheet.o.workOrderId, sheet.o.version, workDone.text, parts.text)
        },
        AppButton {
            visible: sheet.completing === "move"
            variant: sheet.pendingMove === "cancelled" ? "danger" : "primary"
            text: sheet.pendingMove === "cancelled" ? qsTr("Cancel work order") : qsTr("Reopen")
            onClicked: Maintenance.moveOrder(sheet.o.workOrderId, sheet.o.version, sheet.pendingMove, moveNote.text)
        },
        AppButton {
            visible: sheet.loaded && !!sheet.o.canCertify && !sheet.completing
            variant: "primary"
            iconName: "check"
            text: qsTr("Sign off: return to service")
            enabled: !Tasks.busy && (sheet.o.blockers || []).length === 0
            onClicked: Maintenance.certify(sheet.o.workOrderId, sheet.o.version)
        }
    ]
}
