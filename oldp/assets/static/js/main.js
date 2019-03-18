// Load CSS
import '../scss/style.scss';
// Dependencies from NPM
import $ from 'jquery';
import 'bootstrap';
// import 'select2';
import 'select2/dist/js/select2.full.js';
// Local
import './histogram-slider.js';
// import Annotator from './annotator.js';
// import './annotate.js';

// import 'bootstrap/js/dist/util';
// import "select2/dist/css/select2.css";

// window.annotator = new Annotator({
//     document: document,
//     container: document.getElementById('annotator'),
//     body: document.getElementById('annotator-body')
// });

window.jQuery = $;
window.$ = $;

window.showMoreFacets = function(btn) {
    $(btn).hide();
    $('.search-facet-more[data-facet-name="' + $(btn).data('facet-name') + '"]').fadeIn();
};

window.clickRefMarker = function(link) {
    let markerId = $(link).data('marker-id');
    let markers = $('.ref-marker-id-' + uuid);

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

window.toggleEntityMarkers = function(type) {
    $('span.entity-' + type).toggleClass('entity-off');
    $('button.entity-' + type + ' i').toggleClass('fa-toggle-on');
};

window.toggleMarkers = function(labelId) {
    $('span.marker-label' + labelId).toggleClass('marker-off');
    $('button.marker-label' + labelId + ' i').toggleClass('fa-toggle-off').toggleClass('fa-toggle-on');
};

$(document).ready(function() {
    // $('#annotator').annotate();

    $('#histogramSlider').histogramSlider({
        showTooltips: true,
        showSelectedRange: true,
    });

    // Use read-more only for large content
    if($('.read-more-inner').height() < 700) {
        $('.read-more button').hide();
        $('.read-more-container').removeClass('read-more-container');
    } else {

        $('.read-more button').click(function() {
            let btn = $(this),
                up = btn.parent(),
                container = up.parent();

            // Make container full height
            container.removeClass('read-more-container');
            up.hide();

            // prevent jump-down
            return false;
        });
    }

   // $('.select2').select2();
});
