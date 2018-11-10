import $ from 'jquery';
import 'bootstrap';
// import 'select2';
import 'select2/dist/js/select2.full.js';

// import $ from 'jquery/src/core'; // partial imports not needed

window.jQuery = $;
window.$ = $;

// import './autocomplete_light/jquery.init'
// import './autocomplete_light/autocomplete.init'
// import './autocomplete_light/forward'
// import './autocomplete_light/select2'
// import './autocomplete_light/jquery.post-setup'

// 'admin/js/vendor/jquery/jquery%s.js' % extra,
//                 'autocomplete_light/jquery.init.js',
//                 'admin/js/vendor/select2/select2.full%s.js' % extra,
//             ) + i18n_file + (
//                 'autocomplete_light/autocomplete.init.js',
//                 'autocomplete_light/forward.js',
//                 'autocomplete_light/select2.js',
//                 'autocomplete_light/jquery.post-setup.js',

function searchRedirect(query) {
    location.href = '/search?query=' + encodeURIComponent(query);
}
function readMore() {
    $('.readmore').show();
    // $('.section-readmore').show();

    $('.btn-readmore').hide();
}

function resetLineFocus() {
    $('.table-lines tr.line').css('background', '');
}

function focusLine(line) {
    $('.table-lines tr.line[data-line="' + line + '"]').css('background-color', 'rgb(248, 238, 199)');
}

function clickRefMarker(refMarker) {
    var refMarkerUuid = $(refMarker).data('ref-uuid');
    var markers = $('.ref-marker-uuid-' + refMarkerUuid + " a");
    if(markers.length == 1) {
        // Single ref -> redirect to search endpoint
        // searchRedirect(markers.first().data('ref-id'));
        location.href = markers.attr('href');

    } else if(markers.length > 1) {
        // Multiple refs for one marker
        // var refMarkerObj = $('.ref-marker-uuid-' + refMarkerUuid);
        markers.css('background-color', 'rgb(248, 238, 199)');

        location.href = '#refs';

        // $('html, body').animate({
        //     scrollTop: refMarkerObj.offset().top
        // }, 2000);
    } else {
        throw new Error('Ref marker not found: uuid=' + refMarkerUuid);
    }
}

function hashChange() {
    var anchor = document.location.hash;

    if (anchor.substr(1, 1) === 'L') {
        resetLineFocus();
        readMore();

        var lineStr = anchor.substr(2);

        var splits = lineStr.split(',');

        for(var i=0; i < splits.length; i++) {
            var range = splits[i].split('-');
            if(range.length == 1) {
                var line = parseInt(range[0]);

                focusLine(line);

            } else if(range.length == 2) {
                for(var j=parseInt(range[0]); j <= parseInt(range[1]); j++) {
                    focusLine(j);
                }
            } else {
                // error
                throw new Error('Invalid line id');
            }
        }

    }
}

$(document).ready(function() {
    $(window).bind( 'hashchange', function(e) {
        hashChange();
    });
    hashChange();

    $(document).ready(function() {
        // $('.select2').select2();
    });
});
