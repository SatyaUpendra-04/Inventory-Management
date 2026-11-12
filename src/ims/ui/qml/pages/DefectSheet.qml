import QtQuick
import QtQuick.Controls.Basic
import "../components"

// One defect: assess it (ground, defer with a limitation, or not a defect) or fix it.
Sheet {
    id: sheet

    property var d: ({})
    property string decision: ""   // grounded | deferred | cancelled while deciding

    signal workOrderRequested(var defect)

    width: Math.min(620, parent ? parent.width - 64 : 620)
    title: d.number ? d.number + "  ·  " + d.tag : qsTr("Defect")
    subtitle: d.type || ""

    function show(defect) {
        d = defect
        decision = ""
        Maintenance.clearError()
        open()
    }

    Connections {
        target: Maintenance
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md
        Row {
            spacing: Theme.space.xs
            StatusPill { kind: sheet.d.stateKind || "neutral"; text: sheet.d.stateLabel || "" }
            Txt { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Found %1").arg(sheet.d.reported || ""); muted: true }
        }
        Txt { width: parent.width; wrapMode: Text.WordWrap; text: sheet.d.description || "" }
        Txt { visible: !!sheet.d.limitation; width: parent.width; wrapMode: Text.WordWrap
              text: qsTr("Limitation: %1 until %2").arg(sheet.d.limitation || "").arg(sheet.d.deferredUntil || "") }
        Txt { visible: !!sheet.d.note; width: parent.width; wrapMode: Text.WordWrap; muted: true; text: sheet.d.note || "" }

        Column {
            visible: sheet.decision === "deferred"
            width: parent.width
            spacing: Theme.space.sm
            AppTextField { id: limitation; width: parent.width; label: qsTr("Limitation the crew must respect"); placeholder: qsTr("e.g. Max wind 8 m/s; no flights over people") }
            AppDatePicker { id: until; width: 220; label: qsTr("Fix by") }
        }
        AppTextField {
            id: note
            visible: sheet.decision !== ""
            width: parent.width
            label: sheet.decision === "cancelled" ? qsTr("Why it is not a defect (required)") : qsTr("Note (optional)")
        }
        ErrorBanner { text: Maintenance.error }
    }

    actions: [
        AppButton { text: sheet.decision ? qsTr("Back") : qsTr("Close"); onClicked: sheet.decision ? sheet.decision = "" : sheet.close() },
        AppButton { visible: !!sheet.d.canAssess && !sheet.decision; variant: "ghost"; text: qsTr("Not a defect…")
                    onClicked: { sheet.decision = "cancelled"; note.text = "" } },
        AppButton { visible: !!sheet.d.canAssess && !sheet.decision; text: qsTr("Defer…")
                    onClicked: { sheet.decision = "deferred"; note.text = ""; limitation.text = ""
                                 var day = new Date(); day.setDate(day.getDate() + 14); until.hasDate = true; until.selectedDate = day } },
        AppButton { visible: !!sheet.d.canAssess && !sheet.decision; variant: "danger"; text: qsTr("Ground it")
                    onClicked: { sheet.decision = "grounded"; note.text = "" } },
        AppButton { visible: Maintenance.canManage && !!sheet.d.open && !sheet.d.onWorkOrder && sheet.d.state !== "reported" && !sheet.decision
                    variant: "primary"; text: qsTr("Open work order…")
                    onClicked: { sheet.workOrderRequested(sheet.d); sheet.close() } },
        AppButton {
            visible: sheet.decision !== ""
            variant: sheet.decision === "grounded" ? "danger" : "primary"
            text: sheet.decision === "grounded" ? qsTr("Ground it") : sheet.decision === "deferred" ? qsTr("Defer") : qsTr("Not a defect")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Maintenance.assessDefect(sheet.d.defectId, sheet.d.version, sheet.decision, limitation.text,
                                                until.hasDate ? Qt.formatDate(until.selectedDate, "yyyy-MM-dd") : "", note.text)
        }
    ]
}
