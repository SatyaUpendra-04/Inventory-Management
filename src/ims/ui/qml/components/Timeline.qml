import QtQuick
import QtQuick.Controls.Basic

// A planning calendar: one row per item (or project), one column per day, and a bar for
// every booking. Booked bars are solid accent, requests are outlined in amber, equipment
// that is out is solid slate; today's column is tinted.
//   days: [{ label, weekday, month, today, weekend }]
//   rows: [{ label, detail, bars: [{ start, span, kind, label, tip, reservationId, deploymentId }] }]
Item {
    id: root

    property var days: []
    property var rows: []
    property real labelWidth: 200
    property real rowHeight: 40
    property string emptyText: qsTr("Nothing booked in these weeks.")
    readonly property real dayWidth: Math.max(18, (width - labelWidth) / Math.max(1, days.length))

    signal barClicked(string reservationId, string deploymentId)

    function fill(kind) {
        return kind === "approved" ? Theme.colors.accent
             : kind === "out" ? Theme.colors.neutralSolid
             : Theme.colors.warningBg
    }
    function ink(kind) {
        return kind === "approved" ? Theme.colors.onAccent
             : kind === "out" ? Theme.colors.neutralOnSolid
             : Theme.colors.warningText
    }

    // ------------------------------------------------------------ header
    Item {
        id: header
        width: parent.width
        height: 44
        Repeater {
            model: root.days
            delegate: Item {
                required property var modelData
                required property int index
                x: root.labelWidth + index * root.dayWidth
                width: root.dayWidth
                height: header.height
                Rectangle {
                    anchors.fill: parent
                    anchors.topMargin: 2
                    radius: Theme.radius.sm
                    color: modelData.today ? Theme.colors.accentSubtle : "transparent"
                }
                Column {
                    anchors.centerIn: parent
                    Txt {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.month || modelData.weekday
                        variant: "caption"
                        font.weight: modelData.month ? Theme.type.semibold : Theme.type.regular
                        color: modelData.today ? Theme.colors.accentText : Theme.colors.textMuted
                    }
                    Txt {
                        anchors.horizontalCenter: parent.horizontalCenter
                        text: modelData.label
                        variant: modelData.today ? "bodyStrong" : "body"
                        color: modelData.today ? Theme.colors.accentText
                             : modelData.weekend ? Theme.colors.textMuted : Theme.colors.text
                        font.features: { "tnum": 1 }
                    }
                }
            }
        }
        Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider }
    }

    // ------------------------------------------------------------ rows
    ListView {
        id: list
        anchors.top: header.bottom
        anchors.bottom: parent.bottom
        width: parent.width
        clip: true
        boundsBehavior: Flickable.StopAtBounds
        model: root.rows
        ScrollBar.vertical: ScrollBar {}

        // Weekend shading and today's line behind every row.
        Repeater {
            model: root.days
            delegate: Rectangle {
                required property var modelData
                required property int index
                parent: list.contentItem
                x: root.labelWidth + index * root.dayWidth
                y: 0
                z: -1
                width: root.dayWidth
                height: Math.max(list.height, list.contentHeight)
                color: modelData.today ? Theme.colors.accentSubtle
                     : modelData.weekend ? Theme.colors.element : "transparent"
                opacity: modelData.today ? 0.7 : 0.5
            }
        }

        delegate: Item {
            id: row
            required property var modelData
            width: list.width
            height: root.rowHeight

            Column {
                x: Theme.space.sm
                width: root.labelWidth - Theme.space.md
                anchors.verticalCenter: parent.verticalCenter
                Txt { width: parent.width; text: row.modelData.label; variant: "bodyStrong"; elide: Text.ElideRight }
                Txt { width: parent.width; visible: !!row.modelData.detail; text: row.modelData.detail || ""
                      variant: "caption"; muted: true; elide: Text.ElideRight }
            }
            Repeater {
                model: row.modelData.bars
                delegate: AbstractButton {
                    id: bar
                    required property var modelData
                    x: root.labelWidth + modelData.start * root.dayWidth + 2
                    width: modelData.span * root.dayWidth - 4
                    height: root.rowHeight - 14
                    anchors.verticalCenter: parent.verticalCenter
                    hoverEnabled: true
                    focusPolicy: Qt.StrongFocus
                    Accessible.name: modelData.tip
                    ToolTip.visible: hovered
                    ToolTip.delay: 300
                    ToolTip.text: modelData.tip
                    onClicked: root.barClicked(modelData.reservationId, modelData.deploymentId)
                    background: Rectangle {
                        radius: height / 2
                        color: root.fill(bar.modelData.kind)
                        border.width: bar.modelData.kind === "requested" ? 1 : 0
                        border.color: Theme.colors.warningBorder
                        opacity: bar.hovered ? 0.88 : 1
                        FocusRing { show: bar.visualFocus; baseRadius: parent.radius }
                    }
                    contentItem: Txt {
                        leftPadding: Theme.space.sm
                        rightPadding: Theme.space.sm
                        text: bar.modelData.label
                        variant: "caption"
                        font.weight: Theme.type.semibold
                        color: root.ink(bar.modelData.kind)
                        elide: Text.ElideRight
                    }
                }
            }
            Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.5 }
        }
    }

    Txt {
        visible: root.rows.length === 0
        anchors.centerIn: list
        text: root.emptyText
        muted: true
    }
}
