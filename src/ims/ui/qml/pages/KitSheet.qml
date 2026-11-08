import QtQuick
import "../components"

// Create a kit, or manage one: members, what is missing, break it up.
Sheet {
    id: sheet

    property bool isNew: true
    property bool confirmingBreakUp: false
    readonly property var d: Kits.detail

    width: Math.min(640, parent ? parent.width - 64 : 640)
    title: isNew ? qsTr("New kit") : (d.code ? d.code + "  ·  " + d.name : qsTr("Loading…"))
    subtitle: isNew ? qsTr("Give it a code and choose a template to check it against.")
                    : (d.templateName ? qsTr("Template: %1").arg(d.templateName) : qsTr("No template"))

    function openNew() {
        isNew = true
        Kits.clearError()
        code.text = ""; name.text = ""
        template.currentIndex = template.count > 1 ? 1 : 0
        site.currentIndex = 0
        open()
    }
    function show(kitId) {
        isNew = false
        confirmingBreakUp = false
        Kits.clearError()
        Kits.openKit(kitId)
        open()
    }

    Connections {
        target: Kits
        function onSaved(message) { if (sheet.opened && sheet.isNew) sheet.close() }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md

        // ------------------------------------------------------------ new kit
        Column {
            visible: sheet.isNew
            width: parent.width
            spacing: Theme.space.md
            Row {
                width: parent.width
                spacing: Theme.space.md
                AppTextField { id: code; width: 180; label: qsTr("Code"); placeholder: "KIT-DRONE-01" }
                AppTextField { id: name; width: parent.width - 180 - parent.spacing; label: qsTr("Name"); placeholder: qsTr("e.g. Mapping kit 1") }
            }
            Row {
                width: parent.width
                spacing: Theme.space.md
                Column {
                    width: (parent.width - parent.spacing) / 2
                    spacing: 6
                    Txt { text: qsTr("Template"); variant: "caption"; font.weight: Theme.type.medium }
                    AppSelect { id: template; width: parent.width; model: sheet.opened ? Kits.templates() : []; textRole: "label"; valueRole: "value" }
                }
                Column {
                    width: (parent.width - parent.spacing) / 2
                    spacing: 6
                    Txt { text: qsTr("Home site"); variant: "caption"; font.weight: Theme.type.medium }
                    AppSelect { id: site; width: parent.width; model: Equipment.siteOptions; textRole: "label"; valueRole: "value" }
                }
            }
        }

        // ------------------------------------------------------------ existing kit
        Column {
            visible: !sheet.isNew && sheet.d.kitId !== undefined
            width: parent.width
            spacing: Theme.space.sm

            StatusPill { kind: sheet.d.statusKind || "neutral"; text: sheet.d.statusLabel || "" }
            Txt {
                visible: (sheet.d.missing || []).length > 0
                width: parent.width
                text: qsTr("Missing: %1").arg((sheet.d.missing || []).join(", "))
                color: Theme.colors.warningText
                wrapMode: Text.WordWrap
            }
            Repeater {
                model: sheet.d.members || []
                delegate: Rectangle {
                    required property var modelData
                    width: parent.width
                    height: 38
                    radius: Theme.radius.sm
                    color: Theme.colors.element
                    Row {
                        x: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 110; text: modelData.tag; variant: "bodyStrong" }
                        Txt { text: modelData.itemType }
                    }
                    AppButton {
                        visible: Kits.canManage
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        variant: "ghost"
                        text: qsTr("Remove")
                        onClicked: Kits.removeMember(sheet.d.kitId, sheet.d.version, modelData.assetId)
                    }
                }
            }
            Txt { visible: (sheet.d.members || []).length === 0; text: qsTr("No equipment in this kit yet."); muted: true }
            Row {
                visible: Kits.canManage
                spacing: Theme.space.xs
                AppSelect {
                    id: candidate
                    width: 360
                    model: sheet.d.candidates || []
                    textRole: "label"
                    valueRole: "value"
                    displayText: count === 0 ? qsTr("No free equipment to add") : currentText
                }
                AppButton {
                    text: qsTr("Add to kit")
                    enabled: candidate.count > 0
                    onClicked: Kits.addMember(sheet.d.kitId, sheet.d.version, candidate.currentValue)
                }
            }
            Row {
                visible: Kits.canManage
                spacing: Theme.space.xs
                AppButton { visible: !sheet.confirmingBreakUp; compact: true; variant: "ghost"; iconName: "x"; text: qsTr("Break up kit…"); onClicked: sheet.confirmingBreakUp = true }
                Txt { visible: sheet.confirmingBreakUp; anchors.verticalCenter: parent.verticalCenter; text: qsTr("The equipment stays registered."); color: Theme.colors.dangerText }
                AppButton { visible: sheet.confirmingBreakUp; compact: true; text: qsTr("Keep"); onClicked: sheet.confirmingBreakUp = false }
                AppButton { visible: sheet.confirmingBreakUp; compact: true; variant: "danger"; text: qsTr("Break up")
                            onClicked: { Kits.breakUp(sheet.d.kitId, sheet.d.version); sheet.close() } }
            }
        }

        ErrorBanner { text: Kits.error }
    }

    actions: [
        AppButton { text: sheet.isNew ? qsTr("Cancel") : qsTr("Close"); onClicked: sheet.close() },
        AppButton {
            visible: sheet.isNew
            variant: "primary"
            text: qsTr("Create kit")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: Kits.create({ code: code.text, name: name.text, templateId: template.currentValue || "",
                                     homeSiteId: site.currentValue || "" })
        }
    ]
}
