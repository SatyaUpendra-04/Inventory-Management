import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Dialogs
import "../components"

// The equipment register: search, filter, register, print labels, open an asset.
Item {
    id: view

    readonly property var columns: [0.22, 0.19, 0.14, 0.13, 0.11, 0.10, 0.11]

    Component.onCompleted: Equipment.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm

        AppTextField {
            width: 260
            placeholder: qsTr("Search tag, serial, make or model")
            iconName: "search"
            onTextChanged: Equipment.setSearch(text)
        }
        AppSelect {
            id: category
            width: 200
            model: Equipment.categoryOptions
            textRole: "label"
            valueRole: "value"
            onActivated: Equipment.setCategory(currentValue)
        }
        AppButton {
            visible: Equipment.attentionCount > 0 || Equipment.attentionOnly
            iconName: "alert"
            text: Equipment.attentionOnly ? qsTr("Showing %1 needing attention").arg(Equipment.count)
                                          : qsTr("%1 need attention").arg(Equipment.attentionCount)
            variant: Equipment.attentionOnly ? "primary" : "secondary"
            onClicked: Equipment.setAttentionOnly(!Equipment.attentionOnly)
        }
        Item {
            width: Math.max(0, toolbar.width - x - labelsButton.width - registerButton.width - Theme.space.sm * 2)
            height: 1
        }
        AppButton {
            id: labelsButton
            iconName: "layers"
            text: qsTr("Print labels")
            enabled: Equipment.count > 0
            onClicked: labelsSheet.open()
        }
        AppButton {
            id: registerButton
            visible: Equipment.canManage
            variant: "primary"
            iconName: "plus"
            text: qsTr("Register asset")
            onClicked: registerSheet.openNew()
        }
    }

    Card {
        x: Theme.space.xl
        anchors.top: toolbar.bottom
        anchors.topMargin: Theme.space.md
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        elevation: "low"
        radius: Theme.radius.md

        Row {
            id: headings
            x: Theme.space.md
            width: parent.width - Theme.space.md * 2
            height: 38
            Repeater {
                model: [qsTr("Asset"), qsTr("Serial · make"), qsTr("Home site"), qsTr("Condition"),
                        qsTr("Where"), qsTr("Usage"), qsTr("Documents")]
                delegate: Txt {
                    required property string modelData
                    required property int index
                    width: headings.width * view.columns[index]
                    height: 38
                    text: modelData
                    variant: "caption"
                    font.weight: Theme.type.semibold
                    muted: true
                }
            }
        }
        Rectangle { y: 38; width: parent.width; height: 1; color: Theme.colors.divider }

        ListView {
            id: list
            anchors.fill: parent
            anchors.topMargin: 39
            clip: true
            model: Equipment.model
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            delegate: AbstractButton {
                id: row
                required property var model
                width: list.width
                height: 54
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                leftPadding: Theme.space.md
                rightPadding: Theme.space.md
                Accessible.name: model.tag + " " + model.itemType
                onClicked: assetSheet.show(model.assetId)

                background: Rectangle {
                    color: row.hovered ? Theme.colors.element : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                }
                contentItem: Row {
                    width: row.availableWidth
                    readonly property real w: width
                    Column {
                        width: parent.w * view.columns[0]
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { text: row.model.tag; variant: "bodyStrong" }
                        Txt { width: parent.width - 8; text: row.model.itemType; variant: "caption"; muted: true; elide: Text.ElideRight }
                    }
                    Column {
                        width: parent.w * view.columns[1]
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { width: parent.width - 8; text: row.model.serial || "—"; muted: !row.model.serial; elide: Text.ElideRight }
                        Txt { width: parent.width - 8; text: row.model.makeModel; variant: "caption"; muted: true; elide: Text.ElideRight }
                    }
                    Txt { width: parent.w * view.columns[2]; height: row.height; text: row.model.site || "—"; muted: !row.model.site; elide: Text.ElideRight }
                    Item {
                        width: parent.w * view.columns[3]
                        height: row.height
                        StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: row.model.serviceKind; text: row.model.serviceLabel }
                    }
                    Column {
                        width: parent.w * view.columns[4]
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { text: row.model.custodyLabel }
                        Txt { visible: row.model.kitCode !== ""; text: row.model.kitCode; variant: "caption"; muted: true }
                    }
                    Txt { width: parent.w * view.columns[5]; height: row.height; text: row.model.meters || "—"; muted: !row.model.meters; variant: "caption"; font.features: { "tnum": 1 } }
                    Item {
                        width: parent.w * view.columns[6]
                        height: row.height
                        StatusPill {
                            visible: row.model.complianceKind !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            kind: row.model.complianceKind
                            text: row.model.complianceKind === "danger" ? qsTr("Action needed") : qsTr("Expiring")
                            ToolTip.visible: hoverArea.containsMouse
                            ToolTip.text: row.model.complianceText
                            MouseArea { id: hoverArea; anchors.fill: parent; hoverEnabled: true; acceptedButtons: Qt.NoButton }
                        }
                        Txt { visible: row.model.complianceKind === ""; anchors.verticalCenter: parent.verticalCenter; text: qsTr("In order"); variant: "caption"; muted: true }
                    }
                }
            }
        }

        EmptyState {
            visible: Equipment.count === 0
            anchors.centerIn: parent
            iconName: "drone"
            title: Equipment.total === 0 ? qsTr("No equipment registered yet") : qsTr("Nothing matches")
            message: Equipment.total === 0
                     ? qsTr("Register your drones, parts, batteries, DGPS receivers and accessories. Each gets a tag you can print as a QR label.")
                     : qsTr("Try a different search or category.")
            actionText: Equipment.total === 0 && Equipment.canManage ? qsTr("Register asset") : ""
            onAction: registerSheet.openNew()
        }
    }

    RegisterAssetSheet { id: registerSheet }
    AssetSheet { id: assetSheet; onEditRequested: function (detail) { registerSheet.openEdit(detail) } }

    Sheet {
        id: labelsSheet
        title: qsTr("Print QR labels")
        subtitle: qsTr("A4 sheets of 21 labels (63.5 × 38.1 mm). Labels are made for the %n assets listed now.", "", Equipment.count)

        Column {
            width: parent.width
            spacing: Theme.space.sm
            Txt { text: qsTr("Start at label position (1–21), to reuse a part-used sheet:"); variant: "caption" }
            AppTextField { id: startAt; width: 120; text: "1" }
        }
        actions: [
            AppButton { text: qsTr("Cancel"); onClicked: labelsSheet.close() },
            AppButton {
                variant: "primary"
                iconName: "layers"
                text: qsTr("Save PDF…")
                onClicked: saveDialog.open()
            }
        ]
        FileDialog {
            id: saveDialog
            title: qsTr("Save labels as PDF")
            fileMode: FileDialog.SaveFile
            nameFilters: [qsTr("PDF (*.pdf)")]
            defaultSuffix: "pdf"
            onAccepted: {
                Equipment.printLabels([], String(selectedFile), Math.max(0, (parseInt(startAt.text) || 1) - 1))
                labelsSheet.close()
            }
        }
    }
}
