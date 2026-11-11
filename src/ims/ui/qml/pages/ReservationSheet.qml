import QtQuick
import QtQuick.Controls.Basic
import "../components"

// Request a reservation (with a live conflict check), or review one: approve, reject,
// cancel, or check the equipment out when the crew leaves.
Sheet {
    id: sheet

    property bool isNew: true
    property string presetProject: ""
    property string deciding: ""   // "approve" | "reject" | "cancel" while asking for a note
    readonly property var c: Deployments.choices
    readonly property var r: Reservations.conflicts
    readonly property var d: Reservations.detail
    readonly property bool loaded: !isNew && d.reservationId !== undefined
    readonly property var live: isNew ? r : (d.conflicts || ({}))

    width: Math.min(820, parent ? parent.width - 64 : 820)
    title: isNew ? qsTr("Reserve equipment") : (loaded ? qsTr("Reservation") : qsTr("Loading…"))
    subtitle: isNew ? (Reservations.canApprove ? qsTr("As an administrator, your booking is confirmed straight away.")
                                               : qsTr("An administrator approves the request; approved bookings cannot be double-booked."))
                    : (loaded ? sheet.d.project + "  ·  " + sheet.d.dates : "")

    function iso(picker) { return picker.hasDate ? Qt.formatDate(picker.selectedDate, "yyyy-MM-dd") : "" }
    function values() {
        return {
            projectId: project.currentValue || "", startsOn: iso(starts), endsOn: iso(ends),
            kitIds: kits.selected, assetIds: equipment.selected,
            gcpQuantity: gcpStore.currentValue ? gcp.text : "0", gcpSiteId: gcpStore.currentValue || "",
            notes: notes.text
        }
    }
    function recheck() { if (sheet.opened && sheet.isNew) checkTimer.restart() }

    function openNew(projectId) {
        isNew = true
        deciding = ""
        presetProject = projectId || ""
        Reservations.clearError()
        Deployments.loadChoices()
        kits.selected = []; equipment.selected = []
        gcp.text = ""; notes.text = ""; search.text = ""
        var start = new Date(); start.setDate(start.getDate() + 1)
        var end = new Date(); end.setDate(end.getDate() + 5)
        starts.hasDate = true; starts.selectedDate = start
        ends.hasDate = true; ends.selectedDate = end
        open()
    }
    function show(reservationId) {
        isNew = false
        deciding = ""
        Reservations.clearError()
        Reservations.openReservation(reservationId)
        Deployments.loadChoices()
        open()
    }
    onClosed: if (!isNew) Reservations.closeReservation()
    onCChanged: { if (isNew && presetProject) project.selectValue(presetProject); recheck() }

    Timer { id: checkTimer; interval: 250; onTriggered: Reservations.check(sheet.values()) }
    Connections {
        target: Reservations
        function onSaved() { if (sheet.opened && sheet.isNew) sheet.close(); sheet.deciding = "" }
    }

    component Label: Txt { variant: "caption"; font.weight: Theme.type.medium }

    Column {
        width: parent.width
        spacing: Theme.space.md

        // ============================================================ new request
        Column {
            visible: sheet.isNew
            width: parent.width
            spacing: Theme.space.md

            Column {
                width: parent.width
                spacing: 6
                Label { text: qsTr("Project") }
                AppSelect {
                    id: project
                    width: parent.width
                    model: sheet.c.projects || []
                    textRole: "label"
                    valueRole: "value"
                    displayText: count === 0 ? qsTr("No open projects") : currentText
                }
            }
            Row {
                spacing: Theme.space.md
                AppDatePicker { id: starts; width: 200; label: qsTr("First day"); onPicked: sheet.recheck() }
                AppDatePicker { id: ends; width: 200; label: qsTr("Last day"); onPicked: sheet.recheck() }
            }
            Column {
                width: parent.width
                spacing: 6
                Label { text: qsTr("Kits (everything in the kit is booked)") }
                CheckList { id: kits; width: parent.width; maxHeight: 130; model: sheet.c.kits || []
                            emptyText: qsTr("No kits set up."); onToggled: sheet.recheck() }
            }
            Column {
                width: parent.width
                spacing: 6
                Item {
                    width: parent.width
                    height: search.height
                    Label { anchors.verticalCenter: parent.verticalCenter; text: qsTr("More equipment") }
                    AppTextField { id: search; anchors.right: parent.right; width: 220; placeholder: qsTr("Filter"); iconName: "search" }
                }
                CheckList {
                    id: equipment
                    width: parent.width
                    maxHeight: 190
                    model: (sheet.c.bookable || []).filter(function (o) {
                        var q = search.text.trim().toLowerCase()
                        return !q || (o.label + " " + o.detail).toLowerCase().indexOf(q) >= 0 || equipment.isSelected(o.value)
                    })
                    emptyText: qsTr("No equipment registered.")
                    onToggled: sheet.recheck()
                }
            }
            Row {
                spacing: Theme.space.md
                Column {
                    width: 360
                    spacing: 6
                    Label { text: qsTr("GCP banners from") }
                    AppSelect { id: gcpStore; width: parent.width; model: sheet.c.stores || []; textRole: "label"; valueRole: "value"
                                onActivated: sheet.recheck() }
                }
                AppTextField { id: gcp; visible: !!gcpStore.currentValue; width: 140; label: qsTr("How many"); onTextChanged: sheet.recheck() }
            }
            AppTextField { id: notes; width: parent.width; label: qsTr("Notes for the approver (optional)") }
        }

        // ============================================================ existing reservation
        Column {
            visible: sheet.loaded
            width: parent.width
            spacing: Theme.space.sm

            Row {
                spacing: Theme.space.xs
                StatusPill { kind: sheet.d.statusKind || "neutral"; text: sheet.d.statusLabel || "" }
                Txt { anchors.verticalCenter: parent.verticalCenter
                      text: qsTr("%n day(s)", "", sheet.d.days || 0) + "  ·  " + qsTr("asked by %1").arg(sheet.d.requestedBy || "")
                      muted: true }
            }
            Txt { visible: !!sheet.d.decidedBy; width: parent.width; wrapMode: Text.WordWrap; muted: true
                  text: qsTr("%1 by %2").arg(sheet.d.statusLabel || "").arg(sheet.d.decidedBy || "")
                        + (sheet.d.decisionNote ? ": " + sheet.d.decisionNote : "") }
            Txt { visible: !!sheet.d.notes; width: parent.width; wrapMode: Text.WordWrap; text: qsTr("Notes: %1").arg(sheet.d.notes || "") }
            Txt { visible: !!sheet.d.kits; text: qsTr("Kits: %1").arg(sheet.d.kits || ""); variant: "bodyStrong" }
            Repeater {
                model: sheet.d.items || []
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
                        Txt { width: 96; text: modelData.tag; variant: "bodyStrong" }
                        Txt { width: 240; text: modelData.type; elide: Text.ElideRight }
                    }
                    StatusPill { anchors.right: parent.right; anchors.rightMargin: Theme.space.sm; anchors.verticalCenter: parent.verticalCenter
                                 kind: modelData.serviceKind; text: modelData.serviceLabel }
                }
            }
            Txt { visible: (sheet.d.gcp || 0) > 0; text: qsTr("GCP banners: %1 from %2").arg(sheet.d.gcp || 0).arg(sheet.d.gcpFrom || ""); variant: "bodyStrong" }
        }

        // ============================================================ conflicts (both modes)
        Rectangle {
            id: panel
            visible: sheet.isNew || (sheet.loaded && sheet.live.blockers !== undefined)
            width: parent.width
            height: checks.implicitHeight + Theme.space.md * 2
            radius: Theme.radius.md
            readonly property bool blocked: (sheet.live.blockers || []).length > 0
            readonly property bool clear: !blocked && (sheet.live.warnings || []).length === 0
                                          && (!sheet.isNew || !!sheet.live.ready)
            color: blocked ? Theme.colors.dangerBg : (clear ? Theme.colors.successBg : Theme.colors.warningBg)
            border.width: 1
            border.color: blocked ? Theme.colors.dangerBorder : (clear ? Theme.colors.successBorder : Theme.colors.warningBorder)
            Behavior on color { ColorAnimation { duration: Theme.motion.standard } }
            Column {
                id: checks
                x: Theme.space.md
                y: Theme.space.md
                width: parent.width - Theme.space.md * 2
                spacing: 4
                Row {
                    spacing: Theme.space.xs
                    Icon {
                        anchors.verticalCenter: parent.verticalCenter
                        name: panel.blocked ? "circle-x" : (panel.clear ? "circle-check" : "alert")
                        size: 16
                        color: panel.blocked ? Theme.colors.dangerText
                             : panel.clear ? Theme.colors.successText : Theme.colors.warningText
                    }
                    Txt {
                        variant: "bodyStrong"
                        text: (sheet.live.blockers || []).length
                              ? qsTr("%n clash(es) stop this booking", "", sheet.live.blockers.length)
                              : (sheet.live.warnings || []).length
                                ? qsTr("Bookable, with %n thing(s) to sort out before the job", "", sheet.live.warnings.length)
                                : sheet.isNew && !sheet.live.ready ? qsTr("Choose dates and equipment")
                                                                   : qsTr("No clashes")
                    }
                }
                Repeater {
                    model: sheet.live.blockers || []
                    delegate: Txt { required property string modelData; width: checks.width; text: "•  " + modelData; color: Theme.colors.dangerText; wrapMode: Text.WordWrap }
                }
                Repeater {
                    model: sheet.live.warnings || []
                    delegate: Txt { required property string modelData; width: checks.width; text: "•  " + modelData; color: Theme.colors.warningText; wrapMode: Text.WordWrap }
                }
            }
        }

        AppTextField {
            id: decisionNote
            visible: sheet.deciding !== ""
            width: parent.width
            label: sheet.deciding === "reject" ? qsTr("Reason for rejecting (required)")
                   : sheet.deciding === "cancel" ? qsTr("Reason for cancelling (optional)") : qsTr("Note (optional)")
        }
        ErrorBanner { text: Reservations.error }
    }

    actions: [
        AppButton { text: sheet.deciding ? qsTr("Back") : (sheet.isNew ? qsTr("Cancel") : qsTr("Close"))
                    onClicked: sheet.deciding ? sheet.deciding = "" : sheet.close() },
        // new request
        AppButton {
            visible: sheet.isNew
            variant: "primary"
            iconName: "calendar"
            text: Reservations.canApprove ? qsTr("Book") : qsTr("Send request")
            busy: Tasks.busy
            enabled: !Tasks.busy && !!sheet.r.ready && !!project.currentValue
            onClicked: Reservations.request(sheet.values())
        },
        // decisions on an existing reservation
        AppButton {
            visible: sheet.loaded && !!sheet.d.canCancel && sheet.deciding === ""
            variant: "ghost"
            text: qsTr("Cancel reservation…")
            onClicked: { sheet.deciding = "cancel"; decisionNote.text = "" }
        },
        AppButton {
            visible: sheet.loaded && !!sheet.d.canApprove && sheet.deciding === ""
            text: qsTr("Reject…")
            onClicked: { sheet.deciding = "reject"; decisionNote.text = "" }
        },
        AppButton {
            visible: sheet.loaded && !!sheet.d.canApprove && sheet.deciding === ""
            variant: "primary"
            text: qsTr("Approve and book")
            enabled: !Tasks.busy && (sheet.live.blockers || []).length === 0
            onClicked: { sheet.deciding = "approve"; decisionNote.text = "" }
        },
        AppButton {
            visible: sheet.loaded && !!sheet.d.canCheckOut && sheet.deciding === ""
            variant: "primary"
            iconName: "send"
            text: qsTr("Check out now")
            onClicked: { checkout.openFromReservation(sheet.d); sheet.close() }
        },
        AppButton {
            visible: sheet.deciding !== ""
            variant: sheet.deciding === "approve" ? "primary" : "danger"
            text: sheet.deciding === "approve" ? qsTr("Approve and book")
                  : sheet.deciding === "reject" ? qsTr("Reject request") : qsTr("Cancel reservation")
            busy: Tasks.busy
            enabled: !Tasks.busy
            onClicked: {
                if (sheet.deciding === "approve") Reservations.approve(sheet.d.reservationId, sheet.d.version, decisionNote.text)
                else if (sheet.deciding === "reject") Reservations.reject(sheet.d.reservationId, sheet.d.version, decisionNote.text)
                else Reservations.cancel(sheet.d.reservationId, sheet.d.version, decisionNote.text)
            }
        }
    ]

    CheckoutSheet { id: checkout }
}
