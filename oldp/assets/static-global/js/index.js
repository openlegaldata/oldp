// Load CSS
import '../scss/style.scss';
// Dependencies from NPM
import $ from 'jquery';
import 'bootstrap';
// import 'select2';
import 'select2/dist/js/select2.full.js';
// Local
import './histogram-slider.js';
// import 'bootstrap/js/dist/util';
// import "select2/dist/css/select2.css";


window.jQuery = $;
window.$ = $;

window.showMoreFacets = function(btn) {
    $(btn).hide();
    $('.search-facet-more[data-facet-name="' + $(btn).data('facet-name') + '"]').fadeIn();
};


$(document).ready(function() {
    $('#histogramSlider').histogramSlider({
        showTooltips: true,
        showSelectedRange: true,
    });

    $(".read-more button").click(function() {
        let btn = $(this),
            up = btn.parent(),
            container = up.parent();

        // Make container full height
        container.removeClass('read-more-container');
        up.hide();

        // prevent jump-down
        return false;

    });
   // $('.select2').select2();
});
