import QtQuick
import QtQuick.Controls.Basic

// Sortable, selectable table. The model provides roles: display, kind ("text" |
// "number" | "status") and status (a StatusPill kind), plus a sortBy(column, descending) slot.
Item {
    id: root

    property var model
    property var columnWidths: []
    property var rightAligned: []  // column indexes with numbers
    property int sortColumn: -1
    property bool sortDescending: false
    property int hoveredRow: -1
    property int selectedRow: -1

    implicitHeight: header.height + table.contentHeight + 2

    function widthOf(column) {
        return root.columnWidths[column] !== undefined ? root.columnWidths[column] : 140
    }

    Rectangle {
        anchors.fill: parent
        radius: Theme.radius.md
        color: Theme.colors.surface
        border.width: 1
        border.color: Theme.colors.divider
    }

    HorizontalHeaderView {
        id: header
        syncView: table
        anchors.left: table.left
        anchors.top: parent.top
        anchors.topMargin: 1
        clip: true

        delegate: AbstractButton {
            id: headerCell
            required property int index
            required property var model
            readonly property string label: model.display
            implicitHeight: 36
            implicitWidth: root.widthOf(index)
            hoverEnabled: true
            focusPolicy: Qt.NoFocus
            Accessible.name: label
            onClicked: {
                if (root.sortColumn === index) root.sortDescending = !root.sortDescending
                else { root.sortColumn = index; root.sortDescending = false }
                root.model.sortBy(index, root.sortDescending)
            }

            contentItem: Item {
              Row {
                anchors.verticalCenter: parent.verticalCenter
                x: root.rightAligned.indexOf(headerCell.index) >= 0 ? parent.width - width - Theme.space.md
                                                                      : Theme.space.md
                spacing: 4
                Txt {
                    text: headerCell.label
                    variant: "caption"
                    font.weight: Theme.type.semibold
                    color: root.sortColumn === headerCell.index ? Theme.colors.text : Theme.colors.textMuted
                    anchors.verticalCenter: parent.verticalCenter
                }
                Icon {
                    visible: root.sortColumn === headerCell.index
                    name: root.sortDescending ? "arrow-down" : "arrow-up"
                    size: 13
                    color: Theme.colors.text
                    anchors.verticalCenter: parent.verticalCenter
                }
              }
            }
            background: Rectangle {
                color: headerCell.hovered ? Theme.colors.element : "transparent"
                Rectangle {
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: 1
                    color: Theme.colors.divider
                }
            }
        }
    }

    TableView {
        id: table
        anchors.fill: parent
        anchors.topMargin: header.height + 1
        anchors.margins: 1
        clip: true
        model: root.model
        boundsBehavior: Flickable.StopAtBounds
        columnWidthProvider: function (column) { return root.widthOf(column) }
        rowHeightProvider: function () { return 42 }
        ScrollBar.vertical: ScrollBar {}

        delegate: Rectangle {
            id: cell
            required property int row
            required property int column
            required property string display
            required property string kind
            required property string status

            implicitHeight: 42
            color: root.selectedRow === row ? Theme.colors.accentSubtle
                 : root.hoveredRow === row ? Theme.colors.element : "transparent"
            Behavior on color { ColorAnimation { duration: Theme.motion.micro } }

            Rectangle {
                anchors.bottom: parent.bottom
                width: parent.width
                height: 1
                color: Theme.colors.divider
                opacity: 0.6
            }

            Txt {
                visible: cell.kind !== "status"
                anchors.fill: parent
                anchors.leftMargin: Theme.space.md
                anchors.rightMargin: Theme.space.md
                text: cell.display
                elide: Text.ElideRight
                horizontalAlignment: cell.kind === "number" ? Text.AlignRight : Text.AlignLeft
                font.features: { "tnum": 1 }
                font.weight: cell.column === 0 ? Theme.type.medium : Theme.type.regular
            }

            StatusPill {
                visible: cell.kind === "status"
                anchors.left: parent.left
                anchors.leftMargin: Theme.space.md
                anchors.verticalCenter: parent.verticalCenter
                kind: cell.status || "neutral"
                text: cell.display
            }

            HoverHandler {
                onHoveredChanged: {
                    if (hovered) root.hoveredRow = cell.row
                    else if (root.hoveredRow === cell.row) root.hoveredRow = -1
                }
            }
            TapHandler { onTapped: root.selectedRow = cell.row }
        }
    }
}
