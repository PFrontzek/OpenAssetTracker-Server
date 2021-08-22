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

var trackerSelected = $("#trackerSelected");
var trackerAll = $("#trackerAll");
$("#bttnAdd").on("click", function () {
    $("#trackerAll option:selected").each(function (i, ele) {
        var element = $(ele);
        element.prependTo(trackerSelected);
    });
});
$("#bttnRemove").on("click", function () {
    trackerSelected.find("option:selected").each(function (i, ele) {
        var element = $(ele);
        element.prependTo(trackerAll);
    });
});
$("#myForm").on("submit", function () {
    var values = [];
    trackerSelected.find("option").each(function (i, ele) {
        var element = $(ele);
        values.push(element.val());
        console.log(element.val());
    });
    $("#hvTracker").val(JSON.stringify(values));
    console.log($("myForm").val());
    return true;
});
$("#bttnSubmit").on("click", function () {
    trackerSelected.find("option").each(function (i, ele) {
        var element = $(ele);
        console.log(element.val());
    });
});
