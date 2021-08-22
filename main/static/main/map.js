// Copyright (C) 2021 Patrick Frontzek
// This file is part of OpenAssetTracker-Server.

// OpenAssetTracker-Server is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// OpenAssetTracker-Server is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with OpenAssetTracker-Server.  If not, see <http://www.gnu.org/licenses/>. 

var __assign = (this && this.__assign) || function () {
    __assign = Object.assign || function (t) {
        for (var s, i = 1, n = arguments.length; i < n; i++) {
            s = arguments[i];
            for (var p in s) if (Object.prototype.hasOwnProperty.call(s, p))
                t[p] = s[p];
        }
        return t;
    };
    return __assign.apply(this, arguments);
};
var defaults = {
    url: {
        trackerSettings: urlTrackerSettings,
        deviceBase: urlDeviceBase,
        tableData: urlTableData,
        detail: urlDetail,
        websocket: "" + (location.protocol === "https:" ? "wss://" : "ws://") + window.location.host + "/ws/user/" + requestUserId + "/"
    },
    map: {
        latLng: new L.LatLng(51.447292, 7.272232),
        zoom: 12,
        tileUrlTemplate: "https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png",
        tileOptions: {
            attribution: "&copy; <a href=\"https://www.openstreetmap.org/copyright\">OpenStreetMap</a> contributors"
        },
        circleMarkerOptions: {
            red: {
                color: 'red',
                fillColor: '#f03',
                fillOpacity: 0.3
            },
            green: {
                color: 'green',
                fillColor: 'green',
                fillOpacity: 0.1
            }
        }
    },
    tables: {
        autoWidth: false,
        pagingType: "numbers",
        serverSide: true,
        searchDelay: 500,
        order: [
            [0, 'desc']
        ],
        select: {
            toggleable: false,
            blurable: false
        },
        language: { url: "https://cdn.datatables.net/plug-ins/1.10.20/i18n/German.json" }
    },
    dateTimePicker: {
        useCurrent: false,
        locale: "de",
        keepOpen: true,
        buttons: {
            showToday: true,
            showClear: true,
            showClose: true
        },
        calendarWeeks: true,
        icons: {
            time: 'fa fa-clock',
            date: 'fa fa-calendar',
            up: 'fa fa-arrow-up',
            down: 'fa fa-arrow-down',
            previous: 'fa fa-chevron-left',
            next: 'fa fa-chevron-right',
            today: 'fa fa-calendar-check',
            clear: 'fa fa-delete',
            close: 'fa fa-times'
        }
    },
    modal: {
        show: false
    }
};
var lastXhr = null;
var imei = 0;
var start = 0;
var end = 0;
var selectFirstStatus = false;
var selectLastStatus = false;
var modalMap = $("#mapModal");
var modalTracker = $("#modalTrackerEdit");
var cardStatus = $("#cardStatus");
var cardBodyTableStatus = $("#cardStatusBody");
var cardBodyTableTracker = $("#cardTrackerBody");
var progressTableStatus = $("#progressTableStatus");
var progressTableTracker = $("#progressTableTracker");
var spanModalMapTimestamp = $("#modalMapTimestamp");
var bttnModalTrackerOpen = $("#bttnModalTrackerOpen");
var bttnModalTrackerSave = $("#bttnModalTrackerSave");
var bttnModalMapOpen = $("#bttnModalMapOpen");
var bttnModalMapNext = $("#bttnModalMapNext");
var bttnModalMapPrevious = $("#bttnModalMapPrevious");
var tableTracker = $('#trackerTable').DataTable(__assign(__assign({}, JSON.parse(JSON.stringify(defaults.tables))), {
    dom: "l f tr i p", ajax: {
        url: defaults.url.tableData,
        type: "POST",
        data: function (d) {
            d["type"] = "tracker";
            return JSON.stringify(d);
        },
        headers: {
            "X-CSRFToken": token,
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
        }
    }, columns: [
        { data: "imei" },
        { data: "alias" },
        {
            data: {
                _: "battery.display",
                sort: "battery.percentage"
            }
        },
    ]
}));
var tableStatus = $('#statusTable').DataTable(__assign(__assign({}, JSON.parse(JSON.stringify(defaults.tables))), {
    dom: "B l f tr i p", buttons: {
        dom: {
            container: {
                tag: "div",
                className: "btn-group"
            }
        },
        buttons: [{
            text: "Refresh <span id='refreshBadge' class=\"badge badge-light hidden\">0</span>",
            className: "btn btn-outline-primary refreshButton",
            name: "statusRefresh",
            enabled: false,
            action: function (e, dt, node, config) {
                tableStatus.ajax.reload(statusTableReloadCallback, false);
            }
        },
        {
            text: "Export CSV",
            className: "btn btn-primary",
            action: function (e, dt, node, config) {
                var link = document.createElement("a");
                var url = "" + defaults.url.deviceBase + imei + "/export/csv?start=" + start + "&end=" + end;
                link.setAttribute("href", url);
                link.setAttribute("download", url);
                link.click();
                link.remove();
            }
        },
        ]
    }, ajax: {
        url: defaults.url.tableData,
        type: "POST",
        data: function (d) {
            d["type"] = "status";
            d["imei"] = imei;
            d["timespan"] = {
                "start": start,
                "end": end
            };
            return JSON.stringify(d);
        },
        headers: {
            "X-CSRFToken": token,
            'Content-Type': 'application/x-www-form-urlencoded;charset=UTF-8'
        }
    }, columns: [
        {
            data: {
                _: "timestamp.display",
                sort: "timestamp.timestamp"
            }
        },
        { data: "country" },
        { data: "city" },
        { data: "celltower" },
        { data: "temp" },
        {
            data: {
                _: "battery.display",
                sort: "battery.percentage"
            }
        },
    ]
}));
var webSocket = new WebSocket(defaults.url.websocket);
$('.modal').modal(defaults.modal);
var mapMain = L.map('karte').setView(defaults.map.latLng, defaults.map.zoom);
L.tileLayer(defaults.map.tileUrlTemplate, defaults.map.tileOptions).addTo(mapMain);
var layerGroupMapMain = L.layerGroup().addTo(mapMain);
L.control.scale().addTo(mapMain);
if (debug) {
    var mapModal = L.map("modalKarte").setView(defaults.map.latLng, defaults.map.zoom);
    L.tileLayer(defaults.map.tileUrlTemplate, defaults.map.tileOptions).addTo(mapModal);
    L.control.scale().addTo(mapModal);
    var layerGroupMapModal = L.layerGroup().addTo(mapModal);
}
function selectNext(table) {
    var length = table.rows({ selected: true }).length;
    var newId = parseInt(table.rows({ selected: true })[length - 1]) + 1;
    console.log(newId);
    table.rows().deselect();
    if (newId > table.page.len()) {
        selectFirstStatus = true;
        table.page("next").draw(false);
    }
    else {
        table.row(newId, { page: 'current' }).select();
    }
}
;
function selectPrevious(table) {
    var length = table.rows({ selected: true }).length;
    var newId = parseInt(table.rows({ selected: true })[length - 1]) - 1;
    console.log(newId);
    table.rows().deselect();
    if (newId < (debug ? 1 : 0)) {
        selectLastStatus = true;
        table.page("previous").draw('page');
    }
    else {
        table.row(newId, {
            page: 'current'
        }).select();
    }
}
function resetRefreshBadge() {
    var refreshBadge = $("#refreshBadge");
    var refreshButton = $(".refreshButton");
    refreshBadge.text(0);
    refreshBadge.addClass("hidden");
    tableStatus.buttons(refreshButton).disable();
    refreshButton.removeClass("btn-primary");
    refreshButton.addClass("btn-outline-primary");
}
;
function statusTableReloadCallback() {
    tableStatus.order([0, 'desc']).draw();
    layerGroupMapMain.clearLayers();
    if (debug) {
        layerGroupMapModal.clearLayers();
    }
    tableStatus.row(":eq(" + (debug ? 1 : 0) + ")", { page: 'current' }).select();
    resetRefreshBadge();
    progressTableStatus.addClass("minimized");
    cardBodyTableStatus.removeClass("minimized");
}
;
function deselectCallback(e, dt, type, indexes) {
    layerGroupMapMain.clearLayers();
    if (debug) {
        layerGroupMapModal.clearLayers();
    }
}
;
function initTooltips() {
    $('.tooltipped').css("padding", "0.25rem");
    $('.tooltipped').tooltip(defaults.tooltip);
}
;
webSocket.onopen = function () {
    console.log("connected");
    webSocket.send(JSON.stringify("aaaa"));
};
webSocket.onmessage = function (ev) {
    console.log(ev.data);
    var device = JSON.parse(ev.data).device;
    if (device === imei) {
        var refreshButton = $(".refreshButton");
        tableStatus.buttons(refreshButton).enable();
        var refreshBadge = $("#refreshBadge");
        var i = parseInt(refreshBadge.text(), 10);
        refreshBadge.text(++i);
        refreshBadge.removeClass("hidden");
        refreshButton.removeClass("btn-outline-primary");
        refreshButton.addClass("btn-primary");
    }
};
tableTracker.on('deselect', deselectCallback);
tableStatus.on('deselect', deselectCallback);
var fillPlaceholder = function (e, p, sub) {
    if (sub === void 0) { sub = null; }
    var attrs = ["class", "placeholder", "id", "style"];
    if (sub) {
        attrs.forEach(function (attr) {
            e.find(sub).attr(attr, p.attr(attr));
        });
        p.replaceWith(e.find(sub));
        e.remove();
    }
    else {
        attrs.forEach(function (attr) {
            e.attr(attr, p.attr(attr));
        });
        p.replaceWith(e);
    }
};
tableTracker.on("init", function () {
    var wrapper = $("#trackerTable_wrapper");
    // wrapper.addClass('card col-lg-4 col-sm-12 mb-3 p-0 shadow');
    fillPlaceholder($("#trackerTable_length"), $("#trackerTableLength"), "select");
    fillPlaceholder($("#trackerTable_filter"), $("#trackerTableSearch"), "input");
    // let lengthDiv = $("#trackerTable_length");
    // let lengthSelect = lengthDiv.find("select");
    // lengthSelect.attr("class", $("#trackerTableLength").attr("class"));
    // $("#trackerTableLength").replaceWith(lengthSelect);
    // lengthDiv.remove();
    // let filterDiv = $("#trackerTable_filter");
    // let filterControl = filterDiv.find("input");
    // filterControl.attr("class", $("#trackerTableSearch").find("input").attr("class"));
    // filterControl.attr("placeholder", $("#trackerTableSearch").find("input").attr("placeholder"));
    // $("#trackerTableSearch").find("input").replaceWith(filterControl);
    // filterDiv.remove();
    fillPlaceholder($("#trackerTable_info"), $("#trackerTableInfo"));
    fillPlaceholder($("#trackerTable_paginate"), $("#trackerTablePaginate"));
    // $("#trackerTable_wrapper").replaceWith($("#tableTracker"));
    fillPlaceholder($("#trackerTable_wrapper"), $("#cardTrackerBody"));
    cardBodyTableTracker = $("#cardTrackerBody");
    if (debug) {
        modalMap.on("shown.bs.modal", function () { mapModal.invalidateSize(); });
        bttnModalMapOpen.on("click", function () { modalMap.modal("show"); });
        bttnModalTrackerSave.on("click", function () {
            $.ajax({
                url: defaults.url.trackerSettings + imei,
                method: "POST",
                headers: {
                    "X-CSRFToken": token
                },
                data: $("#modalFormTrackerEdit").serialize(),
                beforeSend: function (xhr, settings) {
                    $("#modalFormTrackerEditProgress").removeClass("minimized");
                },
                complete: function (xhr, status) {
                    $("#modalFormTrackerEditProgress").addClass("minimized");
                    var d = tableTracker.row({ selected: true }).data();
                    d["alias"] = $("#modalFormTrackerEditAlias").val();
                    tableTracker.row({ selected: true }).data(d).draw();
                    modalTracker.modal("hide");
                }
            });
        });
        modalTracker.on("shown.bs.modal", function () {
            $.ajax({
                url: defaults.url.trackerSettings + imei,
                method: "GET",
                headers: {
                    "X-CSRFToken": token
                }
            }).done(function (data) {
                $("#modalFormTrackerEditAlias").val(data.alias);
                $("#modalFormTrackerEditImei").val(data.imei);
                $("#modalFormTrackerEditWaittime").val(data.sleeptime);
                $("#modalFormTrackerEditWaittimeUnit option[value='" + data.sleeptime_unit + "']").attr('selected', "true");
                $("#modalFormTrackerEdit").removeClass("minimized");
                $("#modalFormTrackerEditProgress").addClass("minimized");
                $("#modalFormTrackerBttnSave").removeClass("disabled");
            });
        });
        modalTracker.on("hide.bs.modal", function () {
            $("#modalFormTrackerEdit").addClass("minimized");
            $("#modalFormTrackerEditProgress").removeClass("minimized");
            $("#modalFormTrackerBttnSave").addClass("disabled");
        });
        bttnModalTrackerOpen.on("click", function () {
            modalTracker.modal("show");
        });
    }
    ;
    $("#cardTracker").css("height", $("#karte").css("height"));
    $(".table-responsive").css("height", "100%");
    $("#contentRow").css("transform", "scale(1)");
});
tableTracker.on('select', function (e, dt, type, indexes) {
    var rowData = tableTracker.row(indexes).data();
    imei = rowData["imei"];
    bttnModalTrackerOpen.removeClass("disabled");
    bttnModalMapOpen.removeClass("disabled");
    tableStatus.ajax.reload(statusTableReloadCallback, true);
});
tableTracker.on("draw", function (e, settings, json, xhr) {
    initTooltips();
});
tableStatus.on("init", function () {
    fillPlaceholder($("#statusTable_wrapper"), $("#cardStatusBody"));
    fillPlaceholder($("#cardStatusBody").find(".btn-group"), $("#statusTableButtons"));
    fillPlaceholder($("#statusTable_length"), $("#statusTableLength"), "select");
    fillPlaceholder($("#statusTable_filter"), $("#statusTableSearch"), "input");
    fillPlaceholder($("#statusTable_info"), $("#statusTableInfo"));
    fillPlaceholder($("#statusTable_paginate"), $("#statusTablePaginate"));
    cardBodyTableStatus = $("#cardStatusBody");
    $("#dateTimePickerStart").replaceWith("<input type='text' class='form-control datetimepicker-input text-center' id='dateTimePickerStart' data-toggle='datetimepicker' data-target='#dateTimePickerStart'>");
    var dateTimePickerStart = $("#dateTimePickerStart");
    $("#dateTimePickerSeperator").replaceWith("<span class='input-group-text border-left-0 border-right-0 rounded-0'> bis </span>");
    $("#dateTimePickerEnd").replaceWith("<input type='text' class='form-control datetimepicker-input text-center' id='dateTimePickerEnd' data-toggle='datetimepicker' data-target='#dateTimePickerEnd'>");
    var dateTimePickerEnd = $("#dateTimePickerEnd");
    dateTimePickerStart.datetimepicker(defaults.dateTimePicker);
    dateTimePickerStart.datetimepicker("widgetPositioning", {
        horizontal: "right"
    });
    dateTimePickerEnd.datetimepicker(defaults.dateTimePicker);
    dateTimePickerStart.on("change.datetimepicker", function (e) {
        dateTimePickerEnd.datetimepicker("minDate", e["date"]);
        if (start !== e["date"] && e["oldDate"] !== start) {
            start = e["date"].unix();
            tableStatus.ajax.reload(statusTableReloadCallback, true);
        }
    });
    dateTimePickerEnd.on("change.datetimepicker", function (e) {
        dateTimePickerStart.datetimepicker("maxDate", e["date"]);
        if (end !== e["date"] && e["oldDate"] !== end) {
            end = e["date"].unix();
            tableStatus.ajax.reload(statusTableReloadCallback, true);
        }
    });
    if (debug) {
        window.addEventListener("keydown", function (event) {
            // keyCode 38: up
            // keyCode 40: down
            if (event.keyCode == 38) {
                event.preventDefault();
                selectPrevious(tableStatus);
                event.stopPropagation();
                return false;
            }
            else if (event.keyCode == 40) {
                event.preventDefault();
                selectNext(tableStatus);
                event.stopPropagation();
                return false;
            }
        }, false);
    }
});
tableStatus.on('select', function (e, dt, type, indexes) {
    var rowData = tableStatus.row(indexes).data();
    $.ajax({
        url: defaults.url.detail,
        method: "POST",
        data: {
            type: "status",
            id: rowData["id"]
        },
        headers: {
            "X-CSRFToken": token
        }
    }).done(function (data) {
        L.circle([data.lat, data.lon], __assign(__assign({}, defaults.map.circleMarkerOptions.red), { radius: data.radius * 1000 })).addTo(layerGroupMapMain);
        if (debug) {
            L.circle([data.lat, data.lon], __assign(__assign({}, defaults.map.circleMarkerOptions.red), { radius: data.radius * 1000 })).addTo(layerGroupMapModal);
            $.each(data.cells, function (i, cell) {
                L.circle([cell.lat, cell.lon], __assign(__assign({}, defaults.map.circleMarkerOptions.green), { radius: cell.radius })).addTo(layerGroupMapMain);
                L.circle([cell.lat, cell.lon], __assign(__assign({}, defaults.map.circleMarkerOptions.green), { radius: cell.radius })).addTo(layerGroupMapModal);
            });
            mapModal.setView([data.lat, data.lon]);
            spanModalMapTimestamp.html(rowData["timestamp"].display);
        }
        mapMain.setView([data.lat, data.lon]);
    });
});
tableStatus.on("draw", function (e, settings, json, xhr) {
    resetRefreshBadge();
    initTooltips();
    if (selectFirstStatus) {
        tableStatus.row(debug ? 1 : 0, {
            page: 'current'
        }).select();
        selectFirstStatus = false;
    }
    if (selectLastStatus) {
        tableStatus.row(tableStatus.page.len(), {
            page: 'current'
        }).select();
        selectLastStatus = false;
    }
});
tableStatus.on('length', function (e, settings, len) {
    layerGroupMapMain.clearLayers();
    if (debug) {
        layerGroupMapModal.clearLayers();
    }
});
tableStatus.on('preXhr', function (e, settings, data, xhr) {
    if (lastXhr != null) {
        lastXhr.abort();
        console.log("test");
    }
    lastXhr = settings.jqXHR;
    console.log(settings.jqXHR);
    progressTableStatus.removeClass("minimized");
    cardBodyTableStatus.addClass("minimized");
    cardStatus.css("height", cardStatus.height());
});
tableStatus.on('xhr', function () {
    progressTableStatus.addClass("minimized");
    cardBodyTableStatus.removeClass("minimized");
    cardStatus.css("height", "auto");
});
tableTracker.on('xhr', function () {
    progressTableTracker.addClass("minimized");
    cardBodyTableTracker.removeClass("minimized");
});
tableTracker.on('preXhr', function () {
    progressTableTracker.removeClass("minimized");
    cardBodyTableTracker.addClass("minimized");
});
bttnModalMapPrevious.on("click", function () {
    selectPrevious(tableStatus);
});
bttnModalMapNext.on("click", function () {
    selectNext(tableStatus);
});
