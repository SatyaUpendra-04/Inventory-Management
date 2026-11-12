import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Add or edit a programme task: intervals (whichever comes first), tolerance, life limit.
Sheet {
    id: sheet

    property bool isNew: true
    property var task: ({})

    width: Math.min(640, parent ? parent.width - 64 : 640)
    title: isNew ? qsTr("Add maintenance task") : qsTr("Edit %1").arg(task.name || "")
    subtitle: qsTr("Give one or more intervals; the task is due at whichever comes first.")

    function openNew() {
        isNew = true
        task = ({})
        Maintenance.clearError()
        for (var f of [name, hours, cycles, landings, days, tolHours, tolDays, instructions]) f.text = ""
        lifeLimit.checked = false; active.checked = true
        itemType.currentIndex = 0
        open()
    }
    function openEdit(t) {
        isNew = false
        task = t
        Maintenance.clearError()
        name.text = t.name; hours.text = t.everyHours; cycles.text = t.everyCycles
        landings.text = t.everyLandings; days.text = t.everyDays
        tolHours.text = t.toleranceHours; tolDays.text = t.toleranceDays
        instructions.text = t.instructions; lifeLimit.checked = t.lifeLimit; active.checked = t.active
        open()
    }
    function values() {
        return {
            itemTypeId: itemType.currentValue || "", name: name.text, everyHours: hours.text,
            everyCycles: cycles.text, everyLandings: landings.text, everyDays: lifeLimit.checked ? "" : days.text,
            toleranceHours: lifeLimit.checked ? "" : tolHours.text, toleranceDays: lifeLimit.checked ? "" : tolDays.text,
            lifeLimit: lifeLimit.checked, instructions: instructions.text, active: active.checked
        }
    }

    Connections {
        target: Maintenance
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md
        Column {
            visible: sheet.isNew
            width: parent.width
            spacing: 6
            Txt { text: qsTr("For"); variant: "caption"; font.weight: Theme.type.medium }
            AppSelect { id: itemType; width: parent.width; model: sheet.opened ? Maintenance.itemTypes() : []; textRole: "label"; valueRole: "value" }
        }
        AppTextField { id: name; width: parent.width; label: qsTr("Task"); placeholder: qsTr("e.g. 50 h inspection") }
        AppCheckBox { id: lifeLimit; text: qsTr("Life limit: the part is replaced at the limit (counted in hours, cycles or landings)") }
        Row {
            spacing: Theme.space.md
            AppTextField { id: hours; width: 130; label: qsTr("Hours") }
            AppTextField { id: cycles; width: 130; label: qsTr("Cycles") }
            AppTextField { id: landings; width: 130; label: qsTr("Landings") }
            AppTextField { id: days; visible: !lifeLimit.checked; width: 130; label: qsTr("Days") }
        }
        Row {
            visible: !lifeLimit.checked
            spacing: Theme.space.md
            AppTextField { id: tolHours; width: 170; label: qsTr("Tolerance, hours") }
            AppTextField { id: tolDays; width: 170; label: qsTr("Tolerance, days") }
        }
        AppTextField { id: instructions; width: parent.width; label: qsTr("Instructions (optional)") }
        AppCheckBox { id: active; visible: !sheet.isNew; text: qsTr("Active (part of the programme)") }
        ErrorBanner { text: Maintenance.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            text: sheet.isNew ? qsTr("Add task") : qsTr("Save changes")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: sheet.isNew ? Maintenance.addTask(sheet.values())
                                   : Maintenance.updateTask(sheet.task.taskId, sheet.task.version, sheet.values())
        }
    ]
}
