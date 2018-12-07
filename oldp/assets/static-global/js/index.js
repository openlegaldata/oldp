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

window.clickRefMarker = function(link) {
    let uuid = $(link).data('ref-uuid');
    let markers = $('.ref-uuid-' + uuid);

    if(markers.length === 1) {
        // redirect to marker location
        let href = $(markers.parent()).find(".reference-link").attr('href');

        if (href) {
            window.location = href;
        }
    // } else if (markers.length > 1) {
    //     alert('Choose ref:');
    //
    } else {
        // scroll to #refs
        $([document.documentElement, document.body]).animate({
            scrollTop: $('#references').offset().top
        }, 2000);

    }

    return false;
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
