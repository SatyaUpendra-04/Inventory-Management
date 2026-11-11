import QtQuick
import QtQuick.Controls.Basic
import "../components"

// One project: crew, totals, deployments, flight and survey logs.
Sheet {
    id: sheet

    readonly property var d: Projects.detail
    readonly property bool loaded: d.projectId !== undefined
    readonly property var t: d.totals || ({})
    property string voiding: ""   // "sortie:<id>" or "session:<id>" while asking for a reason

    signal editRequested(var detail)

    width: Math.min(900, parent ? parent.width - 64 : 900)
    title: loaded ? d.code + "  ·  " + d.name : qsTr("Loading…")
    subtitle: loaded ? [d.site, d.dates, d.client].filter(function (s) { return s }).join("  ·  ") : ""

    function show(projectId) {
        Projects.clearError()
        voiding = ""
        Projects.openProject(projectId)
        open()
    }
    onClosed: Projects.closeProject()

    component Heading: Txt { variant: "headline"; topPadding: Theme.space.xs }
    component Field: Column {
        property string label: ""
        property string value: ""
        width: 160
        spacing: 2
        Txt { text: parent.label; variant: "caption"; muted: true }
        Txt { text: parent.value || "—"; muted: !parent.value; width: parent.width; elide: Text.ElideRight; font.features: { "tnum": 1 } }
    }
    component Divider: Rectangle { width: parent ? parent.width : 0; height: 1; color: Theme.colors.divider }

    Column {
        width: parent.width
        spacing: Theme.space.md
        visible: sheet.loaded

        // ------------------------------------------------------------ status and crew
        Row {
            spacing: Theme.space.xs
            StatusPill { kind: sheet.d.statusKind || "neutral"; text: sheet.d.statusLabel || "" }
            StatusPill { visible: (sheet.t.openDeployments || 0) > 0; kind: "info"
                         text: qsTr("%n deployment(s) out", "", sheet.t.openDeployments || 0) }
        }
        Flow {
            width: parent.width
            spacing: Theme.space.lg
            Field {
                visible: !!sheet.d.myRole
                width: 300
                label: qsTr("Your part")
                value: sheet.d.myRole ? sheet.d.myRole + (sheet.d.myWork ? "  ·  " + sheet.d.myWork : "") : ""
            }
            Field { label: qsTr("Chief pilot"); value: sheet.d.chiefPilot ? sheet.d.chiefPilot + "  ·  " + sheet.d.chiefPilotLicence : "" ; width: 260 }
            Field { label: qsTr("Lead surveyor"); value: sheet.d.surveyor || "" }
            Field { label: qsTr("Flights"); value: sheet.t.flights ? sheet.t.flights + "  ·  " + sheet.t.flightTime : "" }
            Field { label: qsTr("Survey sessions"); value: sheet.t.sessions ? sheet.t.sessions + "  ·  " + sheet.t.surveyTime : "" }
            Field { label: qsTr("Area surveyed"); value: sheet.t.area && sheet.t.area !== "—" ? sheet.t.area : "" }
            Field { label: qsTr("Points"); value: sheet.t.points ? String(sheet.t.points) : "" }
            Field {
                label: qsTr("GCP banners")
                width: 260
                value: sheet.t.gcpIssued ? qsTr("%1 issued · %2 back · %3 used").arg(sheet.t.gcpIssued)
                                             .arg(sheet.t.gcpReturned).arg(sheet.t.gcpConsumed) : ""
            }
        }
        Txt { visible: !!sheet.d.notes; width: parent.width; text: sheet.d.notes || ""; muted: true; wrapMode: Text.WordWrap }

        Row {
            visible: Projects.canManage
            spacing: Theme.space.xs
            Repeater {
                model: sheet.d.statusActions || []
                delegate: AppButton {
                    required property var modelData
                    compact: true
                    text: modelData.label
                    variant: modelData.value === "cancelled" ? "ghost" : "secondary"
                    onClicked: Projects.setStatus(sheet.d.projectId, sheet.d.version, modelData.value)
                }
            }
            AppButton { compact: true; variant: "ghost"; iconName: "sliders"; text: qsTr("Edit details")
                        onClicked: sheet.editRequested(sheet.d) }
            AppButton { visible: !!sheet.d.canRemove; compact: true; variant: "ghost"; iconName: "x"; text: qsTr("Remove")
                        onClicked: { Projects.remove(sheet.d.projectId, sheet.d.version); sheet.close() } }
        }

        Divider {}

        // ------------------------------------------------------------ reservations
        Item {
            width: parent.width
            height: bookHeading.height
            Heading { id: bookHeading; text: qsTr("Reservations") }
            AppButton {
                visible: Reservations.canRequest && !!sheet.d.isOpen
                anchors.right: parent.right
                compact: true
                iconName: "calendar"
                text: qsTr("Reserve equipment")
                onClicked: reservationSheet.openNew(sheet.d.projectId)
            }
        }
        Txt { visible: (sheet.d.reservations || []).length === 0; text: qsTr("Nothing reserved for this project."); muted: true }
        Repeater {
            model: sheet.d.reservations || []
            delegate: AbstractButton {
                id: booking
                required property var modelData
                width: parent.width
                height: 36
                hoverEnabled: true
                focusPolicy: Qt.StrongFocus
                Accessible.name: modelData.dates
                onClicked: reservationSheet.show(modelData.reservationId)
                background: Rectangle {
                    radius: Theme.radius.sm
                    color: booking.hovered ? Theme.colors.elementHover : Theme.colors.element
                    FocusRing { show: booking.visualFocus }
                }
                contentItem: Item {
                    Row {
                        x: Theme.space.sm
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 120; text: booking.modelData.dates; variant: "bodyStrong" }
                        Txt { width: 420; elide: Text.ElideRight; muted: true
                              text: booking.modelData.items + (booking.modelData.gcp ? qsTr("  ·  %1 GCP").arg(booking.modelData.gcp) : "") }
                    }
                    StatusPill { anchors.right: parent.right; anchors.rightMargin: Theme.space.sm; anchors.verticalCenter: parent.verticalCenter
                                 kind: booking.modelData.statusKind; text: booking.modelData.statusLabel }
                }
            }
        }

        Divider {}

        // ------------------------------------------------------------ deployments
        Item {
            width: parent.width
            height: deployHeading.height
            Heading { id: deployHeading; text: qsTr("Equipment out") }
            AppButton {
                visible: Deployments.canDeploy && !!sheet.d.isOpen
                anchors.right: parent.right
                compact: true
                variant: "primary"
                iconName: "send"
                text: qsTr("Check out equipment")
                onClicked: checkout.openFor(sheet.d.projectId)
            }
        }
        Txt { visible: (sheet.d.deployments || []).length === 0; text: qsTr("Nothing has gone out on this project yet."); muted: true }
        Repeater {
            model: sheet.d.deployments || []
            delegate: Rectangle {
                required property var modelData
                width: parent.width
                height: dRow.implicitHeight + Theme.space.sm * 2
                radius: Theme.radius.sm
                color: Theme.colors.element
                Column {
                    id: dRow
                    x: Theme.space.sm
                    y: Theme.space.sm
                    width: parent.width - Theme.space.sm * 2 - returnButton.width
                    spacing: 2
                    Row {
                        spacing: Theme.space.sm
                        Txt { text: modelData.label; variant: "bodyStrong" }
                        StatusPill { kind: modelData.stateKind; text: modelData.stateLabel }
                    }
                    Txt { width: parent.width; text: qsTr("%n item(s): ", "", modelData.itemCount) + modelData.items; muted: true; elide: Text.ElideRight; variant: "caption" }
                    Txt { width: parent.width; text: qsTr("Crew: ") + modelData.crew + (modelData.gcp ? qsTr("  ·  %1 GCP banners").arg(modelData.gcp) : ""); muted: true; variant: "caption" }
                    Txt { visible: !!modelData.failure; width: parent.width; text: modelData.failure; color: Theme.colors.dangerText; variant: "caption"; wrapMode: Text.WordWrap }
                }
                AppButton {
                    id: returnButton
                    anchors.right: parent.right
                    anchors.rightMargin: Theme.space.sm
                    anchors.verticalCenter: parent.verticalCenter
                    compact: true
                    text: modelData.canReturn && Deployments.canReturn ? qsTr("Return…") : qsTr("View")
                    onClicked: returnSheet.show(modelData.deploymentId)
                }
            }
        }

        Divider {}

        // ------------------------------------------------------------ flights
        Item {
            width: parent.width
            height: flightHeading.height
            Heading { id: flightHeading; text: qsTr("Flights") }
            AppButton {
                visible: Projects.canLog && (sheet.d.loggable || []).length > 0
                anchors.right: parent.right
                compact: true
                iconName: "plus"
                text: qsTr("Log flight")
                onClicked: sortieSheet.start(sheet.d.loggable)
            }
        }
        Txt {
            visible: (sheet.d.sorties || []).length === 0
            text: (sheet.d.loggable || []).length ? qsTr("No flights logged yet.") : qsTr("Flights can be logged once equipment has gone out.")
            muted: true
        }
        Repeater {
            model: sheet.d.sorties || []
            delegate: Column {
                required property var modelData
                width: parent.width
                spacing: 4
                Item {
                    width: parent.width
                    height: 34
                    opacity: modelData.void ? 0.55 : 1
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 96; text: modelData.when; variant: "caption"; muted: true }
                        Txt { width: 84; text: modelData.drone; variant: "bodyStrong"; font.strikeout: modelData.void }
                        Txt { width: 130; text: modelData.pilot; elide: Text.ElideRight }
                        Txt { width: 90; text: modelData.time; font.features: { "tnum": 1 } }
                        Txt { width: 200; text: [modelData.batteries, modelData.media].filter(function (s) { return s }).join("  ·  ") || "—"; muted: true; variant: "caption"; elide: Text.ElideRight }
                        Txt { visible: modelData.void; text: qsTr("Cancelled: %1").arg(modelData.voidReason); color: Theme.colors.dangerText; variant: "caption" }
                    }
                    AppButton {
                        visible: Projects.canCorrect && !modelData.void && sheet.voiding !== "sortie:" + modelData.sortieId
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        variant: "ghost"
                        text: qsTr("Cancel log…")
                        onClicked: { sheet.voiding = "sortie:" + modelData.sortieId; voidReason.text = "" }
                    }
                }
                Row {
                    visible: sheet.voiding === "sortie:" + modelData.sortieId
                    spacing: Theme.space.xs
                    AppTextField { id: voidReason; width: 320; placeholder: qsTr("Why is this log wrong?") }
                    AppButton { compact: true; text: qsTr("Keep"); onClicked: sheet.voiding = "" }
                    AppButton { compact: true; variant: "danger"; text: qsTr("Cancel log")
                                onClicked: { Projects.voidSortie(modelData.sortieId, modelData.version, voidReason.text); sheet.voiding = "" } }
                }
            }
        }

        Divider {}

        // ------------------------------------------------------------ survey sessions
        Item {
            width: parent.width
            height: surveyHeading.height
            Heading { id: surveyHeading; text: qsTr("Survey sessions") }
            AppButton {
                visible: Projects.canLog && (sheet.d.loggable || []).length > 0
                anchors.right: parent.right
                compact: true
                iconName: "plus"
                text: qsTr("Log survey")
                onClicked: surveySheet.start(sheet.d.loggable)
            }
        }
        Txt { visible: (sheet.d.sessions || []).length === 0; text: qsTr("No survey sessions logged yet."); muted: true }
        Repeater {
            model: sheet.d.sessions || []
            delegate: Column {
                required property var modelData
                width: parent.width
                spacing: 4
                Item {
                    width: parent.width
                    height: 34
                    opacity: modelData.void ? 0.55 : 1
                    Row {
                        anchors.verticalCenter: parent.verticalCenter
                        spacing: Theme.space.md
                        Txt { width: 96; text: modelData.when; variant: "caption"; muted: true }
                        Txt { width: 54; text: modelData.mode; variant: "bodyStrong"; font.strikeout: modelData.void }
                        Txt { width: 200; text: qsTr("Base %1 · rovers %2").arg(modelData.base).arg(modelData.rovers); elide: Text.ElideRight }
                        Txt { width: 90; text: modelData.time; font.features: { "tnum": 1 } }
                        Txt { width: 200; text: [modelData.area, modelData.points ? qsTr("%1 points").arg(modelData.points) : "", modelData.fixRate ? qsTr("%1 fixed").arg(modelData.fixRate) : ""].filter(function (s) { return s }).join("  ·  ") || "—"; muted: true; variant: "caption"; elide: Text.ElideRight }
                        Txt { visible: modelData.void; text: qsTr("Cancelled: %1").arg(modelData.voidReason); color: Theme.colors.dangerText; variant: "caption" }
                    }
                    AppButton {
                        visible: Projects.canCorrect && !modelData.void && sheet.voiding !== "session:" + modelData.sessionId
                        anchors.right: parent.right
                        anchors.verticalCenter: parent.verticalCenter
                        compact: true
                        variant: "ghost"
                        text: qsTr("Cancel log…")
                        onClicked: { sheet.voiding = "session:" + modelData.sessionId; sessionReason.text = "" }
                    }
                }
                Row {
                    visible: sheet.voiding === "session:" + modelData.sessionId
                    spacing: Theme.space.xs
                    AppTextField { id: sessionReason; width: 320; placeholder: qsTr("Why is this log wrong?") }
                    AppButton { compact: true; text: qsTr("Keep"); onClicked: sheet.voiding = "" }
                    AppButton { compact: true; variant: "danger"; text: qsTr("Cancel log")
                                onClicked: { Projects.voidSession(modelData.sessionId, modelData.version, sessionReason.text); sheet.voiding = "" } }
                }
            }
        }

        ErrorBanner { text: Projects.error }
    }

    actions: [ AppButton { text: qsTr("Close"); onClicked: sheet.close() } ]

    CheckoutSheet { id: checkout }
    ReservationSheet { id: reservationSheet }
    ReturnSheet { id: returnSheet }
    SortieSheet { id: sortieSheet }
    SurveySheet { id: surveySheet }
}
