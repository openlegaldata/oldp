import $ from 'jquery';
import 'bootstrap';
// import 'select2';
import 'select2/dist/js/select2.full.js';

import './histogram-slider.js';


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

   // $('.select2').select2();
});
