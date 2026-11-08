import QtQuick
import "../components"

// Register a new asset, or edit an existing one's details.
Sheet {
    id: sheet

    property bool isNew: true
    property var asset: ({})
    readonly property var typeInfo: {
        var options = Equipment.itemTypeOptions
        for (var i = 0; i < options.length; ++i)
            if (options[i].value === itemType.currentValue) return options[i]
        return ({ serialized: false, warranty: false, meters: [] })
    }

    width: Math.min(620, parent ? parent.width - 64 : 620)
    title: isNew ? qsTr("Register asset") : qsTr("Edit %1").arg(asset.tag || "")
    subtitle: isNew ? qsTr("Choose what it is; the next free tag is filled in for you.") : asset.itemType || ""

    function iso(picker) { return picker.hasDate ? Qt.formatDate(picker.selectedDate, "yyyy-MM-dd") : "" }
    function setDate(picker, value) {
        picker.hasDate = value !== ""
        if (value !== "") picker.selectedDate = new Date(value + "T00:00:00")
    }

    function openNew() {
        isNew = true
        asset = ({})
        Equipment.clearError()
        itemType.currentIndex = 0
        tag.text = Equipment.suggestTag(itemType.currentValue || "")
        for (var f of [serial, make, modelField, notes, hours, cycles, landings]) f.text = ""
        homeSite.currentIndex = 0
        setDate(acquired, ""); setDate(warranty, "")
        open()
    }
    function openEdit(detail) {
        isNew = false
        asset = detail
        Equipment.clearError()
        itemType.selectValue(detail.itemTypeId)
        tag.text = detail.tag; serial.text = detail.serial; make.text = detail.make
        modelField.text = detail.model; notes.text = detail.notes
        homeSite.selectValue(detail.homeSiteId)
        setDate(acquired, detail.acquiredOn); setDate(warranty, detail.warrantyUntil)
        open()
    }
    function values() {
        return {
            itemTypeId: itemType.currentValue, tag: tag.text, serial: serial.text, make: make.text,
            model: modelField.text, homeSiteId: homeSite.currentValue || "", notes: notes.text,
            acquiredOn: iso(acquired), warrantyUntil: typeInfo.warranty ? iso(warranty) : "",
            hours: hours.text, cycles: cycles.text, landings: landings.text
        }
    }

    Connections {
        target: Equipment
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md

        Column {
            width: parent.width
            spacing: 6
            Txt { text: qsTr("What is it?"); variant: "caption"; font.weight: Theme.type.medium }
            AppSelect {
                id: itemType
                width: parent.width
                enabled: sheet.isNew
                model: Equipment.itemTypeOptions
                textRole: "label"
                valueRole: "value"
                onActivated: if (sheet.isNew) tag.text = Equipment.suggestTag(currentValue)
            }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: tag; width: 160; label: qsTr("Asset tag"); iconName: "layers" }
            AppTextField {
                id: serial
                width: parent.width - 160 - parent.spacing
                label: sheet.typeInfo.serialized ? qsTr("Serial number (required)") : qsTr("Serial number (if it has one)")
            }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: make; width: (parent.width - parent.spacing) / 2; label: qsTr("Make"); placeholder: qsTr("e.g. Trimble") }
            AppTextField { id: modelField; width: (parent.width - parent.spacing) / 2; label: qsTr("Model"); placeholder: qsTr("e.g. R12") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Home site"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect { id: homeSite; width: parent.width; model: Equipment.siteOptions; textRole: "label"; valueRole: "value" }
            }
            AppDatePicker { id: acquired; width: (parent.width - parent.spacing) / 2; label: qsTr("Acquired on") }
        }
        AppDatePicker { id: warranty; visible: sheet.typeInfo.warranty; width: (parent.width - Theme.space.md) / 2; label: qsTr("Warranty until") }

        Column {
            visible: sheet.isNew && sheet.typeInfo.meters.length > 0
            width: parent.width
            spacing: Theme.space.xs
            Txt { text: qsTr("Usage so far (if it is not new)"); variant: "bodyStrong" }
            Row {
                spacing: Theme.space.md
                AppTextField { id: hours; visible: sheet.typeInfo.meters.indexOf("hours") >= 0; width: 140; label: qsTr("Flight hours") }
                AppTextField { id: cycles; visible: sheet.typeInfo.meters.indexOf("cycles") >= 0; width: 140; label: qsTr("Cycles") }
                AppTextField { id: landings; visible: sheet.typeInfo.meters.indexOf("landings") >= 0; width: 140; label: qsTr("Landings") }
            }
        }
        AppTextField { id: notes; width: parent.width; label: qsTr("Notes") }
        ErrorBanner { text: Equipment.error }
    }

    actions: [
        AppButton { text: qsTr("Cancel"); onClicked: sheet.close() },
        AppButton {
            variant: "primary"
            text: sheet.isNew ? qsTr("Register") : qsTr("Save changes")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: sheet.isNew ? Equipment.register(sheet.values())
                                   : Equipment.update(sheet.asset.assetId, sheet.asset.version, sheet.values())
        }
    ]
}
