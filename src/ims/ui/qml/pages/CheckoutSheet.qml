import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Check equipment, crew and GCP banners out to a project. A readiness check runs as
// choices change; anything that blocks the deployment is listed and Deploy stays off.
Sheet {
    id: sheet

    readonly property var c: Deployments.choices
    readonly property var r: Deployments.readiness
    property string presetProject: ""

    width: Math.min(820, parent ? parent.width - 64 : 820)
    title: qsTr("Check out equipment")
    subtitle: qsTr("Everything is checked before it goes: condition, documents, certificates and stock.")

    function iso(picker) { return picker.hasDate ? Qt.formatDate(picker.selectedDate, "yyyy-MM-dd") : "" }
    function values() {
        return {
            projectId: project.currentValue || "", deployedOn: iso(day),
            kitIds: kits.selected, assetIds: equipment.selected, crewIds: crew.selected,
            gcpQuantity: gcpStore.currentValue ? gcp.text : "0", gcpSiteId: gcpStore.currentValue || "",
            notes: notes.text
        }
    }
    function recheck() { if (sheet.opened) checkTimer.restart() }

    function openFor(projectId) {
        presetProject = projectId || ""
        Deployments.clearError()
        Deployments.loadChoices()
        kits.selected = []; equipment.selected = []; crew.selected = []
        gcp.text = ""; notes.text = ""; search.text = ""
        day.hasDate = true; day.selectedDate = new Date()
        open()
    }
    onCChanged: {
        if (presetProject) project.selectValue(presetProject)
        recheck()
    }

    Timer { id: checkTimer; interval: 250; onTriggered: Deployments.check(sheet.values()) }
    Connections {
        target: Deployments
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
                Label { text: qsTr("Project") }
                AppSelect {
                    id: project
                    width: parent.width
                    model: sheet.c.projects || []
                    textRole: "label"
                    valueRole: "value"
                    displayText: count === 0 ? qsTr("No open projects") : currentText
                }
            }
            AppDatePicker { id: day; width: 200; label: qsTr("Going out on"); onPicked: sheet.recheck() }
        }

        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Kits (everything in the kit goes)") }
                CheckList {
                    id: kits
                    width: parent.width
                    maxHeight: 150
                    model: sheet.c.kits || []
                    emptyText: qsTr("No kits set up.")
                    onToggled: sheet.recheck()
                }
            }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Label { text: qsTr("Crew") }
                CheckList {
                    id: crew
                    width: parent.width
                    maxHeight: 150
                    model: sheet.c.crew || []
                    onToggled: sheet.recheck()
                }
            }
        }

        Column {
            width: parent.width
            spacing: 6
            Item {
                width: parent.width
                height: search.height
                Label { anchors.verticalCenter: parent.verticalCenter; text: qsTr("More equipment (in store, not in a kit)") }
                AppTextField { id: search; anchors.right: parent.right; width: 220; placeholder: qsTr("Filter"); iconName: "search" }
            }
            CheckList {
                id: equipment
                width: parent.width
                maxHeight: 200
                model: (sheet.c.equipment || []).filter(function (o) {
                    var q = search.text.trim().toLowerCase()
                    return !q || (o.label + " " + o.detail).toLowerCase().indexOf(q) >= 0 || equipment.isSelected(o.value)
                })
                emptyText: qsTr("No equipment in store.")
                onToggled: sheet.recheck()
            }
        }

        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: 360
                spacing: 6
                Label { text: qsTr("GCP banners from") }
                AppSelect {
                    id: gcpStore
                    width: parent.width
                    model: sheet.c.stores || []
                    textRole: "label"
                    valueRole: "value"
                    onActivated: sheet.recheck()
                }
            }
            AppTextField {
                id: gcp
                visible: !!gcpStore.currentValue
                width: 140
                label: qsTr("How many")
                onTextChanged: sheet.recheck()
            }
        }
        AppTextField { id: notes; width: parent.width; label: qsTr("Notes (optional)") }

        // ------------------------------------------------------------ readiness
        Rectangle {
            width: parent.width
            height: checks.implicitHeight + Theme.space.md * 2
            radius: Theme.radius.md
            readonly property bool blocked: (sheet.r.blockers || []).length > 0
            color: blocked ? Theme.colors.dangerBg : (sheet.r.ready ? Theme.colors.successBg : Theme.colors.element)
            border.width: 1
            border.color: blocked ? Theme.colors.dangerBorder : (sheet.r.ready ? Theme.colors.successBorder : Theme.colors.divider)
            Behavior on color { ColorAnimation { duration: Theme.motion.standard } }
            Column {
                id: checks
                x: Theme.space.md
                y: Theme.space.md
                width: parent.width - Theme.space.md * 2
                spacing: 4
                Row {
                    spacing: Theme.space.xs
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: (sheet.r.blockers || []).length ? "circle-x" : (sheet.r.ready ? "circle-check" : "info")
                        size: 16
                        color: (sheet.r.blockers || []).length ? Theme.colors.dangerText : (sheet.r.ready ? Theme.colors.successText : Theme.colors.textMuted)
                    }
                    Txt {
                        variant: "bodyStrong"
                        text: (sheet.r.blockers || []).length
                              ? qsTr("%n thing(s) stop this deployment", "", sheet.r.blockers.length)
                              : sheet.r.ready ? qsTr("Ready: %n item(s) can go out", "", sheet.r.items || 0)
                                              : qsTr("Choose equipment and crew")
                    }
                }
                Repeater {
                    model: sheet.r.blockers || []
                    delegate: Txt { required property string modelData; width: checks.width; text: "•  " + modelData; color: Theme.colors.dangerText; wrapMode: Text.WordWrap }
                }
                Repeater {
                    model: sheet.r.warnings || []
                    delegate: Txt { required property string modelData; width: checks.width; text: "•  " + modelData; color: Theme.colors.warningText; wrapMode: Text.WordWrap }
                }
            }
        }
        ErrorBanner { text: Deployments.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            iconName: "send"
            text: qsTr("Check out")
            busy: Tasks.busy
            enabled: !Tasks.busy && !!sheet.r.ready && !!project.currentValue
            onClicked: Deployments.deploy(sheet.values())
        }
    ]
}
