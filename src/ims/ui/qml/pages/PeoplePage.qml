import QtQuick
import QtQuick.Controls.Basic
import "../components"

// People: pilots, surveyors and administrators (admin only).
Item {
    id: page

    property var section: ({})

    readonly property var columns: [0.30, 0.12, 0.13, 0.17, 0.14, 0.14]

    function licencePill(status) {
        return ({ valid: "success", expiring: "warning", expired: "danger" })[status] || "neutral"
    }
    function licenceText(row) {
        if (!row.licenceNumber) return ""
        if (row.licenceStatus === "expired") return qsTr("Expired %1").arg(row.licenceExpiry)
        if (row.licenceStatus === "expiring") return qsTr("Expires %1").arg(row.licenceExpiry)
        return qsTr("Valid to %1").arg(row.licenceExpiry)
    }

    Component.onCompleted: People.refresh()

    Row {
        id: toolbar
        x: Theme.space.xl
        y: Theme.space.lg
        width: parent.width - Theme.space.xl * 2
        spacing: Theme.space.sm

        AppTextField {
            width: 280
            placeholder: qsTr("Search name, username, employee ID")
            iconName: "search"
            onTextChanged: People.setFilterText(text)
        }
        SegmentedControl {
            segmentWidth: 92
            value: People.roleFilter
            options: [{ value: "", label: qsTr("Everyone") }, { value: "admin", label: qsTr("Admins") },
                      { value: "pilot", label: qsTr("Pilots") }, { value: "surveyor", label: qsTr("Surveyors") }]
            onActivated: function (v) { People.setRoleFilter(v) }
        }
        Item { width: toolbar.width - 280 - 372 - addButton.width - countLabel.width - Theme.space.sm * 4; height: 1 }
        Txt {
            id: countLabel
            anchors.verticalCenter: parent.verticalCenter
            text: People.count === People.total ? qsTr("%n people", "", People.total)
                                                : qsTr("%1 of %2").arg(People.count).arg(People.total)
            muted: true
            variant: "caption"
        }
        AppButton {
            id: addButton
            variant: "primary"
            iconName: "plus"
            text: qsTr("Add person")
            onClicked: personSheet.openNew()
        }
    }

    Card {
        id: listCard
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
                model: [qsTr("Person"), qsTr("Role"), qsTr("Employee ID"), qsTr("Contact"), qsTr("Licence"), qsTr("Account")]
                delegate: Txt {
                    required property string modelData
                    required property int index
                    width: headings.width * page.columns[index]
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
            model: People.model
            boundsBehavior: Flickable.StopAtBounds
            ScrollBar.vertical: ScrollBar {}

            add: Transition { NumberAnimation { property: "opacity"; from: 0; to: 1; duration: Theme.motion.standard } }

            delegate: AbstractButton {
                id: row
                required property var model
                width: list.width
                height: 62
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                leftPadding: Theme.space.md
                rightPadding: Theme.space.md
                Accessible.name: model.name
                onClicked: personSheet.openEdit(model.personId)

                background: Rectangle {
                    color: row.hovered ? Theme.colors.element : "transparent"
                    Behavior on color { ColorAnimation { duration: Theme.motion.micro } }
                    Rectangle { anchors.bottom: parent.bottom; width: parent.width; height: 1; color: Theme.colors.divider; opacity: 0.6 }
                    FocusRing { show: row.visualFocus; anchors.margins: 2; baseRadius: 4 }
                }

                contentItem: Row {
                    width: row.availableWidth
                    readonly property real w: width

                    Row {
                        width: parent.w * page.columns[0]
                        height: row.height
                        spacing: Theme.space.sm
                        Avatar {
                            size: 36
                            source: row.model.picture
                            initials: row.model.initials
                            anchors.verticalCenter: parent.verticalCenter
                        }
                        Column {
                            anchors.verticalCenter: parent.verticalCenter
                            width: parent.width - 48
                            Txt { width: parent.width; text: row.model.name + (row.model.isSelf ? qsTr("  (you)") : ""); variant: "bodyStrong"; elide: Text.ElideRight }
                            Txt { width: parent.width; text: "@" + row.model.username; variant: "caption"; muted: true; elide: Text.ElideRight }
                        }
                    }
                    Txt { width: parent.w * page.columns[1]; height: row.height; text: row.model.roleLabel }
                    Txt { width: parent.w * page.columns[2]; height: row.height; text: row.model.employeeId; font.features: { "tnum": 1 } }
                    Column {
                        width: parent.w * page.columns[3]
                        anchors.verticalCenter: parent.verticalCenter
                        Txt { width: parent.width - 8; text: row.model.email; elide: Text.ElideRight }
                        Txt { width: parent.width - 8; text: row.model.phone; variant: "caption"; muted: true }
                    }
                    Item {
                        width: parent.w * page.columns[4]
                        height: row.height
                        StatusPill {
                            visible: row.model.licenceNumber !== ""
                            anchors.verticalCenter: parent.verticalCenter
                            kind: page.licencePill(row.model.licenceStatus)
                            text: page.licenceText(row.model)
                        }
                        Txt { visible: row.model.licenceNumber === ""; anchors.verticalCenter: parent.verticalCenter; text: "—"; muted: true }
                    }
                    Item {
                        width: parent.w * page.columns[5]
                        height: row.height
                        StatusPill {
                            anchors.verticalCenter: parent.verticalCenter
                            kind: row.model.account
                            text: row.model.accountLabel
                        }
                    }
                }
            }
        }

        EmptyState {
            visible: People.count === 0
            anchors.centerIn: parent
            iconName: "users"
            title: People.total === 0 ? qsTr("No one here yet") : qsTr("No one matches")
            message: People.total === 0 ? qsTr("Add your pilots, surveyors and administrators. Each gets a temporary password to start with.")
                                        : qsTr("Try a different name or role.")
            actionText: People.total === 0 ? qsTr("Add person") : ""
            onAction: personSheet.openNew()
        }
    }

    PersonSheet { id: personSheet }
    TemporaryPasswordSheet { id: passwordSheet }

    Connections {
        target: People
        function onTemporaryPassword(name, username, password) { passwordSheet.show(name, username, password) }
    }
}
