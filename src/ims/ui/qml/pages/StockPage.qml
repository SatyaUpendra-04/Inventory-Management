import QtQuick
import QtQuick.Controls.Basic
import QtQuick.Layouts
import "../components"

// GCP banner stock: how many at each site, reorder alerts, receipts, write-offs, counts.
Item {
    id: page

    property var section: ({})
    readonly property var columns: [0.40, 0.18, 0.18, 0.24]

    Component.onCompleted: Stock.refresh()

    Item {
        id: summary
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        height: 92

        Row {
            spacing: Theme.space.md
            Card {
                width: 220
                height: 92
                padding: Theme.space.md
                Column {
                    spacing: 2
                    Txt { text: qsTr("%1s on hand").arg(Stock.itemName); variant: "caption"; muted: true }
                    Txt { text: Stock.total; variant: "title1"; font.features: { "tnum": 1 } }
                }
            }
            Card {
                width: 220
                height: 92
                padding: Theme.space.md
                Column {
                    spacing: 2
                    Txt { text: qsTr("Sites at or below reorder level"); variant: "caption"; muted: true }
                    Row {
                        spacing: Theme.space.xs
                        Txt { text: Stock.lowCount; variant: "title1"; color: Stock.lowCount > 0 ? Theme.colors.dangerText : Theme.colors.text }
                        StatusPill { visible: Stock.lowCount > 0; anchors.verticalCenter: parent.verticalCenter; kind: "danger"; text: qsTr("Reorder") }
                    }
                }
            }
        }
        Row {
            visible: Stock.canManage
            anchors.right: parent.right
            anchors.top: parent.top
            spacing: Theme.space.xs
            AppButton { iconName: "bell"; text: qsTr("Reorder level"); onClicked: actionSheet.start("level") }
            AppButton { iconName: "minus"; text: qsTr("Write off"); onClicked: actionSheet.start("writeOff") }
            AppButton { iconName: "check"; text: qsTr("Stock count"); onClicked: actionSheet.start("count") }
            AppButton { variant: "primary"; iconName: "plus"; text: qsTr("Receive"); onClicked: actionSheet.start("receive") }
        }
    }

    Card {
        id: sitesCard
        x: Theme.space.xl
        anchors.top: summary.bottom
        anchors.topMargin: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        height: siteRows.count > 0 ? 39 + siteRows.count * 46 + 2 : 39 + emptySites.height + Theme.space.lg * 2
        elevation: "low"
        radius: Theme.radius.md

        Row {
            id: headings
            x: Theme.space.md
            width: parent.width - Theme.space.md * 2
            height: 38
            Repeater {
                model: [qsTr("Site"), qsTr("On hand"), qsTr("Reorder level"), qsTr("Status")]
                delegate: Txt {
                    required property string modelData
                    required property int index
                    width: headings.width * page.columns[index]
                    height: 38
                    text: modelData
                    variant: "caption"
                    font.weight: Theme.type.semibold
                    muted: true
                    horizontalAlignment: index === 1 || index === 2 ? Text.AlignRight : Text.AlignLeft
                    rightPadding: index === 1 || index === 2 ? Theme.space.lg : 0
                }
            }
        }
        Rectangle { y: 38; width: parent.width; height: 1; color: Theme.colors.divider }
        Column {
            y: 39
            x: Theme.space.md
            width: parent.width - Theme.space.md * 2
            Repeater {
                id: siteRows
                model: Stock.sites
                delegate: Item {
                    required property var model
                    width: parent.width
                    height: 46
                    Row {
                        anchors.fill: parent
                        Txt { width: parent.width * page.columns[0]; height: 46; text: model.site; elide: Text.ElideRight }
                        Txt { width: parent.width * page.columns[1]; height: 46; text: model.onHand; variant: "bodyStrong"; horizontalAlignment: Text.AlignRight; rightPadding: Theme.space.lg; font.features: { "tnum": 1 } }
                        Txt { width: parent.width * page.columns[2]; height: 46; text: model.level || "—"; muted: !model.level; horizontalAlignment: Text.AlignRight; rightPadding: Theme.space.lg; font.features: { "tnum": 1 } }
                        Item { width: parent.width * page.columns[3]; height: 46
                               StatusPill { anchors.verticalCenter: parent.verticalCenter; kind: model.statusKind; text: model.statusLabel } }
                    }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                }
            }
        }
        EmptyState {
            id: emptySites
            visible: siteRows.count === 0
            anchors.horizontalCenter: parent.horizontalCenter
            y: 39 + Theme.space.lg
            iconName: "flag"
            title: qsTr("No GCP banners recorded yet")
            message: Stock.canManage ? qsTr("Record a delivery with Receive. Sites must exist first (Organisation → Sites).")
                                     : qsTr("An administrator records deliveries here.")
        }
    }

    Card {
        x: Theme.space.xl
        anchors.top: sitesCard.bottom
        anchors.topMargin: Theme.space.lg
        anchors.bottom: parent.bottom
        anchors.bottomMargin: Theme.space.xl
        width: parent.width - Theme.space.xl * 2
        elevation: "low"
        radius: Theme.radius.md
        padding: Theme.space.md

        Txt { id: movesTitle; text: qsTr("Recent movements"); variant: "headline" }
        ListView {
            id: moves
            anchors.fill: parent
            anchors.topMargin: movesTitle.height + Theme.space.sm
            clip: true
            model: Stock.movements
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}
            delegate: Row {
                required property var model
                height: 30
                spacing: Theme.space.md
                Txt { width: 140; height: 30; text: model.when; variant: "caption"; muted: true }
                Txt { width: 160; height: 30; text: model.kind }
                Txt { width: 110; height: 30; text: model.site; muted: true }
                Txt { width: 60; height: 30; text: model.quantity; variant: "bodyStrong"; horizontalAlignment: Text.AlignRight; font.features: { "tnum": 1 } }
                Txt { width: 280; height: 30; text: model.reason; muted: true; elide: Text.ElideRight }
                Txt { height: 30; text: model.by; variant: "caption"; muted: true }
            }
            Txt { visible: moves.count === 0; text: qsTr("Nothing yet."); muted: true }
        }
    }

    Sheet {
        id: actionSheet
        property string mode: "receive"
        readonly property var texts: ({
            receive: [qsTr("Receive GCP banners"), qsTr("Record a delivery into a site's store."), qsTr("Quantity received"), qsTr("Supplier or delivery note")],
            writeOff: [qsTr("Write off GCP banners"), qsTr("Banners lost or damaged while in store."), qsTr("Quantity"), qsTr("Reason (required)")],
            count: [qsTr("Stock count"), qsTr("Enter what you counted; any difference from the records is adjusted and logged."), qsTr("Quantity counted"), qsTr("Note")],
            level: [qsTr("Reorder level"), qsTr("Alert when this site has this many banners or fewer."), qsTr("Reorder level"), ""]
        })
        width: 480
        title: texts[mode][0]
        subtitle: texts[mode][1]

        function start(newMode) {
            mode = newMode
            Stock.clearError()
            quantity.text = ""
            note.text = ""
            open()
        }

        Connections { target: Stock; function onSaved() { if (actionSheet.opened) actionSheet.close() } }

        Column {
            width: parent.width
            spacing: Theme.space.md
            Column {
                width: parent.width
                spacing: 6
                Txt { text: qsTr("Site"); variant: "caption"; font.weight: Theme.type.medium }
                AppSelect { id: siteSelect; width: parent.width; model: actionSheet.opened ? Stock.siteChoices() : []; textRole: "label"; valueRole: "value" }
            }
            AppTextField { id: quantity; width: 180; label: actionSheet.texts[actionSheet.mode][2] }
            AppTextField { id: note; visible: actionSheet.mode !== "level"; width: parent.width; label: actionSheet.texts[actionSheet.mode][3] }
            ErrorBanner { text: Stock.error }
        }
        actions: [
            AppButton { text: qsTr("Cancel"); onClicked: actionSheet.close() },
            AppButton {
                variant: "primary"
                text: qsTr("Save")
                enabled: siteSelect.count > 0 && !Tasks.busy
                busy: Tasks.busy
                onClicked: {
                    var site = siteSelect.currentValue
                    if (actionSheet.mode === "receive") Stock.receive(site, quantity.text, note.text)
                    else if (actionSheet.mode === "writeOff") Stock.writeOff(site, quantity.text, note.text)
                    else if (actionSheet.mode === "count") Stock.count(site, quantity.text, note.text)
                    else Stock.setReorderLevel(site, quantity.text)
                }
            }
        ]
    }
}
