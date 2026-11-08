import QtQuick
import "../components"

// Log one GNSS survey session: which receiver was the base, which were rovers, results.
Sheet {
    id: sheet

    property var deployments: []
    readonly property var dep: deployments.length ? deployments[Math.max(0, deployment.currentIndex)] : ({})

    width: Math.min(680, parent ? parent.width - 64 : 680)
    title: qsTr("Log survey session")
    subtitle: qsTr("The same receiver can be the base one day and a rover the next.")

    function start(list) {
        deployments = list || []
        Projects.clearError()
        deployment.currentIndex = 0
        for (var f of [hours, area, points, fixRate, notes]) f.text = ""
        rovers.selected = []; batteries.selected = []
        mode.currentIndex = 0; base.currentIndex = 0; controller.currentIndex = 0
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
                    onActivated: { rovers.selected = []; batteries.selected = [] }
                }
            }
            AppDatePicker { id: day; width: 200; label: qsTr("Surveyed on") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) * 0.6
                spacing: 6
                Label { text: qsTr("Surveyor") }
                AppSelect { id: surveyor; width: parent.width; model: sheet.dep.crewOptions || []; textRole: "label"; valueRole: "value" }
            }
            Column {
                width: (parent.width - parent.spacing) * 0.4
                spacing: 6
                Label { text: qsTr("Method") }
                AppSelect { id: mode; width: parent.width; model: Projects.surveyModes(); textRole: "label"; valueRole: "value" }
            }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Base") }
                AppSelect {
                    id: base
                    width: parent.width
                    model: [{ value: "", label: qsTr("No base (network RTK)") }].concat(sheet.dep.receivers || [])
                    textRole: "label"
                    valueRole: "value"
                    onActivated: {
                        var at = rovers.selected.indexOf(currentValue)
                        if (at >= 0) rovers.toggle(currentValue)
                    }
                }
                Label { text: qsTr("Controller") ; topPadding: Theme.space.xs }
                AppSelect {
                    id: controller
                    width: parent.width
                    model: [{ value: "", label: qsTr("Not recorded") }].concat(sheet.dep.controllers || [])
                    textRole: "label"
                    valueRole: "value"
                }
            }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Rovers") }
                CheckList {
                    id: rovers
                    width: parent.width
                    maxHeight: 120
                    model: (sheet.dep.receivers || []).filter(function (r) { return r.value !== base.currentValue })
                    emptyText: qsTr("No receivers went out.")
                }
            }
        }
        Row {
            spacing: Theme.space.md
            AppTextField { id: hours; width: 120; label: qsTr("Hours") }
            AppTextField { id: area; width: 130; label: qsTr("Area (ha)") }
            AppTextField { id: points; width: 120; label: qsTr("Points") }
            AppTextField { id: fixRate; width: 130; label: qsTr("Fix rate (%)") }
        }
        Column {
            width: parent.width
            spacing: 6
            Label { text: qsTr("Receiver and controller batteries used") }
            CheckList { id: batteries; width: parent.width; maxHeight: 120; model: sheet.dep.gnssBatteries || []
                        emptyText: qsTr("No survey batteries went out.") }
        }
        AppTextField { id: notes; width: parent.width; label: qsTr("Notes (optional)") }
        ErrorBanner { text: Projects.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            text: qsTr("Log session")
            busy: Tasks.busy
            enabled: !Tasks.busy && surveyor.count > 0
            onClicked: Projects.logSession({
                deploymentId: deployment.currentValue || "", surveyorId: surveyor.currentValue || "",
                surveyedOn: Qt.formatDate(day.selectedDate, "yyyy-MM-dd"), mode: mode.currentValue,
                baseId: base.currentValue || "", roverIds: rovers.selected,
                controllerId: controller.currentValue || "", batteryIds: batteries.selected,
                hours: hours.text, area: area.text, points: points.text, fixRate: fixRate.text,
                notes: notes.text
            })
        }
    ]
}
