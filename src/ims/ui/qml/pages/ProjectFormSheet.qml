import QtQuick
import "../components"

// Create or edit a project.
Sheet {
    id: sheet

    property bool isNew: true
    property var project: ({})
    property bool codeTouched: false

    width: Math.min(620, parent ? parent.width - 64 : 620)
    title: isNew ? qsTr("New project") : qsTr("Edit %1").arg(project.code || "")
    subtitle: isNew ? qsTr("The chief pilot must hold a valid DGCA certificate.") : project.name || ""

    function iso(picker) { return picker.hasDate ? Qt.formatDate(picker.selectedDate, "yyyy-MM-dd") : "" }
    function setDate(picker, value) {
        picker.hasDate = value !== ""
        if (value !== "") picker.selectedDate = new Date(value + "T00:00:00")
    }
    function suggest() {
        if (isNew && !codeTouched)
            code.text = Projects.suggestCode(site.currentValue || "", iso(starts))
    }

    function openNew() {
        isNew = true
        project = ({})
        Projects.clearError()
        for (var f of [name, client, notes]) f.text = ""
        site.currentIndex = 0
        pilot.currentIndex = 0
        surveyor.currentIndex = 0
        setDate(starts, Qt.formatDate(new Date(), "yyyy-MM-dd")); setDate(ends, "")
        codeTouched = false
        suggest()
        open()
    }
    function openEdit(detail) {
        isNew = false
        project = detail
        Projects.clearError()
        code.text = detail.code; name.text = detail.name; client.text = detail.client
        notes.text = detail.notes
        site.selectValue(detail.siteId)
        pilot.selectValue(detail.chiefPilotId)
        surveyor.selectValue(detail.surveyorId)
        setDate(starts, detail.startsOn); setDate(ends, detail.endsOn)
        codeTouched = true
        open()
    }
    function values() {
        return {
            code: code.text, name: name.text, siteId: site.currentValue || "", client: client.text,
            startsOn: iso(starts), endsOn: iso(ends), chiefPilotId: pilot.currentValue || "",
            surveyorId: surveyor.currentValue || "", notes: notes.text
        }
    }

    Connections {
        target: Projects
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md

        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Site"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect {
                    id: site
                    width: parent.width
                    model: Projects.siteOptions
                    textRole: "label"
                    valueRole: "value"
                    displayText: count === 0 ? qsTr("Add a site first") : currentText
                    onActivated: sheet.suggest()
                }
            }
            AppTextField {
                id: code
                width: (parent.width - parent.spacing) / 2
                label: qsTr("Project code")
                Connections { target: code.field; function onTextEdited() { sheet.codeTouched = true } }
            }
        }
        AppTextField { id: name; width: parent.width; label: qsTr("Name"); placeholder: qsTr("e.g. Keonjhar pit volume survey") }
        AppTextField { id: client; width: parent.width; label: qsTr("Client (optional)") }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppDatePicker { id: starts; width: (parent.width - parent.spacing) / 2; label: qsTr("Starts"); onPicked: sheet.suggest() }
            AppDatePicker { id: ends; width: (parent.width - parent.spacing) / 2; label: qsTr("Ends (if known)") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Chief pilot"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect { id: pilot; width: parent.width; model: Projects.pilotOptions; textRole: "label"; valueRole: "value" }
            }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Lead surveyor"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect { id: surveyor; width: parent.width; model: Projects.surveyorOptions; textRole: "label"; valueRole: "value" }
            }
        }
        AppTextField { id: notes; width: parent.width; label: qsTr("Notes") }
        ErrorBanner { text: Projects.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            text: sheet.isNew ? qsTr("Create project") : qsTr("Save changes")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: sheet.isNew ? Projects.create(sheet.values())
                                   : Projects.update(sheet.project.projectId, sheet.project.version, sheet.values())
        }
    ]
}
