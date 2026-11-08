import QtQuick
import "../components"

// Log one flight. Hours, landings and cycles go onto the drone and every part fitted to
// it; each battery used gets a cycle; the PPK base gets the flight time.
Sheet {
    id: sheet

    property var deployments: []
    readonly property var dep: deployments.length ? deployments[Math.max(0, deployment.currentIndex)] : ({})

    width: Math.min(680, parent ? parent.width - 64 : 680)
    title: qsTr("Log flight")
    subtitle: qsTr("Only equipment and crew from the chosen deployment can be logged.")

    function start(list) {
        deployments = list || []
        Projects.clearError()
        deployment.currentIndex = 0
        minutes.text = ""; landings.text = "1"; cycles.text = "1"; notes.text = ""
        batteries.selected = []; media.selected = []
        day.hasDate = true; day.selectedDate = new Date()
        open()
    }

    Connections {
        target: Projects
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    component Label: Txt { variant: "caption"; font.weight: Theme.type.medium }

    Column {
        width: parent.width
        spacing: Theme.space.md

        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: parent.width - day.width - parent.spacing
                spacing: 6
                Label { text: qsTr("Deployment") }
                AppSelect {
                    id: deployment
                    width: parent.width
                    model: sheet.deployments
                    textRole: "label"
                    valueRole: "deploymentId"
                    onActivated: { batteries.selected = []; media.selected = [] }
                }
            }
            AppDatePicker { id: day; width: 200; label: qsTr("Flown on") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Drone") }
                AppSelect { id: drone; width: parent.width; model: sheet.dep.drones || []; textRole: "label"; valueRole: "value"
                            displayText: count === 0 ? qsTr("No drone in this deployment") : currentText }
            }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Pilot") }
                AppSelect { id: pilot; width: parent.width; model: sheet.dep.pilots || []; textRole: "label"; valueRole: "value"
                            displayText: count === 0 ? qsTr("No licensed pilot in the crew") : currentText }
            }
        }
        Row {
            spacing: Theme.space.md
            AppTextField { id: minutes; width: 150; label: qsTr("Flight time (minutes)") }
            AppTextField { id: landings; width: 110; label: qsTr("Landings") }
            AppTextField { id: cycles; width: 110; label: qsTr("Cycles") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Batteries used") }
                CheckList { id: batteries; width: parent.width; maxHeight: 140; model: sheet.dep.batteries || []
                            emptyText: qsTr("No flight batteries went out.") }
            }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("SD cards / disks that carried the data") }
                CheckList { id: media; width: parent.width; maxHeight: 140; model: sheet.dep.media || []
                            emptyText: qsTr("No data cards went out.") }
            }
        }
        Column {
            width: parent.width
            spacing: 6
            Label { text: qsTr("PPK base (if used)") }
            AppSelect {
                id: base
                width: 320
                model: [{ value: "", label: qsTr("Not used") }].concat(sheet.dep.receivers || [])
                textRole: "label"
                valueRole: "value"
            }
        }
        AppTextField { id: notes; width: parent.width; label: qsTr("Notes (optional)") }
        ErrorBanner { text: Projects.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            text: qsTr("Log flight")
            busy: Tasks.busy
            enabled: !Tasks.busy && drone.count > 0 && pilot.count > 0
            onClicked: Projects.logSortie({
                deploymentId: deployment.currentValue || "", droneId: drone.currentValue || "",
                pilotId: pilot.currentValue || "", flownOn: Qt.formatDate(day.selectedDate, "yyyy-MM-dd"),
                minutes: minutes.text, landings: landings.text, cycles: cycles.text,
                batteryIds: batteries.selected, mediaIds: media.selected,
                ppkBaseId: base.currentValue || "", notes: notes.text
            })
        }
    ]
}
