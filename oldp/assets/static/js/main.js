// main JS for Web app
// - facets show
// - clickable reference markers -> scroll to reference section
// - toggle entity markers
// - read more for case text
// - dropdown navbar

(function() {
    // Show hidden facets
    window.showMoreFacets = function(btn) {
      btn.style.display = 'none';
      const facetName = btn.dataset.facetName;
      document
        .querySelectorAll(`.search-facet-more[data-facet-name="${facetName}"]`)
        .forEach(el => {
          // simple fade-in
          el.style.opacity = 0;
          el.style.display = '';
          let last = +new Date();
          const tick = function() {
            el.style.opacity = +el.style.opacity + (new Date() - last) / 200;
            last = +new Date();
  
            if (+el.style.opacity < 1) {
              (window.requestAnimationFrame && requestAnimationFrame(tick)) || setTimeout(tick, 16);
            }
          };
          tick();
        });
    };
  
    // Click on a reference marker
    window.clickRefMarker = function(link) {
      const markerId = link.dataset.markerId;
      const markers = Array.from(document.querySelectorAll(`.ref-marker-id-${markerId}`));
  
      if (markers.length === 1) {
        // redirect to marker location
        const parent = markers[0].parentElement;
        const refLink = parent.querySelector('.reference-link');
        if (refLink && refLink.href) {
          window.location.href = refLink.href;
        }
      } else {
        // smooth-scroll to #references
        const refs = document.getElementById('references');
        if (refs) {
          refs.scrollIntoView({ behavior: 'smooth' });
        }
      }
  
      return false;
    };
  
    // Toggle entity markers on/off
    window.toggleEntityMarkers = function(type) {
      document
        .querySelectorAll(`span.entity-${type}`)
        .forEach(el => el.classList.toggle('entity-off'));
      document
        .querySelectorAll(`button.entity-${type} i`)
        .forEach(icon => icon.classList.toggle('fa-toggle-on'));
    };
  
    // Toggle individual markers on/off
    window.toggleMarkers = function(labelId) {
      document
        .querySelectorAll(`span.marker-label${labelId}`)
        .forEach(el => el.classList.toggle('marker-off'));
      document
        .querySelectorAll(`button.marker-label${labelId} i`)
        .forEach(icon => {
          icon.classList.toggle('fa-toggle-off');
          icon.classList.toggle('fa-toggle-on');
        });
    };
  
    // Autocomplete widgets
    document.addEventListener('DOMContentLoaded', function() {
      document.querySelectorAll('.autocomplete-widget').forEach(function(container) {
        var url = container.dataset.autocompleteUrl;
        var textInput = container.querySelector('input[type="text"]');
        var hiddenInput = container.querySelector('input[type="hidden"]');
        var dropdown = container.querySelector('.autocomplete-dropdown');
        var debounceTimer = null;
        var activeIndex = -1;

        textInput.addEventListener('input', function() {
          hiddenInput.value = '';
          activeIndex = -1;
          var query = textInput.value.trim();
          clearTimeout(debounceTimer);
          if (query.length < 1) {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
            return;
          }
          debounceTimer = setTimeout(function() {
            fetch(url + '?q=' + encodeURIComponent(query))
              .then(function(r) { return r.json(); })
              .then(function(data) {
                dropdown.innerHTML = '';
                activeIndex = -1;
                if (!data.results || data.results.length === 0) {
                  dropdown.style.display = 'none';
                  return;
                }
                data.results.forEach(function(item) {
                  var div = document.createElement('div');
                  div.className = 'autocomplete-item';
                  div.textContent = item.text;
                  div.dataset.value = item.id;
                  div.addEventListener('mousedown', function(e) {
                    e.preventDefault();
                    selectItem(item.id, item.text);
                  });
                  dropdown.appendChild(div);
                });
                dropdown.style.display = 'block';
              });
          }, 250);
        });

        textInput.addEventListener('keydown', function(e) {
          var items = dropdown.querySelectorAll('.autocomplete-item');
          if (!items.length) return;
          if (e.key === 'ArrowDown') {
            e.preventDefault();
            activeIndex = Math.min(activeIndex + 1, items.length - 1);
            updateActive(items);
          } else if (e.key === 'ArrowUp') {
            e.preventDefault();
            activeIndex = Math.max(activeIndex - 1, 0);
            updateActive(items);
          } else if (e.key === 'Enter' && activeIndex >= 0) {
            e.preventDefault();
            var item = items[activeIndex];
            selectItem(item.dataset.value, item.textContent);
          } else if (e.key === 'Escape') {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
            activeIndex = -1;
          }
        });

        textInput.addEventListener('blur', function() {
          setTimeout(function() {
            dropdown.innerHTML = '';
            dropdown.style.display = 'none';
          }, 150);
        });

        function selectItem(id, text) {
          hiddenInput.value = id;
          textInput.value = text;
          dropdown.innerHTML = '';
          dropdown.style.display = 'none';
          activeIndex = -1;
        }

        function updateActive(items) {
          items.forEach(function(el, i) {
            el.classList.toggle('active', i === activeIndex);
          });
          if (activeIndex >= 0) {
            items[activeIndex].scrollIntoView({ block: 'nearest' });
          }
        }
      });
    });

    // DOM ready
    document.addEventListener('DOMContentLoaded', function() {
      const readInner = document.querySelector('.read-more-inner');
      const readBtn   = document.querySelector('.read-more button');
      const container = document.querySelector('.read-more-container');
  
      if (readInner && readBtn && container) {
        if (readInner.offsetHeight < 700) {
          readBtn.style.display = 'none';
          container.classList.remove('read-more-container');
        } else {
          readBtn.addEventListener('click', function(evt) {
            evt.preventDefault();
            container.classList.remove('read-more-container');
            readBtn.parentElement.style.display = 'none';
          });
        }
      }

       
    });

    // Bootstrap-like collapse toggle
    document.addEventListener('DOMContentLoaded', function() {
        document.querySelectorAll('[data-toggle="collapse"]').forEach(function(toggle) {
            toggle.addEventListener('click', function(e) {
                e.preventDefault();
                var targetSel = toggle.getAttribute('data-target');
                var target = document.querySelector(targetSel);
                if (!target) return;
                var isOpen = target.classList.contains('show');
                target.classList.toggle('show', !isOpen);
                toggle.setAttribute('aria-expanded', String(!isOpen));
            });
        });
    });

    // Bootstrap-like dropdown toggle
    document.addEventListener('DOMContentLoaded', function() {
        // Grab all dropdown toggles
        var toggles = document.querySelectorAll('[data-toggle="dropdown"]');
      
        // Toggle one dropdown
        toggles.forEach(function(toggle) {
          toggle.addEventListener('click', function(e) {
            e.preventDefault();
            e.stopPropagation();
      
            // Find the .dropdown parent and its menu
            var dropdown = toggle.closest('.dropdown');
            var menu = dropdown.querySelector('.dropdown-menu');
            var isOpen = menu.classList.contains('show');
      
            // Close any open dropdowns first
            closeAll();
      
            if (!isOpen) {
              menu.classList.add('show');
              toggle.setAttribute('aria-expanded', 'true');
            }
          });
        });
      
        // Close on outside click
        document.addEventListener('click', function() {
          closeAll();
        });
      
        // Close on ESC key
        document.addEventListener('keydown', function(e) {
          if (e.key === 'Escape') {
            closeAll();
          }
        });
      
        function closeAll() {
          toggles.forEach(function(toggle) {
            var dropdown = toggle.closest('.dropdown');
            var menu = dropdown.querySelector('.dropdown-menu');
            if (menu.classList.contains('show')) {
              menu.classList.remove('show');
              toggle.setAttribute('aria-expanded', 'false');
            }
          });
        }
      });
      
  })();
  