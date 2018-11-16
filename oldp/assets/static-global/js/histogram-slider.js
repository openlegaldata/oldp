import $ from "jquery";

import 'jquery-ui/ui/core';
import 'jquery-ui/ui/widgets/slider';

const pluginName = "histogramSlider",
        dataKey = "plugin_" + pluginName;

let updateHistogram = function (selectedRange, sliderMin, rangePerBin, histogramName, sliderName) {
    let leftValue = selectedRange[0],
        rightValue = selectedRange[1];

    //$("#" + sliderName + "-value").html(leftValue + " - " + rightValue);

    // set opacity per bin based on the slider values
    $("#" + histogramName + " .in-range").each(function (index, bin) {
        let binRange = getBinRange(rangePerBin, index, sliderMin);

        if (binRange[1] < rightValue) {
            // Set opacity based on left (min) slider
            if (leftValue > binRange[1]) {
                setOpacity(bin, 0);
            } else if (leftValue < binRange[0]) {
                setOpacity(bin, 1);
            } else {
                //setOpacity(bin, 1);
                setOpacity(bin, 1 - (leftValue - binRange[0]) / rangePerBin);
            }
        } else if (binRange[0] > leftValue) {
            // Set opacity based on right (max) slider value
            if (rightValue > binRange[1]) {
                setOpacity(bin, 1);
            } else if (rightValue < binRange[0]) {
                setOpacity(bin, 0);
            } else {
                //setOpacity(bin, 1);
                setOpacity(bin, (rightValue - binRange[0]) / rangePerBin);
            }
        }
    });
};

let getBinRange = function(rangePerBin, index, sliderMin) {
    let min = (rangePerBin * index) + sliderMin,
        max = rangePerBin * (index + 1) - 1;

    return [min, max];
};

let setOpacity = function(bin, val) {
    $(bin).css("opacity", val);
};

let convertToHeight = function (v) {
    // console.log('convertToHeight: ', v);
    // return parseInt(5 * v + 1);
    return parseInt(v + 1);
};

let calculateHeightRatio = function(bins, histogramHeight) {
    let maxValue = Math.max.apply(null, bins);
    let height = convertToHeight(maxValue);

    if (height > histogramHeight) {
        return histogramHeight / height;
    }

    return 1;
};

function monthDiff(d1, d2) {
    let months;
    months = (d2.getFullYear() - d1.getFullYear()) * 12;
    months -= d1.getMonth() + 1;
    months += d2.getMonth();
    return months <= 0 ? 0 : months;
}

function setDateRange(startDate, endDate) {

    $("span.rangeFromDate").text(startDate);
    $("span.rangeToDate").text(endDate);

    $("input.rangeFromDate").val(startDate);
    $("input.rangeToDate").val(endDate);
}

let sliderValueToDate = function(v, startDate, extraDay) {
  // console.log('Slider value to date: v=', v, ' startDate=', startDate);

  let d = new Date(startDate);
  d.setMonth(startDate.getMonth() + parseInt(v) );

  // if (extraDay) {
  //   d.setDate(startDate.getDate() + 1);
  //   }

  //d.setTime(startDate.getTime() + parseInt(v) * 1000 * 3600 * 24 );
  return d.toISOString().slice(0, 10);
};

let Plugin = function (element, options) {
    this.element = element;

    this.options = {
        sliderRange: [0, 1000000], // Min and Max slider values
        optimalRange: [-1, -1], // Optimal range to select within
        selectedRange: [0, 0], // Min and Max slider values selected
        height: 150,
        numberOfBins: 40,
        showTooltips: false,
        showSelectedRange: false,
        startDate: new Date(),
        step: 1,
    };

    this.init(options);
};

Plugin.prototype = {
    getNumberOfBins: function () {
      return monthDiff(this.options.startDate, this.options.endDate);
    },
    getSliderRange: function() {
      return [0, monthDiff(this.options.startDate, this.options.endDate)];
    },
    getSelectedRange: function() {
      return this.getSliderRange();
    },
    init: function (options) {
        $.extend(this.options, options);

        let self = this;

        let dataItems = $(self.element).data('items');

        self.options.startDate = new Date($(self.element).data('start-date'));
        self.options.endDate = new Date($(self.element).data('end-date'));

        let bins = new Array(this.getNumberOfBins()).fill(0),
            range = this.getSliderRange()[1] - this.getSliderRange()[0],
            rangePerBin = range / this.getNumberOfBins();

        for (let i = 0; i < dataItems.length; i++) {
            // Convert date str to slider value
            dataItems[i].value = monthDiff(self.options.startDate, new Date(dataItems[i].date));

            // console.log(dataItems[i].value);

            let index = parseInt(dataItems[i].value / rangePerBin),
                increment = 1;

            if (dataItems[i].count) {
                // Handle grouped data structure
                increment = parseInt(dataItems[i].count);
            }

            bins[index] += increment;
        }

        let histogramName = self.element.attr('id') + "-histogram",
            sliderName = self.element.attr('id') + "-slider";

        let wrapHtml = "<div id='" + histogramName + "' style='height:" + self.options.height + "px; overflow: hidden;'></div>" +
            "<div id='" + sliderName + "'></div>";

        self.element.html(wrapHtml);

        let heightRatio = calculateHeightRatio(bins, self.options.height),
            widthPerBin = 100 / this.getNumberOfBins();

        for (let i = 0; i < bins.length; i++) {
          // console.log(rangePerBin, ' -  -  ', this.getSliderRange());

            let binRange = getBinRange(rangePerBin, i, this.getSliderRange()[0]),
                inRangeClass = "bin-color-selected",
                outRangeClass = "bin-color";
            //console.log(binRange);
            if (self.options.optimalRange[0] <= binRange[0] && binRange[0] <= self.options.optimalRange[1]) {
                inRangeClass = "bin-color-optimal-selected";
                outRangeClass = "bin-color-optimal";
            }

            let toolTipHtml = self.options.showTooltips ? "<span class='tooltiptext'>" + bins[i] + " docs - " + sliderValueToDate(binRange[0], self.options.startDate, true) + "</span>" : "";

            let scaledValue = parseInt(bins[i] * heightRatio),
                height = convertToHeight(scaledValue),
                inRangeOffset = parseInt(self.options.height - height),
                outRangeOffset = -parseInt(self.options.height - height * 2);

            let binHtml = "<div class='slider-tooltip' style='float:left!important;width:" + widthPerBin + "%;'>" +
                toolTipHtml +
                "<div class='bin in-range " + inRangeClass + "' style='height:" + height + "px;bottom:-" + inRangeOffset + "px;position: relative;'></div>" +
                "<div class='bin out-of-range " + outRangeClass + "' style='height:" + height + "px;bottom:" + outRangeOffset + "px;position: relative;'></div>" +
                "</div>";

            $("#" + histogramName).append(binHtml);
        }

        $("#" + sliderName).slider({
            range: true,
            min: self.getSliderRange()[0],
            max: self.getSliderRange()[1],
            step: self.options.step,
            values: self.getSelectedRange(),
            slide: function (event, ui) {
                updateHistogram(ui.values, self.getSliderRange()[0], rangePerBin, histogramName, sliderName);

                let startDate = sliderValueToDate(ui.values[0], self.options.startDate, true),
                    endDate = sliderValueToDate(ui.values[1], self.options.startDate);

                setDateRange(startDate, endDate);

                //$("#rangeFromDate").text(parseInt(ui.values[0]));
                //$("#rangeToDate").text(diffDays - parseInt(ui.values[1]));
            }
        });

        if (self.options.showSelectedRange){
            $("#" + sliderName).after("<p id='" + sliderName + "-value' class='selected-range'></p>");
        }


        setDateRange(sliderValueToDate(0, self.options.startDate, true), sliderValueToDate(self.getNumberOfBins(), self.options.startDate));

        updateHistogram(self.getSelectedRange(), self.getSliderRange()[0], rangePerBin, histogramName, sliderName);
    }
};

$.fn[pluginName] = function (options) {
    let plugin = this.data(dataKey);

    if (plugin instanceof Plugin) {
        if (typeof options !== 'undefined') {
            plugin.init(options);
        }
    } else {
        plugin = new Plugin(this, options);
        this.data(dataKey, plugin);
    }

    return plugin;
};
