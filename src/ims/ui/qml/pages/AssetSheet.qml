import QtQuick
import QtQuick.Controls.Basic
import "../components"

// One asset's full record: condition, actions, fitted parts, documents, firmware, history.
Sheet {
    id: sheet

    readonly property var d: Equipment.detail
    readonly property bool loaded: d.assetId !== undefined
    property string pendingAction: ""
    property string documentFile: ""
    property bool reporting: false
    property string recordTask: ""

    signal editRequested(var detail)

    width: Math.min(860, parent ? parent.width - 64 : 860)
    title: loaded ? d.tag + "  ·  " + d.itemType : qsTr("Loading…")
    subtitle: loaded ? [d.categoryLabel, d.site].filter(function (s) { return s }).join("  ·  ") : ""

    function show(assetId) {
        Equipment.clearError()
        Maintenance.clearError()
        reporting = false
        recordTask = ""
        pendingAction = ""
        Equipment.openAsset(assetId)
        open()
    }
    onClosed: Equipment.closeAsset()

    function iso(picker) { return picker.hasDate ? Qt.formatDate(picker.selectedDate, "yyyy-MM-dd") : "" }

    component Heading: Txt { variant: "headline"; topPadding: Theme.space.xs }
    component Field: Column {
        property string label: ""
        property string value: ""
        width: 180
        spacing: 2
        Txt { text: parent.label; variant: "caption"; muted: true }
        Txt { text: parent.value || "—"; muted: !parent.value; width: parent.width; elide: Text.ElideRight }
    }

    Column {
        width: parent.width
        spacing: Theme.space.md
        visible: sheet.loaded

        // ------------------------------------------------------------ condition
        Flow {
            width: parent.width
            spacing: Theme.space.xs
            StatusPill { kind: sheet.d.serviceKind || "neutral"; text: sheet.d.serviceLabel || "" }
            StatusPill { kind: "neutral"; text: sheet.d.custodyLabel || "" }
            StatusPill { visible: !!sheet.d.kitCode; kind: "info"; text: qsTr("In %1").arg(sheet.d.kitCode || "") }
            Repeater {
                model: sheet.d.problems || []
                delegate: StatusPill { required property var modelData; kind: modelData.kind; text: modelData.text }
            }
        }

        Flow {
            width: parent.width
            spacing: Theme.space.lg
            Field { label: qsTr("Serial number"); value: sheet.d.serial || "" }
            Field { label: qsTr("Make and model"); value: [sheet.d.make, sheet.d.model].filter(function (s) { return s }).join(" ") }
            Field { label: qsTr("Home site"); value: sheet.d.site || "" }
            Field { label: qsTr("Acquired"); value: sheet.d.acquiredOn || "" }
            Field { visible: !!sheet.d.tracksWarranty; label: qsTr("Warranty until"); value: sheet.d.warrantyUntil || "" }
            Field { visible: (sheet.d.firmware || []).length > 0; label: qsTr("Firmware"); value: ((sheet.d.firmware || [])[0] || {}).version || "" }
            Repeater {
                model: sheet.d.meters || []
                delegate: Field { required property var modelData; label: modelData.label; value: modelData.value }
            }
        }
        Txt { visible: !!sheet.d.notes; width: parent.width; text: sheet.d.notes || ""; muted: true; wrapMode: Text.WordWrap }

        // ------------------------------------------------------------ status actions
        Column {
            visible: (sheet.d.actions || []).length > 0
            width: parent.width
            spacing: Theme.space.xs
            Flow {
                width: parent.width
                spacing: Theme.space.xs
                Repeater {
                    model: sheet.d.actions || []
                    delegate: AppButton {
                        required property var modelData
                        compact: true
                        text: modelData.label
                        variant: modelData.key === "ground" ? "danger"
                               : modelData.key === "certify" ? "primary" : "secondary"
                        onClicked: {
                            if (modelData.needsReason) { sheet.pendingAction = modelData.key; reason.text = "" }
                            else Equipment.changeStatus(sheet.d.assetId, modelData.key, "")
                        }
                    }
                }
                AppButton {
                    visible: Equipment.canManage
                    compact: true
                    variant: "ghost"
                    iconName: "sliders"
                    text: qsTr("Edit details")
                    onClicked: sheet.editRequested(sheet.d)
                }
            }
            Row {
                visible: sheet.pendingAction !== ""
                spacing: Theme.space.xs
                AppTextField { id: reason; width: 360; placeholder: qsTr("Reason (required), e.g. Motor 3 vibration after landing") }
                AppButton { y: 0; compact: true; variant: "danger"; text: qsTr("Confirm")
                            onClicked: { Equipment.changeStatus(sheet.d.assetId, sheet.pendingAction, reason.text); sheet.pendingAction = "" } }
                AppButton { compact: true; text: qsTr("Cancel"); onClicked: sheet.pendingAction = "" }
            }
        }

        // ------------------------------------------------------------ maintenance
        Column {
            readonly property var m: sheet.d.maintenance || ({})
            id: maintenanceSection
            visible: (m.tasks || []).length > 0 || (m.defects || []).length > 0 || Maintenance.canReport
            width: parent.width
            spacing: Theme.space.xs
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Item {
                width: parent.width
                height: maintenanceHeading.height
                Heading { id: maintenanceHeading; text: qsTr("Maintenance") }
                Row {
                    anchors.right: parent.right
                    anchors.bottom: parent.bottom
                    spacing: Theme.space.xs
                    AppButton { visible: Maintenance.canReport && !sheet.reporting; compact: true; variant: "ghost"; iconName: "alert"
                                text: qsTr("Report defect…"); onClicked: { sheet.reporting = true; defectText.text = ""; unsafe.checked = false } }
                    AppButton { visible: Maintenance.canManage && !maintenanceSection.m.workOrderId; compact: true; iconName: "wrench"
                                text: qsTr("Open work order…")
                                onClicked: orderSheet.openNew(sheet.d.assetId, sheet.d.tag, "", [], []) }
                    AppButton { visible: !!maintenanceSection.m.workOrderId; compact: true; iconName: "wrench"
                                text: maintenanceSection.m.workOrder || ""
                                onClicked: orderSheet.show(maintenanceSection.m.workOrderId) }
                }
            }
            Rectangle {
                visible: (maintenanceSection.m.grounding || []).length > 0
                width: parent.width
                height: groundCol.implicitHeight + Theme.space.sm * 2
                radius: Theme.radius.sm
                color: Theme.colors.dangerBg
                border.width: 1
                border.color: Theme.colors.dangerBorder
                Column {
                    id: groundCol
                    x: Theme.space.sm; y: Theme.space.sm
                    width: parent.width - Theme.space.sm * 2
                    Repeater {
                        model: maintenanceSection.m.grounding || []
                        delegate: Txt { required property string modelData; width: groundCol.width; wrapMode: Text.WordWrap
                                        text: "•  " + modelData; color: Theme.colors.dangerText }
                    }
                }
            }
            // report a defect, inline
            Column {
                visible: sheet.reporting
                width: parent.width
                spacing: Theme.space.xs
                AppTextField { id: defectText; width: parent.width; placeholder: qsTr("What is wrong? e.g. Arm 3 creaks under load") }
                Row {
                    spacing: Theme.space.sm
                    AppCheckBox { id: unsafe; text: qsTr("Unsafe: ground it now") }
                    AppButton { compact: true; text: qsTr("Cancel"); onClicked: sheet.reporting = false }
                    AppButton { compact: true; variant: unsafe.checked ? "danger" : "primary"; text: qsTr("Report")
                                onClicked: { Maintenance.reportDefect(sheet.d.assetId, defectText.text, unsafe.checked); sheet.reporting = false } }
                }
            }
            Repeater {
                model: maintenanceSection.m.defects || []
                delegate: Rectangle {
                    required property var modelData
                    width: parent.width
                    height: 36
                    radius: Theme.radius.sm
                    color: Theme.colors.element
                    Row {
                        x: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 80; text: modelData.number; variant: "bodyStrong" }
                        Txt { width: 420; elide: Text.ElideRight
                              text: modelData.description + (modelData.limitation ? qsTr("  ·  limitation: %1").arg(modelData.limitation) : "") }
                    }
                    StatusPill { anchors.right: parent.right; anchors.rightMargin: Theme.space.sm; anchors.verticalCenter: parent.verticalCenter
                                 kind: modelData.stateKind; text: modelData.stateLabel }
                }
            }
            Repeater {
                model: maintenanceSection.m.tasks || []
                delegate: Item {
                    required property var modelData
                    width: parent.width
                    height: 34
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 220; height: 34; text: modelData.task; elide: Text.ElideRight }
                        Txt { width: 190; height: 34; text: modelData.intervals; variant: "caption"; muted: true; elide: Text.ElideRight }
                        Item { width: 96; height: 34
                               StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: modelData.stateKind; text: modelData.stateLabel } }
                        Txt { width: 200; height: 34; text: modelData.summary; variant: "caption"; font.features: { "tnum": 1 }
                              color: modelData.state === "overdue" ? Theme.colors.dangerText : Theme.colors.textMuted }
                    }
                    AppButton {
                        visible: Maintenance.canManage && !modelData.lifeLimit
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        variant: "ghost"
                        text: qsTr("Record done…")
                        onClicked: { sheet.recordTask = modelData.taskId; recordNote.text = ""; recordDay.hasDate = true; recordDay.selectedDate = new Date() }
                    }
                }
            }
            Row {
                visible: sheet.recordTask !== ""
                spacing: Theme.space.xs
                AppDatePicker { id: recordDay; width: 180 }
                AppTextField { id: recordNote; width: 260; placeholder: qsTr("Note, e.g. done by the dealer") }
                AppButton { text: qsTr("Cancel"); onClicked: sheet.recordTask = "" }
                AppButton { variant: "primary"; text: qsTr("Record")
                            onClicked: { Maintenance.recordDone(sheet.d.assetId, sheet.recordTask,
                                                                Qt.formatDate(recordDay.selectedDate, "yyyy-MM-dd"), recordNote.text)
                                         sheet.recordTask = "" } }
            }
            ErrorBanner { text: Maintenance.error }
        }

        // ------------------------------------------------------------ configuration
        Column {
            visible: !!sheet.d.isDrone || !!(sheet.d.installedOn && sheet.d.installedOn.tag)
            width: parent.width
            spacing: Theme.space.xs
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Heading { text: sheet.d.isDrone ? qsTr("Fitted parts") : qsTr("Fitted to") }

            Row {
                visible: !!(sheet.d.installedOn && sheet.d.installedOn.tag)
                spacing: Theme.space.sm
                Txt { anchors.verticalCenter: parent.verticalCenter; text: sheet.d.installedOn ? sheet.d.installedOn.tag + (sheet.d.installedOn.position ? "  ·  " + sheet.d.installedOn.position : "") : "" }
                AppButton { visible: Equipment.canMaintain; compact: true; text: qsTr("Remove from airframe"); onClicked: Equipment.removeComponent(sheet.d.assetId, "") }
            }

            Repeater {
                model: sheet.d.components || []
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
                        Txt { width: 100; text: modelData.position; muted: true }
                        Txt { width: 110; text: modelData.tag; variant: "bodyStrong" }
                        Txt { width: 240; text: modelData.itemType }
                    }
                    AppButton {
                        visible: Equipment.canMaintain
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        variant: "ghost"
                        text: qsTr("Remove")
                        onClicked: Equipment.removeComponent(modelData.assetId, "")
                    }
                }
            }
            Txt {
                visible: !!sheet.d.isDrone && (sheet.d.components || []).length === 0
                text: qsTr("No parts recorded on this airframe yet.")
                muted: true
            }
            Row {
                visible: !!sheet.d.isDrone && Equipment.canMaintain
                spacing: Theme.space.xs
                AppSelect {
                    id: loose
                    width: 300
                    model: sheet.d.looseComponents || []
                    textRole: "label"
                    valueRole: "value"
                    displayText: count === 0 ? qsTr("No loose parts to fit") : currentText
                }
                AppTextField { id: position; width: 150; placeholder: qsTr("Position, e.g. Motor 1") }
                AppButton {
                    text: qsTr("Fit part")
                    enabled: loose.count > 0
                    onClicked: { Equipment.installComponent(sheet.d.assetId, loose.currentValue, position.text); position.text = "" }
                }
            }
        }

        // ------------------------------------------------------------ documents
        Column {
            width: parent.width
            spacing: Theme.space.xs
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Heading { text: qsTr("Documents") }
            Repeater {
                model: sheet.d.documents || []
                delegate: Rectangle {
                    required property var modelData
                    width: parent.width
                    height: 42
                    radius: Theme.radius.sm
                    color: Theme.colors.element
                    Row {
                        x: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 180; text: modelData.kindLabel; variant: "bodyStrong" }
                        Txt { width: 170; text: modelData.reference; elide: Text.ElideRight }
                        Txt { width: 120; text: modelData.validUntil || "—"; muted: true }
                        StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: modelData.statusKind; text: modelData.statusLabel }
                        Icon { visible: modelData.hasFile; name: "layers"; size: 15; color: Theme.colors.textMuted; anchors.verticalCenter: parent.verticalCenter
                               ToolTip.visible: false }
                    }
                    AppButton {
                        visible: Equipment.canManage
                        anchors.right: parent.right
                        anchors.rightMargin: 4
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        variant: "ghost"
                        text: qsTr("Remove")
                        onClicked: Equipment.removeDocument(modelData.documentId, modelData.version)
                    }
                }
            }
            Txt { visible: (sheet.d.documents || []).length === 0; text: qsTr("No documents yet."); muted: true }

            Column {
                visible: Equipment.canManage
                width: parent.width
                spacing: Theme.space.xs
                topPadding: Theme.space.xs
                Row {
                    width: parent.width
                    spacing: Theme.space.sm
                    AppSelect { id: docKind; width: 200; model: sheet.d.documentKinds || []; textRole: "label"; valueRole: "value" }
                    AppTextField { id: docReference; width: 170; placeholder: qsTr("Number / reference") }
                    AppTextField { id: docIssuer; width: parent.width - 200 - 170 - parent.spacing * 2; placeholder: qsTr("Issued by") }
                }
                Row {
                    spacing: Theme.space.sm
                    AppDatePicker { id: docIssued; width: 170; placeholder: qsTr("Issued on") }
                    AppDatePicker { id: docValid; width: 170; placeholder: qsTr("Valid until") }
                    FileButton {
                        compact: true
                        iconName: "plus"
                        text: sheet.documentFile ? qsTr("Scan attached") : qsTr("Attach scan")
                        nameFilters: [qsTr("Document (*.pdf *.png *.jpg *.jpeg)")]
                        onChosen: function (url) { sheet.documentFile = url }
                    }
                    AppButton {
                        compact: true
                        variant: "primary"
                        text: qsTr("Add document")
                        onClicked: {
                            Equipment.addDocument(sheet.d.assetId, {
                                kind: docKind.currentValue, reference: docReference.text, issuer: docIssuer.text,
                                issuedOn: sheet.iso(docIssued), validUntil: sheet.iso(docValid)
                            }, sheet.documentFile)
                            docReference.text = ""; docIssuer.text = ""; docIssued.hasDate = false; docValid.hasDate = false
                            sheet.documentFile = ""
                        }
                    }
                }
            }
        }

        // ------------------------------------------------------------ firmware
        Column {
            visible: !!sheet.d.isDrone || (sheet.d.firmware || []).length > 0 || sheet.d.categoryLabel === "GNSS & controllers"
            width: parent.width
            spacing: Theme.space.xs
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Heading { text: qsTr("Firmware") }
            Repeater {
                model: sheet.d.firmware || []
                delegate: Row {
                    required property var modelData
                    required property int index
                    spacing: Theme.space.md
                    Txt { width: 160; text: modelData.version; variant: index === 0 ? "bodyStrong" : "body" }
                    Txt { width: 120; text: modelData.installedOn; muted: true }
                    Txt { text: modelData.note; muted: true }
                }
            }
            Row {
                visible: Equipment.canMaintain
                spacing: Theme.space.sm
                AppTextField { id: fwVersion; width: 170; placeholder: qsTr("Version, e.g. v04.02.0100") }
                AppDatePicker { id: fwDate; width: 170; placeholder: qsTr("Installed on") }
                AppTextField { id: fwNote; width: 220; placeholder: qsTr("Note") }
                AppButton {
                    text: qsTr("Record")
                    onClicked: { Equipment.recordFirmware(sheet.d.assetId, fwVersion.text, sheet.iso(fwDate), fwNote.text); fwVersion.text = ""; fwNote.text = "" }
                }
            }
        }

        // ------------------------------------------------------------ history
        Column {
            width: parent.width
            spacing: 4
            Rectangle { width: parent.width; height: 1; color: Theme.colors.divider }
            Heading { text: qsTr("Status history") }
            Repeater {
                model: sheet.d.history || []
                delegate: Row {
                    required property var modelData
                    spacing: Theme.space.md
                    Txt { width: 140; text: modelData.when; variant: "caption"; muted: true }
                    Txt { text: modelData.to; variant: "caption" }
                    Txt { text: modelData.reason ? "— " + modelData.reason : ""; variant: "caption"; muted: true }
                }
            }
            Txt { visible: (sheet.d.history || []).length === 0; text: qsTr("No changes yet: serviceable and in store since it was registered."); muted: true; variant: "caption" }
        }

        ErrorBanner { text: Equipment.error }
    }

    actions: [
        AppButton { text: qsTr("Close"); onClicked: sheet.close() }
    ]

    WorkOrderSheet { id: orderSheet }
}
