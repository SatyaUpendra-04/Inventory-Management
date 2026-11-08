import QtQuick
import "../components"

// Add, edit or view a site.
Sheet {
    id: sheet

    property bool isNew: true
    property var site: ({})
    property bool confirmingRemove: false
    readonly property bool editable: Sites.canManage

    width: Math.min(600, parent ? parent.width - 64 : 600)
    title: isNew ? qsTr("Add site") : site.code + " · " + site.name
    subtitle: isNew ? qsTr("A store, mine site, workshop or office.") : site.kindLabel || ""

    function openNew() { isNew = true; site = ({}); reset(); open() }
    function openEdit(siteId) { isNew = false; site = Sites.site(siteId); reset(); open() }
    function reset() {
        Sites.clearError()
        confirmingRemove = false
        code.text = site.code || ""
        name.text = site.name || ""
        kind.selectValue(site.kind || "store")
        status.selectValue(site.status || "active")
        region.text = site.region || ""
        mineral.text = site.mineral || ""
        latitude.text = site.latitude || ""
        longitude.text = site.longitude || ""
        area.text = site.area || ""
        notes.text = site.notes || ""
    }
    function values() {
        return {
            code: code.text, name: name.text, kind: kind.currentValue, status: status.currentValue,
            region: region.text, mineral: mineral.text, latitude: latitude.text,
            longitude: longitude.text, area: area.text, notes: notes.text
        }
    }

    Connections {
        target: Sites
        function onSaved() { if (sheet.opened) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md
        enabled: sheet.editable

        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: code; width: 160; label: qsTr("Code"); placeholder: "MAIN-STORE" }
            AppTextField { id: name; width: parent.width - 160 - parent.spacing; label: qsTr("Name") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Type"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect { id: kind; width: parent.width; model: Sites.kinds(); textRole: "label"; valueRole: "value" }
            }
            Column {
                width: (parent.width - parent.spacing) / 2
                spacing: 6
                Txt { text: qsTr("Status"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect { id: status; width: parent.width; model: Sites.statuses(); textRole: "label"; valueRole: "value" }
            }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: region; width: (parent.width - parent.spacing) / 2; label: qsTr("Region"); placeholder: qsTr("e.g. Keonjhar, Odisha") }
            AppTextField { id: mineral; width: (parent.width - parent.spacing) / 2; label: qsTr("Mineral"); placeholder: qsTr("e.g. Iron ore") }
        }
        Row {
            width: parent.width
            spacing: Theme.space.md
            AppTextField { id: latitude; width: (parent.width - parent.spacing * 2) / 3; label: qsTr("Latitude"); placeholder: "21.6289" }
            AppTextField { id: longitude; width: (parent.width - parent.spacing * 2) / 3; label: qsTr("Longitude"); placeholder: "85.5817" }
            AppTextField { id: area; width: (parent.width - parent.spacing * 2) / 3; label: qsTr("Area (hectares)") }
        }
        AppTextField { id: notes; width: parent.width; label: qsTr("Notes") }

        Column {
            visible: !sheet.isNew && sheet.editable
            width: parent.width
            spacing: Theme.space.xs
            AppButton {
                visible: !sheet.confirmingRemove
                compact: true
                variant: "ghost"
                iconName: "x"
                text: qsTr("Remove site…")
                onClicked: sheet.confirmingRemove = true
            }
            Row {
                visible: sheet.confirmingRemove
                spacing: Theme.space.xs
                Txt { anchors.verticalCenter: parent.verticalCenter; text: qsTr("Remove this site?"); color: Theme.colors.dangerText }
                AppButton { compact: true; text: qsTr("Keep"); onClicked: sheet.confirmingRemove = false }
                AppButton { compact: true; variant: "danger"; text: qsTr("Remove"); onClicked: Sites.remove(sheet.site.siteId, sheet.site.version) }
            }
        }

        ErrorBanner { text: Sites.error }
    }

    actions: [
        AppButton { text: sheet.editable ? qsTr("Cancel") : qsTr("Close"); onClicked: sheet.close() },
        AppButton {
            visible: sheet.editable
            variant: "primary"
            text: sheet.isNew ? qsTr("Add site") : qsTr("Save changes")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: sheet.isNew ? Sites.create(sheet.values()) : Sites.update(sheet.site.siteId, sheet.site.version, sheet.values())
        }
    ]
}
